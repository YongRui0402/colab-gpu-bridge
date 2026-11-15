"""原樣轉送到遠端 Ollama(research.md R8:`client.send(..., stream=True)` + `StreamingResponse(r.aiter_raw())`)。

方法、路徑、query、本文與標頭照送,`Host` 改成轉發位址,hop-by-hop 標頭不轉;
回應的狀態碼、標頭與本文原樣傳回(contracts/ollama-compat.openapi.yaml 開頭的處理順序 (4))。
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import anyio
import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from cgb.services.session_lifecycle import ForwardTarget

# contracts/ollama-compat.openapi.yaml § paths./api/generate.post 的 x-timeout:連線 10 秒;收到第一段之前與兩段之間 300 秒
FORWARD_TIMEOUT = httpx.Timeout(10.0, read=300.0)

# RFC 9110 § 7.6.1 的 hop-by-hop 標頭;`Host` 與 `Content-Length` 由 httpx 依轉發位址與本文重新產生
HOP_BY_HOP = frozenset(
    {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "trailers", "transfer-encoding", "upgrade"}
)
_REGENERATED = frozenset({"host", "content-length"})


def _end_to_end(headers: httpx.Headers | dict[str, str], *, drop: frozenset[str] = frozenset()) -> list[tuple[str, str]]:
    """去掉 hop-by-hop 標頭,以及 `Connection` 標頭點名的那些。"""
    items = list(headers.items())
    named = {token.strip().lower() for name, value in items if name.lower() == "connection" for token in value.split(",")}
    return [(name, value) for name, value in items if name.lower() not in HOP_BY_HOP | named | drop]


def _hide_target(headers: list[tuple[str, str]], base_url: str) -> dict[str, str]:
    """回應標頭裡指到轉發位址的網址改成只剩路徑(例如遠端的 302 `Location`),用戶端不會知道也不會直連轉發位址(NFR-003)。"""
    return {name: value.replace(base_url, "") for name, value in headers}


# 串流中途出事時補的最後一行(contracts/ollama-compat.openapi.yaml § paths./api/generate.post 的 x-stream-error-codes)
# 與執行環境的連線中斷(OLLAMA_STREAM_INTERRUPTED)
STREAM_INTERRUPTED_MESSAGE = "串流中斷:與 Colab 執行環境的連線中斷,工作階段正在重連"
# 工作階段在請求進行中被結束,使用者結束或變更執行階段類型(NO_READY_SESSION)
SESSION_ENDED_MESSAGE = "工作階段已結束,這次回應中斷"
NDJSON = "application/x-ndjson"
UNREACHABLE_MESSAGE = "連不到 Colab 上的模型服務,工作階段可能正在重連,請稍後再試"


class StreamAborted(Exception):
    """非 NDJSON 的回應中途斷了,無法補行:讓連線直接中斷,呼叫者收到不完整的本文。"""


def ollama_error(message: str, status_code: int) -> JSONResponse:
    """本系統自己產生的錯誤:本文沿用 Ollama 的 `{"error": ...}`(schema `OllamaError`),原因代碼不放進本文。"""
    return JSONResponse({"error": message}, status_code=status_code)


def error_line(message: str, *, after: bytes) -> bytes:
    """NDJSON 最後補的 `OllamaError` 一行;前一段沒有以換行結尾時先補換行。"""
    line = (json.dumps({"error": message}, ensure_ascii=False) + "\n").encode()
    return line if after.endswith(b"\n") or not after else b"\n" + line


async def cancel_and_reap(pending: "asyncio.Future[bytes]") -> None:
    """取消等不到的那一段並取回結果(對話頁的轉送也用):被取消(用戶端斷開)時,遠端斷線後不留下「Task exception was never retrieved」。

    用戶端斷開時外層正在被取消:遮蔽取消,等那一段收尾(httpx 在裡面關連線)完成。
    """
    pending.cancel()
    with anyio.CancelScope(shield=True):
        await asyncio.gather(pending, return_exceptions=True)


async def _relay(upstream: httpx.Response, ended: asyncio.Event, on_interrupted: Callable[[], None]) -> AsyncIterator[bytes]:
    """逐段傳回。工作階段被結束時不再等遠端,補一行「已結束」;非預期的斷線才通知呼叫端並補「串流中斷」。"""
    chunks = upstream.aiter_raw()
    ended_wait = asyncio.ensure_future(ended.wait())
    last = b""
    next_chunk: asyncio.Future[bytes] | None = None
    try:
        while True:
            next_chunk = asyncio.ensure_future(anext(chunks))
            await asyncio.wait({next_chunk, ended_wait}, return_when=asyncio.FIRST_COMPLETED)
            if not next_chunk.done():
                next_chunk.cancel()
                await asyncio.gather(next_chunk, return_exceptions=True)
                message = SESSION_ENDED_MESSAGE
                break
            try:
                chunk = next_chunk.result()
            except StopAsyncIteration:
                return
            except httpx.TransportError:
                if ended.is_set():
                    message = SESSION_ENDED_MESSAGE
                else:
                    on_interrupted()
                    message = STREAM_INTERRUPTED_MESSAGE
                break
            last = chunk or last
            yield chunk
    finally:
        ended_wait.cancel()
        if next_chunk is not None:
            await cancel_and_reap(next_chunk)
    if not upstream.headers.get("content-type", "").startswith(NDJSON):
        raise StreamAborted(message)
    yield error_line(message, after=last)


async def forward(
    client: httpx.AsyncClient, request: Request, target: ForwardTarget, on_interrupted: Callable[[], None]
) -> Response:
    """把請求送到 `target.base_url`,回應逐段傳回、不緩衝;串流中途非預期斷線時呼叫 `on_interrupted`。"""
    # 直接建 httpx.Request:不經 client.build_request,才不會混進 httpx 預設的 `Connection`、`Accept-Encoding` 等標頭
    upstream_request = httpx.Request(
        request.method,
        httpx.URL(target.base_url + request.url.path, query=request.url.query.encode()),
        headers=_end_to_end(request.headers, drop=_REGENERATED),
        content=await request.body(),
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.ConnectError:
        # OLLAMA_UNREACHABLE:還沒收到任何 HTTP 回應;說明不帶轉發位址與例外原文(NFR-003、NFR-010)
        return ollama_error(UNREACHABLE_MESSAGE, 502)
    return StreamingResponse(
        _relay(upstream, target.ended, on_interrupted),
        status_code=upstream.status_code,
        headers=_hide_target(_end_to_end(upstream.headers), target.base_url),
        background=BackgroundTask(upstream.aclose),
    )
