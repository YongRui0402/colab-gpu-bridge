"""`/api/chat`(contracts/ui.openapi.yaml § paths./chat.post)。

沒有轉接層方法:以 httpx 打 forward target,逐行判讀並轉送(plan.md Q35)。失敗歸類照 contracts/remote-ollama.openapi.yaml
§ paths./api/chat.post 的 info.x-failure-rules 第 1~8 條;串流中途的失敗補一行 `ChatStreamFailure`(物件),
和 Ollama 相容端點 `_relay` 補的 `{"error": "<字串>"}` 是兩回事,所以這裡不共用 `_relay`。
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any

import anyio
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from cgb.api._body import read_json
from cgb.domain.errors import MESSAGES, ApiError, ollama_error
from cgb.domain.model_name import is_valid
from cgb.ollama_compat.forward import NDJSON, cancel_and_reap

router = APIRouter()


def _has_text_content(item: dict[str, Any]) -> bool:
    """`content` 是字串(請求裡的訊息與回應裡的 `message` 共用的欄位檢查)。"""
    return isinstance(item.get("content"), str)


def _parse_line(line: bytes) -> dict[str, Any] | None:
    """一行是 JSON 物件、`done` 是布林(或是帶 `error` 的行),`done: false` 的行 `message.content` 是字串;否則回 None。"""
    try:
        parsed = json.loads(line)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    if "error" in parsed:
        return parsed
    if not isinstance(parsed.get("done"), bool):
        return None
    if not parsed["done"]:
        message = parsed.get("message")
        if not isinstance(message, dict) or not _has_text_content(message):
            return None
    return parsed


def _failure_line(code: str) -> bytes:
    """串流開始之後失敗時補的最後一行 `ChatStreamFailure`(`error` 是物件,不帶遠端的英文原文)。"""
    return (json.dumps({"error": {"code": code, "message": MESSAGES[code]}}, ensure_ascii=False) + "\n").encode()


async def _relay_chat(upstream: httpx.Response, stop: asyncio.Event) -> AsyncIterator[bytes]:
    """逐段轉送遠端的回應,並以行為單位看有沒有出現 `done: true`;串流中途失敗時補一行 `ChatStreamFailure`。

    `stop` 被設定(工作階段被結束、變更類型或判定失聯)時不再等遠端,補 `SESSION_ENDED` 並結束。
    """
    chunks = upstream.aiter_raw()
    stop_wait = asyncio.ensure_future(stop.wait())
    next_chunk: asyncio.Future[bytes] | None = None
    pending = b""
    done = False
    try:
        while True:
            next_chunk = asyncio.ensure_future(anext(chunks))
            await asyncio.wait({next_chunk, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
            if not next_chunk.done():
                yield _failure_line("SESSION_ENDED")
                return
            try:
                chunk = next_chunk.result()
            except StopAsyncIteration:
                break
            except httpx.ReadTimeout:
                yield _failure_line("OLLAMA_TIMEOUT")
                return
            except httpx.TransportError:
                yield _failure_line("OLLAMA_STREAM_INTERRUPTED")
                return
            *complete, pending = (pending + chunk).split(b"\n")
            for line in complete:
                if not line:
                    continue
                parsed = _parse_line(line)
                if parsed is None:
                    # 不是 JSON 物件,或必要欄位的型別不符(x-failure-rules 第 8 條)
                    yield _failure_line("OLLAMA_BAD_RESPONSE")
                    return
                if "error" in parsed:
                    # 遠端自己送的 `{"error": "<英文>"}` 不原樣轉送,換成 `ChatStreamFailure` 並結束(Q6、Q11)
                    yield _failure_line("OLLAMA_SERVER_ERROR")
                    return
                done = done or parsed.get("done") is True
                yield line + b"\n"
        if not done:
            # 遠端正常結束,但還沒出現 `done: true`
            yield _failure_line("OLLAMA_STREAM_INTERRUPTED")
    finally:
        stop_wait.cancel()
        if next_chunk is not None:
            await cancel_and_reap(next_chunk)


# 這幾種狀態表示回覆途中工作階段結束了:使用者結束、變更執行階段類型(結束舊的)、判定失聯(只有對話頁這樣處理,Q60)
_SESSION_OVER = frozenset({"ending", "ended", "lost"})


async def _stream(upstream: httpx.Response, repo: Any, session_name: str, idle: Any) -> AsyncIterator[bytes]:
    """逐段轉送;不論正常結束、失敗或用戶端斷開,最後都關上游,遠端 Ollama 才會停止產生(FR-006)。"""
    stop = asyncio.Event()

    def check() -> None:
        # 看的是送出這則訊息時的那個工作階段:變更類型時最新的一筆已是新的,舊的那筆才是被結束的
        row = repo.get(session_name)
        if row is None or row["state"] in _SESSION_OVER:
            stop.set()

    repo.listeners.append(check)
    try:
        check()
        async with aclosing(_relay_chat(upstream, stop)) as relayed:
            async for chunk in relayed:
                yield chunk
    finally:
        repo.listeners.remove(check)
        idle.request_finished()
        # 用戶端斷開時這裡正在被取消:遮蔽取消,上游才真的關得上
        with anyio.CancelScope(shield=True):
            await upstream.aclose()


# S1 `info.x-failure-rules` 第 3 條:串流開始之前遠端回的狀態碼 → (回給瀏覽器的狀態碼, 代碼)
_FAILED_BEFORE_STREAM = {
    400: (502, "OLLAMA_BAD_REQUEST"),
    404: (404, "OLLAMA_NOT_FOUND"),
    500: (502, "OLLAMA_SERVER_ERROR"),
}


def _is_ndjson(content_type: str) -> bool:
    """只比 media type(`;` 之前、去掉前後空白,不分大小寫),忽略 `charset` 等參數。"""
    return content_type.split(";")[0].strip().lower() == NDJSON


def _is_message(item: object) -> bool:
    return (
        isinstance(item, dict)
        and item.get("role") in ("user", "assistant")
        and _has_text_content(item)
    )


async def _open_upstream(client: httpx.AsyncClient, upstream_request: httpx.Request) -> httpx.Response:
    """送到遠端並判讀串流開始之前的結果(S1 `info.x-failure-rules` 第 1~4 條);不合的丟 `ApiError`。"""
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        # 連線逾時,或在時限內沒收到回應標頭:逾時同時也是傳輸層失敗,所以先看(x-failure-rules 第 1 條)
        raise ollama_error("OLLAMA_TIMEOUT") from None
    except httpx.TransportError:
        # 還沒收到任何 HTTP 回應標頭:OLLAMA_UNREACHABLE(S1 x-failure-rules 第 2 條);說明不帶轉發位址與例外原文(NFR-003、NFR-010)
        raise ollama_error("OLLAMA_UNREACHABLE") from None
    if upstream.status_code in _FAILED_BEFORE_STREAM:
        await upstream.aclose()
        status, code = _FAILED_BEFORE_STREAM[upstream.status_code]
        # 不讀也不轉遠端的 `error` 英文原文;狀態碼換成對瀏覽器有意義的(遠端的 400 不是使用者輸入錯,Q13)
        raise ApiError(status, code)
    if upstream.status_code != 200 or not _is_ndjson(upstream.headers.get("content-type", "")):
        # 其他狀態碼(含 3xx,不跟著導向)與 200 但不是 NDJSON(x-failure-rules 第 3、4 條)
        await upstream.aclose()
        raise ollama_error("OLLAMA_BAD_RESPONSE")
    return upstream


def _check_request(body: object) -> dict[str, Any]:
    """檢查 (1):本文、`model`、`messages` 與每一則訊息的格式;不合的丟 400。"""
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_REQUEST_BODY")
    if not is_valid(body.get("model")):
        raise ApiError(400, "INVALID_MODEL_NAME")
    if not isinstance(body.get("messages"), list) or not body["messages"]:
        raise ApiError(400, "EMPTY_CHAT_MESSAGES")
    if not all(_is_message(m) for m in body["messages"]):
        raise ApiError(400, "INVALID_CHAT_MESSAGE")
    return body


@router.post("/chat")
async def chat(request: Request) -> StreamingResponse:
    services = request.app.state.services
    body = _check_request(await read_json(request))
    target = services.lifecycle.forward_target()
    if target is None:
        # 開啟中、重連中、結束中與沒有工作階段都不排隊、不轉送(FR-008)
        raise ApiError(503, "NO_READY_SESSION")
    session_name = services.sessions_repo.latest()["name"]
    # 通過 (1)(2) 之後,到串流結束之間算進行中的請求,不計閒置;結束時重設倒數(FR-007)
    services.idle.request_started()
    # 只轉 `role` 與 `content`;`stream` 固定 true、`keep_alive` 固定 -1,不加其他參數(plan.md Q9、Q59)
    messages = [{"role": m["role"], "content": m["content"]} for m in body["messages"]]
    payload = {"model": body["model"], "messages": messages, "stream": True, "keep_alive": -1}
    upstream_request = httpx.Request("POST", httpx.URL(target.base_url + "/api/chat"), json=payload)
    try:
        upstream = await _open_upstream(request.app.state.chat_client, upstream_request)
    except BaseException:
        # 串流開始之前失敗:不會有串流結束的收尾,這裡把進行中的請求數減回來
        services.idle.request_finished()
        raise
    return StreamingResponse(
        _stream(upstream, services.sessions_repo, session_name, services.idle),
        media_type=NDJSON,
    )
