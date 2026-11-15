"""E3 Ollama 相容端點的 `/v1/*`(specs/006-agent-client-connect/testplan.md § 2.1;contracts/ollama-compat.openapi.yaml)。

接縫:Ollama 相容端點的 HTTP;工作階段經 UI 的 `/api/session` 開到就緒,轉送打到測試行程內的假 Ollama 伺服器。
`bridge` fixture 沿用 `integration/test_ollama_compat.py`。
"""

from typing import Any

import asyncio
import json
import time

import httpx

from fakes import HangReply, JsonReply
from fakes.ollama_server import SseReply
from integration.test_ollama_compat import Bridge, bridge, timed_request, wait_for  # noqa: F401 - bridge 是 pytest fixture

CHAT_BODY = {"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "你好"}], "stream": False}

# ---------------------------------------------------------------- US1-OC-05


def error_of(response: httpx.Response) -> dict[str, Any]:
    """OpenAI 格式的 `error` 物件;本文不是這個格式時回空字典(讓斷言失敗而不是丟例外)。"""
    try:
        error = response.json().get("error")
    except ValueError:
        return {}
    return error if isinstance(error, dict) else {}


async def test_沒開放的_v1_路徑一律回_404_OpenAI_格式_不轉送(bridge: Bridge) -> None:
    # Arrange:工作階段就緒
    await bridge.ready()

    # Act
    responses = [
        await bridge.ollama.post("/v1/completions", json={"model": "qwen2.5:3b", "prompt": "你好"}),
        await bridge.ollama.post("/v1/embeddings", json={"model": "qwen2.5:3b", "input": "你好"}),
        await bridge.ollama.get("/v1/responses"),
    ]

    # Assert
    assert [r.status_code for r in responses] == [404, 404, 404]
    errors = [error_of(r) for r in responses]
    assert [e.get("code") for e in errors] == ["unsupported_path"] * 3, [r.text for r in responses]
    assert [e.get("type") for e in errors] == ["invalid_request_error"] * 3
    assert all("/v1/chat/completions" in e.get("message", "") and "/v1/models" in e.get("message", "") for e in errors), errors
    assert bridge.server.requests == []


# ---------------------------------------------------------------- US1-OC-01


async def test_v1_chat_completions_非串流原樣轉送並原樣傳回(bridge: Bridge) -> None:
    # Arrange:假 Ollama 的 /v1/chat/completions 回一則 chat.completion
    await bridge.ready()
    completion = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1763251200,
        "model": "qwen2.5:3b",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "你好!"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
    }
    bridge.server.add("POST", "/v1/chat/completions", JsonReply(completion))

    # Act
    response = await bridge.ollama.post(
        "/v1/chat/completions",
        content=json.dumps(CHAT_BODY).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
    )

    # Assert
    bridge.server.assert_all_matched()
    received = bridge.server.requests_to("POST", "/v1/chat/completions")
    assert (response.status_code, response.content) == (200, json.dumps(completion).encode())
    assert len(received) == 1 and received[0].json() == CHAT_BODY


# ---------------------------------------------------------------- US1-OC-02


def sse(*events: dict[str, Any] | str) -> bytes:
    """SSE 的位元組:每段 `data: ` 一行加一個空行(內容是 dict 就是 JSON、是字串就原樣,例如 `[DONE]`)。"""
    return b"".join(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n".encode() for e in events)


def chunk(delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": "chatcmpl-2",
        "object": "chat.completion.chunk",
        "created": 1763251200,
        "model": "qwen2.5:3b",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


STREAM_BODY = {
    **CHAT_BODY,
    "stream": True,
    "stream_options": {"include_usage": True},
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "查天氣",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            },
        }
    ],
}


async def post_stream(bridge: Bridge, body: dict[str, Any]) -> tuple[int, str, bytes]:
    """送 `POST /v1/chat/completions` 並讀完本文:回狀態碼、`Content-Type` 與收到的原始位元組。"""
    received = b""
    async with bridge.ollama.stream("POST", "/v1/chat/completions", json=body) as response:
        async for part in response.aiter_raw():
            received += part
        return response.status_code, response.headers.get("content-type", ""), received


async def test_v1_chat_completions_串流與工具呼叫逐位元組原樣傳回(bridge: Bridge) -> None:
    # Arrange:假 Ollama 回三段 chunk(第二段的 delta 帶完整的 tool_calls)與 [DONE]
    await bridge.ready()
    tool_calls = [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": '{"city":"台北"}'}}]
    events = [chunk({"role": "assistant", "content": ""}), chunk({"tool_calls": tool_calls}), chunk({}, "tool_calls"), "[DONE]"]
    bridge.server.add("POST", "/v1/chat/completions", SseReply(events))

    # Act
    status, content_type, received = await post_stream(bridge, STREAM_BODY)

    # Assert
    forwarded = bridge.server.requests_to("POST", "/v1/chat/completions")
    assert status == 200 and content_type.startswith("text/event-stream"), (status, content_type)
    assert received == sse(*events)
    assert len(forwarded) == 1
    assert forwarded[0].json().get("tools") == STREAM_BODY["tools"]
    assert forwarded[0].json().get("stream_options") == {"include_usage": True}


# ---------------------------------------------------------------- US1-OC-03


async def test_v1_models_原樣轉送模型清單(bridge: Bridge) -> None:
    # Arrange:假 Ollama 的 /v1/models 回一個模型
    await bridge.ready()
    models = {"object": "list", "data": [{"id": "qwen2.5:3b", "object": "model"}]}
    bridge.server.add("GET", "/v1/models", JsonReply(models))

    # Act
    response = await bridge.ollama.get("/v1/models")

    # Assert
    assert (response.status_code, response.content) == (200, json.dumps(models).encode())


# ---------------------------------------------------------------- US1-OC-04


async def test_v1_沒有工作階段時_1_秒內回_503_OpenAI_格式_不轉送(bridge: Bridge) -> None:
    # Arrange:沒有工作階段;假 Ollama 若收到請求就一直不回
    bridge.server.add("POST", "/v1/chat/completions", HangReply())

    # Act
    response, elapsed = await timed_request(bridge.ollama, "POST", "/v1/chat/completions", json=CHAT_BODY)

    # Assert
    assert response is not None and elapsed <= 1.0, elapsed
    assert response.status_code == 503, response.text
    error = error_of(response)
    assert (error.get("type"), error.get("code")) == ("service_unavailable", "no_ready_session"), response.text
    assert "沒有可用的工作階段" in error.get("message", "")
    assert bridge.server.requests == []


# ---------------------------------------------------------------- US1-OC-06


async def test_v1_連不到遠端時回_502_OpenAI_格式_說明不含轉發位址(bridge: Bridge) -> None:
    # Arrange:工作階段就緒,之後假 Ollama 停止,通道回報的位址連不上
    await bridge.ready()
    port = bridge.server.port
    bridge.server.stop()

    # Act
    response = await bridge.ollama.post("/v1/chat/completions", json=CHAT_BODY)

    # Assert
    assert response.status_code == 502, response.text
    error = error_of(response)
    assert error.get("code") == "ollama_unreachable", response.text
    assert "127.0.0.1" not in error.get("message", "") and str(port) not in error.get("message", "")


# ---------------------------------------------------------------- US1-OC-07


async def read_sse(client: httpx.AsyncClient, body: dict[str, Any], received: bytearray) -> bool:
    """`POST /v1/chat/completions` 串流讀完,收到的位元組放進 `received`。正常結束回 True,中途被重設(本文不完整)回 False。"""
    try:
        async with client.stream("POST", "/v1/chat/completions", json=body) as response:
            async for part in response.aiter_raw():
                received.extend(part)
    except (httpx.RemoteProtocolError, httpx.ReadError):
        return False
    return True


def sse_segments(raw: bytes) -> list[str]:
    """SSE 本文依空行切成各段的 `data: ` 之後的內容。"""
    return [segment.removeprefix("data: ") for segment in raw.decode().split("\n\n") if segment]


async def test_v1_串流中途斷線時補一段_stream_interrupted_與_DONE_連線正常結束(bridge: Bridge) -> None:
    # Arrange:假 Ollama 送完第一段就斷線
    await bridge.ready()
    first = chunk({"role": "assistant", "content": "你"})
    bridge.server.add("POST", "/v1/chat/completions", SseReply([first], then="disconnect"))
    received = bytearray()

    # Act
    completed = await read_sse(bridge.ollama, {**CHAT_BODY, "stream": True}, received)

    # Assert
    assert completed, f"串流沒有正常收尾,收到 {bytes(received)!r}"
    segments = sse_segments(bytes(received))
    assert len(segments) == 3, segments
    assert json.loads(segments[0]) == first
    error = json.loads(segments[1]).get("error", {})
    assert (error.get("type"), error.get("code")) == ("api_error", "stream_interrupted"), segments[1]
    assert error.get("message")
    assert segments[2] == "[DONE]"


# ---------------------------------------------------------------- US1-OC-08


async def test_v1_串流中使用者結束工作階段時補一段_no_ready_session_與_DONE(bridge: Bridge) -> None:
    # Arrange:假 Ollama 送完第一段就停住
    await bridge.ready()
    first = chunk({"role": "assistant", "content": "你"})
    bridge.server.add("POST", "/v1/chat/completions", SseReply([first], then="hang"))
    received = bytearray()

    # Act:收到第一段之後結束工作階段
    reading = asyncio.create_task(read_sse(bridge.ollama, {**CHAT_BODY, "stream": True}, received))
    try:
        got_first = await wait_for(lambda: b"\n\n" in received, timeout=2.0)
        await bridge.ui.delete("/api/session")
        completed = await asyncio.wait_for(reading, 5.0)
    finally:
        reading.cancel()

    # Assert
    assert got_first, "收不到第一段"
    assert completed, f"串流沒有正常收尾,收到 {bytes(received)!r}"
    segments = sse_segments(bytes(received))
    assert len(segments) == 3, segments
    assert json.loads(segments[0]) == first
    assert json.loads(segments[1]).get("error", {}).get("code") == "no_ready_session", segments[1]
    assert segments[2] == "[DONE]"


# ---------------------------------------------------------------- US1-OC-09


async def test_v1_遠端回的模型不存在_404_原樣傳回_不改寫(bridge: Bridge) -> None:
    # Arrange:假 Ollama 回 404 與它自己的錯誤本文
    await bridge.ready()
    remote_error = {"error": {"message": 'model "nope" not found', "type": "api_error"}}
    bridge.server.add("POST", "/v1/chat/completions", JsonReply(remote_error, status=404))

    # Act
    response = await bridge.ollama.post("/v1/chat/completions", json={**CHAT_BODY, "model": "nope"})

    # Assert
    assert (response.status_code, response.content) == (404, json.dumps(remote_error).encode())


# ---------------------------------------------------------------- US1-OC-10


async def test_原生路徑的錯誤本文仍是字串_不受_v1_格式影響(bridge: Bridge) -> None:
    # Arrange:沒有開工作階段

    # Act
    responses = [
        await bridge.ollama.post("/api/generate", json={"model": "qwen2.5:3b", "prompt": "你好"}),
        await bridge.ollama.post("/api/pull", json={"model": "qwen2.5:3b"}),
        await bridge.ollama.get("/api/me"),
    ]

    # Assert
    assert [r.status_code for r in responses] == [503, 403, 404]
    assert all(isinstance(r.json().get("error"), str) for r in responses), [r.text for r in responses]


# ---------------------------------------------------------------- US1-OC-11


async def test_v1_串流不緩衝_每一段送出後_0_5_秒內到達(bridge: Bridge) -> None:
    # Arrange:假 Ollama 每 0.1 秒送一段、共 10 段(第 i 段最早在請求送出後 i * 0.1 秒送出)
    await bridge.ready()
    interval, count = 0.1, 10
    bridge.server.add("POST", "/v1/chat/completions", SseReply([chunk({"content": str(i)}) for i in range(count)], interval=interval))
    arrivals: list[float] = []
    seen = 0

    # Act:記下每一段到達用戶端的時間
    started = time.monotonic()
    async with bridge.ollama.stream("POST", "/v1/chat/completions", json={**CHAT_BODY, "stream": True}) as response:
        async for part in response.aiter_raw():
            seen += part.count(b"\n\n")
            arrivals.extend([time.monotonic()] * (seen - len(arrivals)))

    # Assert:到達時間減去最早的送出時間,是延遲的上限
    assert len(arrivals) == count, arrivals
    delays = [arrived - (started + i * interval) for i, arrived in enumerate(arrivals)]
    assert max(delays) <= 0.5, delays
    assert arrivals[0] < started + (count - 1) * interval, "第一段在最後一段送出之後才到達(被緩衝成一次傳回)"
