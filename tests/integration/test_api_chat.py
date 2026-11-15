"""E2 後端 UI API:`POST /api/chat`(testplan.md § 3.1;contracts/ui.openapi.yaml § paths./chat.post)。

接縫:UI 的 HTTP(`/api/chat` 與 `/api/session`);工作階段經 `/api/session` 開到就緒,五個轉接層用替身,
對話真的經過 httpx 打到測試行程內的假 Ollama 伺服器(`fakes.server`)。串流的案例一律用 `live_servers`。
"""

import asyncio
import gc
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any

import httpx
import pytest

from cgb.app import Timeouts
from fakes import DisconnectReply, Gate, HangReply, JsonReply, NdjsonReply
from integration.test_api_models import set_loaded, set_tags, tag
from integration.test_api_session import wait_for_state
from integration.test_ollama_compat import (
    MODEL,
    Bridge,
    closed_port,
    connect,
    enter_opening,
    enter_reconnecting,
    has_cjk,
    wait_for,
)


@pytest.fixture
async def bridge(live_servers: Any, fakes: Any) -> AsyncIterator[Bridge]:
    async with connect(live_servers, fakes) as connected:
        yield connected


def chunk(text: str) -> dict[str, Any]:
    return {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "message": {"role": "assistant", "content": text}, "done": False}


DONE = {
    "model": MODEL,
    "created_at": "2026-11-09T09:00:02Z",
    "message": {"role": "assistant", "content": ""},
    "done": True,
    "done_reason": "stop",
    "total_duration": 1000000000,
    "load_duration": 1000000,
    "prompt_eval_count": 12,
    "eval_count": 30,
    "eval_duration": 762323000,
}

CHAT_BODY = {"model": MODEL, "messages": [{"role": "user", "content": "你好"}]}


# ---- 004 US2-API-01


async def test_回覆逐行傳回_不等整則收完(bridge: Bridge) -> None:
    # Arrange:替身送 3 行,第 2、3 行之前各等測試放行
    await bridge.ready()
    g1, g2 = Gate(), Gate()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你"), g1, chunk("好"), g2, DONE]))
    lines: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}

    async def consume() -> None:
        async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
            meta["status"] = response.status_code
            meta["content_type"] = response.headers.get("content-type")
            async for line in response.aiter_lines():
                lines.append(json.loads(line))

    # Act
    reading = asyncio.create_task(consume())
    try:
        first_early = await wait_for(lambda: len(lines) >= 1, timeout=0.3)
        g1.release()
        await wait_for(lambda: len(lines) >= 2, timeout=2.0)
    finally:
        g1.release()
        g2.release()
    await asyncio.wait_for(reading, 5.0)

    # Assert
    assert meta["status"] == 200
    assert (meta["content_type"] or "").startswith("application/x-ndjson")
    assert first_early, "放行第 1 道閘門之前,用戶端沒有讀到第 1 行(串流被緩衝成一次傳回)"
    assert lines == [chunk("你"), chunk("好"), DONE]
    assert lines[-1]["eval_count"] == 30
    assert lines[-1]["eval_duration"] == 762_323_000


# ---- 004 US2-API-02


async def test_只轉_model_與_messages_的_role_content_並固定串流與保留載入(bridge: Bridge) -> None:
    # Arrange
    await bridge.ready()
    bridge.fakes.remote_ollama.list_local_models.reset_calls()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("c"), DONE]))
    name = "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF"
    body = {
        "model": name,
        "messages": [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b", "thinking": "想"},
            {"role": "user", "content": "c", "images": ["aGk="]},
        ],
        "stream": False,
        "keep_alive": "5m",
        "think": True,
        "options": {"temperature": 0},
        "system": "s",
        "format": "json",
    }

    # Act
    response = await bridge.ui.post("/api/chat", json=body)

    # Assert
    received = bridge.server.requests_to("POST", "/api/chat")
    assert response.status_code == 200
    assert len(received) == 1
    assert received[0].json() == {
        "model": name,
        "messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}],
        "stream": True,
        "keep_alive": -1,
    }
    assert [set(m) for m in received[0].json()["messages"][1:]] == [{"role", "content"}, {"role", "content"}]
    assert len(bridge.server.requests_to("GET", "/api/tags")) == 0
    assert bridge.fakes.remote_ollama.list_local_models.call_count == 0


# ---- 004 US2-API-03

DONE_WITHOUT_EVAL_COUNT = {k: v for k, v in DONE.items() if k != "eval_count"}
DONE_WITHOUT_EVAL_DURATION = {k: v for k, v in DONE.items() if k != "eval_duration"}
DONE_WITH_ZERO_EVAL_DURATION = {**DONE, "eval_duration": 0}


@pytest.mark.parametrize(
    "done_line",
    [DONE_WITHOUT_EVAL_COUNT, DONE_WITHOUT_EVAL_DURATION, DONE_WITH_ZERO_EVAL_DURATION],
    ids=["缺 eval_count", "缺 eval_duration", "eval_duration 為 0"],
)
async def test_結束行缺統計或耗時為_0_仍照原樣傳回_算完成(bridge: Bridge, done_line: dict[str, Any]) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你"), done_line]))

    # Act
    async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
        status = response.status_code
        lines = [json.loads(line) async for line in response.aiter_lines()]

    # Assert
    assert status == 200
    assert len(lines) == 2
    assert lines[-1] == done_line
    assert all("error" not in line for line in lines)


# ---- 004 US2-API-04


async def test_思考過程的行與空字串的行原樣傳回(bridge: Bridge) -> None:
    # Arrange
    await bridge.ready()
    t1 = {**chunk(""), "message": {"role": "assistant", "content": "", "thinking": "想一"}}
    t2 = {**chunk(""), "message": {"role": "assistant", "content": "", "thinking": "想二"}}
    bridge.server.add("POST", "/api/chat", NdjsonReply([t1, t2, chunk("答"), DONE]))

    # Act
    async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
        lines = [json.loads(line) async for line in response.aiter_lines()]

    # Assert
    assert lines == [t1, t2, chunk("答"), DONE]
    assert all("error" not in line for line in lines)


# ---- 004 US2-API-05


async def test_半行與切在多位元組字元中間的段落等到換行才判讀(bridge: Bridge) -> None:
    # Arrange:把 chunk("你好") 從「你」的第 2 個位元組切成兩段,中間夾一道閘門
    await bridge.ready()
    raw = json.dumps(chunk("你好"), ensure_ascii=False).encode() + b"\n"
    cut = raw.index("你".encode()) + 1
    gate = Gate()
    bridge.server.add("POST", "/api/chat", NdjsonReply([raw[:cut], gate, raw[cut:], DONE]))

    async def release_later() -> None:
        await asyncio.sleep(0.05)
        gate.release()

    # Act
    releasing = asyncio.create_task(release_later())
    async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
        lines = [json.loads(line) async for line in response.aiter_lines()]
    await releasing

    # Assert
    assert lines == [chunk("你好"), DONE]
    assert all("error" not in line for line in lines)


# ---- 004 US2-API-06


async def test_用戶端斷開後關上游_不留錯誤也不觸發健康檢查(
    make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts, caplog: pytest.LogCaptureFixture
) -> None:
    # Arrange:排程的健康檢查拉長到測試期間不會發生,看得出是不是轉送觸發的;用量要有替身,否則背景讀用量的錯誤會混進日誌
    fakes.colab.get_usage.returns({"balance": 50.0, "ratePerHour": 1.15, "activeAssignments": 1, "readAt": "2026-11-09T09:00:00Z"})
    servers = start_live_servers(make_app(timeouts=replace(test_timeouts, health_interval=60.0)))
    async with connect(servers, fakes) as bridge:
        await bridge.ready()
        caplog.set_level(logging.DEBUG)
        gate = Gate()
        bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你"), gate, chunk("好"), DONE]))
        checks_before = bridge.fakes.tunnel.check_health.call_count

        # Act:讀到第 1 行後關閉回應(用戶端斷開),量替身多久發現被關了;之後放行、等一下再收尾
        try:
            async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
                lines = response.aiter_lines()
                await anext(lines)
            closed_seen = await wait_for(lambda: len(bridge.server.closed_requests("POST", "/api/chat")) == 1, timeout=0.3)
        finally:
            gate.release()
        await asyncio.sleep(0.2)
        gc.collect()
        session = (await bridge.ui.get("/api/session")).json()
        checks_after = bridge.fakes.tunnel.check_health.call_count

    # Assert
    assert closed_seen, "用戶端斷開後 0.3 秒內,替身沒有發現對話請求被關掉(上游沒有關)"
    assert "Task exception was never retrieved" not in caplog.text
    assert [r for r in caplog.records if r.name.startswith("cgb") and r.levelno >= logging.WARNING] == []
    assert checks_after == checks_before
    assert session["state"] == "ready"
    assert session["idle"]["activeRequests"] == 0


# ---- 004 US2-API-07

JSON_HEADERS = {"Content-Type": "application/json"}


async def post_raw(bridge: Bridge, content: bytes) -> tuple[int, Any]:
    """送出原始位元組;後端崩潰、連線被直接切斷時回 (0, None),讓斷言(而不是例外)指出沒有照合約回 400。"""
    try:
        # 每次用新的連線:後端崩潰切斷連線時,不讓壞掉的連線留在 `bridge.ui` 的連線池裡拖累後面的請求
        async with httpx.AsyncClient(base_url=bridge.ui.base_url, timeout=5.0) as client:
            response = await client.post("/api/chat", content=content, headers=JSON_HEADERS)
    except httpx.TransportError:
        return 0, None
    return response.status_code, response.json().get("code") if response.headers.get("content-type", "").startswith("application/json") else None


async def post_full(bridge: Bridge, body: Any) -> tuple[int, dict[str, Any], str]:
    """送出 JSON 本文,回 (狀態碼, 解析後的錯誤本文, 原文);非 JSON 的本文解析成 {}、連線被切斷時狀態碼是 0。"""
    try:
        async with httpx.AsyncClient(base_url=bridge.ui.base_url, timeout=5.0) as client:
            response = await client.post("/api/chat", json=body)
    except httpx.TransportError:
        return 0, {}, ""
    is_json = response.headers.get("content-type", "").startswith("application/json")
    return response.status_code, response.json() if is_json else {}, response.text


async def test_本文不是合法_JSON_或不是物件時回_400_不轉送(bridge: Bridge) -> None:
    # Arrange:替身若收到請求就一直不回;情況 B 先做(沒有工作階段),再開到就緒做情況 A
    bridge.server.add("POST", "/api/chat", HangReply())

    # Act
    no_session = await post_raw(bridge, b'{"model":')
    await bridge.ready()
    not_json = await post_raw(bridge, b'{"model":')
    not_object = await post_raw(bridge, b"[1, 2]")

    # Assert
    assert [not_json, not_object, no_session] == [(400, "INVALID_REQUEST_BODY")] * 3
    assert bridge.server.requests_to("POST", "/api/chat") == []


# ---- 004 US2-API-08


async def test_model_缺少或名稱格式不對時回_400_不轉送(bridge: Bridge) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("x"), DONE]))
    valid_name = "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
    messages = [{"role": "user", "content": "你好"}]
    bodies = [
        {"messages": messages},  # A 缺少
        {"model": 123, "messages": messages},  # B 不是字串
        {"model": "Qwen2.5", "messages": messages},  # C 官方名稱有大寫
        {"model": "huggingface.co/bartowski/x", "messages": messages},  # D
        {"model": "bartowski/x", "messages": messages},  # E 社群名稱
        {"model": valid_name, "messages": messages},  # 對照組 F
    ]

    # Act
    results = [await post_raw(bridge, json.dumps(body).encode()) for body in bodies]

    # Assert
    assert results[:5] == [(400, "INVALID_MODEL_NAME")] * 5
    assert results[5][0] == 200
    received = bridge.server.requests_to("POST", "/api/chat")
    assert [r.json()["model"] for r in received] == [valid_name]


# ---- 004 US2-API-09


async def test_messages_缺少_不是陣列或是空的時回_400_不轉送(bridge: Bridge) -> None:
    # Arrange:替身若收到請求就一直不回
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", HangReply())
    bodies = [
        {"model": MODEL},  # A 缺少
        {"model": MODEL, "messages": "你好"},  # B 不是陣列
        {"model": MODEL, "messages": []},  # C 空陣列
    ]

    # Act
    results = [await post_raw(bridge, json.dumps(body).encode()) for body in bodies]

    # Assert
    assert results == [(400, "EMPTY_CHAT_MESSAGES")] * 3
    assert bridge.server.requests_to("POST", "/api/chat") == []


# ---- 004 US2-API-10


async def test_messages_裡有不合法的一則時回_400_不轉送(bridge: Bridge) -> None:
    # Arrange:每一輪都是一則合法的 user 訊息加上一則不合法的(放在中間,看是不是每一則都檢查);替身若收到請求就一直不回
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", HangReply())
    valid = {"role": "user", "content": "你好"}
    broken = [
        "hi",  # A 不是物件
        {"role": "system", "content": "x"},  # B
        {"content": "x"},  # C 缺 role
        {"role": "user", "content": 1},  # D
        {"role": "user"},  # E 缺 content
    ]

    # Act
    results = [await post_raw(bridge, json.dumps({"model": MODEL, "messages": [valid, item, valid]}).encode()) for item in broken]

    # Assert
    assert results == [(400, "INVALID_CHAT_MESSAGE")] * 5
    assert bridge.server.requests_to("POST", "/api/chat") == []


# ---- 004 US2-API-11


async def enter_none(bridge: Bridge) -> None:
    """A:沒有開工作階段。"""


async def enter_ended(bridge: Bridge) -> None:
    """D:使用者結束之後。"""
    await bridge.ready()
    await bridge.ui.delete("/api/session")
    await wait_for_state(bridge.ui, "ended")


@pytest.mark.parametrize("enter", [enter_none, enter_opening, enter_reconnecting, enter_ended], ids=["沒有工作階段", "開啟中", "重連中", "使用者結束之後"])
async def test_工作階段不是就緒時回_503_不轉送(bridge: Bridge, enter: Any) -> None:
    # Arrange:替身若收到請求就一直不回
    bridge.server.add("POST", "/api/chat", HangReply())
    gate = await enter(bridge)

    # Act
    try:
        result = await post_raw(bridge, json.dumps(CHAT_BODY).encode())
    finally:
        if gate is not None:
            gate.release()

    # Assert
    assert result == (503, "NO_READY_SESSION")
    assert bridge.server.requests_to("POST", "/api/chat") == []


# ---- 004 US2-API-12


async def point_to_closed_port(bridge: Bridge) -> int:
    """A:轉發位址的 port 沒有在聽。"""
    port = closed_port()
    opened = bridge.world._open_tunnel
    bridge.fakes.tunnel.open_tunnel.side_effect(lambda *a, **k: {**opened(*a, **k), "baseUrl": f"http://127.0.0.1:{port}"})
    return port


async def reply_disconnect(bridge: Bridge) -> int:
    """B:替身讀完請求就斷線,不回任何位元組。"""
    bridge.server.add("POST", "/api/chat", DisconnectReply())
    return bridge.server.port


@pytest.mark.parametrize("arrange", [point_to_closed_port, reply_disconnect], ids=["連不上轉發位址", "遠端沒回就斷線"])
async def test_串流開始前連不到遠端時回_502_中文說明不含轉發位址(bridge: Bridge, arrange: Any) -> None:
    # Arrange
    port = await arrange(bridge)
    await bridge.ready()

    # Act
    status, error, text = await post_full(bridge, CHAT_BODY)

    # Assert
    assert (status, error.get("code")) == (502, "OLLAMA_UNREACHABLE")
    assert has_cjk(error.get("message", ""))
    assert "127.0.0.1" not in text and str(port) not in text


# ---- 004 US2-API-13


@pytest.mark.parametrize(
    ("remote_status", "remote_error", "expected_status", "expected_code", "english"),
    [
        (400, "invalid message format", 502, "OLLAMA_BAD_REQUEST", "invalid"),
        (404, "model 'qwen2.5:0.5b' not found", 404, "OLLAMA_NOT_FOUND", "not found"),
        (500, "model requires more system memory", 502, "OLLAMA_SERVER_ERROR", "memory"),
    ],
    ids=["遠端回 400", "遠端回 404", "遠端回 500"],
)
async def test_遠端在串流開始前回_400_404_500_時換成對應的代碼與中文說明(
    bridge: Bridge, remote_status: int, remote_error: str, expected_status: int, expected_code: str, english: str
) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", JsonReply({"error": remote_error}, status=remote_status))

    # Act
    status, error, text = await post_full(bridge, CHAT_BODY)

    # Assert
    assert (status, error.get("code")) == (expected_status, expected_code)
    assert has_cjk(error.get("message", ""))
    assert english not in text


# ---- 004 US2-API-14


@pytest.mark.parametrize(
    "reply",
    [
        JsonReply({}, status=302, headers={"Location": "/api/other"}),
        JsonReply({"error": "x"}, status=503),
        JsonReply({"message": {"content": "hi"}, "done": True}),
    ],
    ids=["302 導向", "503", "200 但不是 NDJSON"],
)
async def test_遠端回其他狀態碼或不是_NDJSON_時回_502_不跟著導向(bridge: Bridge, reply: JsonReply) -> None:
    # Arrange:導向的目標也有劇本,收到請求就看得出有沒有被跟著走
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", reply)
    bridge.server.add("GET", "/api/other", JsonReply({}))
    bridge.server.add("POST", "/api/other", JsonReply({}))

    # Act
    status, error, _ = await post_full(bridge, CHAT_BODY)

    # Assert
    assert (status, error.get("code")) == (502, "OLLAMA_BAD_RESPONSE")
    assert bridge.server.requests_to("GET", "/api/other") + bridge.server.requests_to("POST", "/api/other") == []


# ---- 004 US2-API-15


@asynccontextmanager
async def timed_bridge(make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts, **timeouts: float) -> AsyncIterator[Bridge]:
    """注入逾時的後端(Q38、Q44):排程的健康檢查拉長到 60 秒,看得出是不是轉送觸發的;`timeouts` 覆寫其他時限。"""
    fakes.colab.get_usage.returns({"balance": 50.0, "ratePerHour": 1.15, "activeAssignments": 1, "readAt": "2026-11-09T09:00:00Z"})
    servers = start_live_servers(make_app(timeouts=replace(test_timeouts, **{"health_interval": 60.0, **timeouts})))
    async with connect(servers, fakes) as bridge:
        yield bridge


async def test_收到回應標頭之前逾時回_504_OLLAMA_TIMEOUT(make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts) -> None:
    # Arrange:替身收到請求後不回應標頭
    async with timed_bridge(make_app, start_live_servers, fakes, test_timeouts, chat_read=0.2) as bridge:
        await bridge.ready()
        bridge.server.add("POST", "/api/chat", HangReply())

        # Act
        started = time.monotonic()
        status, error, _ = await post_full(bridge, CHAT_BODY)
        elapsed = time.monotonic() - started

    # Assert
    assert 0.2 <= elapsed <= 0.6, elapsed
    assert (status, error.get("code")) == (504, "OLLAMA_TIMEOUT")


# ---- 004 US2-API-16


def failure_code(line: dict[str, Any]) -> Any:
    """`ChatStreamFailure` 的 `error.code`;不是 `ChatStreamFailure`(沒有 `error`,或 `error` 是遠端的英文字串)時回 None。"""
    error = line.get("error")
    return error.get("code") if isinstance(error, dict) else None


async def read_lines(bridge: Bridge, body: Any = CHAT_BODY) -> tuple[int, list[dict[str, Any]], list[float]]:
    """送出並讀完;回 (狀態碼, 收到的每一行, 每一行到達的時間)。讀不完(連線被切斷)時回已讀到的。"""
    lines: list[dict[str, Any]] = []
    arrivals: list[float] = []
    status = 0
    try:
        async with bridge.ui.stream("POST", "/api/chat", json=body) as response:
            status = response.status_code
            async for line in response.aiter_lines():
                lines.append(json.loads(line))
                arrivals.append(time.monotonic())
    except httpx.TransportError:
        pass
    return status, lines, arrivals


async def test_兩段之間逾時時最後一行是_OLLAMA_TIMEOUT(make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts) -> None:
    # Arrange:替身送 1 行後不結束也不斷線
    async with timed_bridge(make_app, start_live_servers, fakes, test_timeouts, chat_read=0.2) as bridge:
        await bridge.ready()
        bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你")], then="hang"))

        # Act
        status, lines, arrivals = await read_lines(bridge)

    # Assert
    assert status == 200
    assert len(lines) == 2 and lines[0] == chunk("你"), lines
    assert failure_code(lines[-1]) == "OLLAMA_TIMEOUT", lines
    assert 0.2 <= arrivals[1] - arrivals[0] <= 0.6, arrivals


# ---- 004 US2-API-17


@pytest.mark.parametrize("then", ["disconnect", "end"], ids=["遠端中途斷線", "遠端正常結束但沒有 done"])
async def test_done_之前斷線或結束時最後一行是_OLLAMA_STREAM_INTERRUPTED(
    make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts, then: Any
) -> None:
    # Arrange
    async with timed_bridge(make_app, start_live_servers, fakes, test_timeouts) as bridge:
        await bridge.ready()
        bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你")], then=then))

        # Act
        _, lines, _ = await read_lines(bridge)

    # Assert
    assert len(lines) == 2 and lines[0] == chunk("你"), lines
    assert failure_code(lines[-1]) == "OLLAMA_STREAM_INTERRUPTED", lines
    assert has_cjk(lines[-1]["error"]["message"])


# ---- 004 US2-API-18


async def test_遠端送_error_行時換成_OLLAMA_SERVER_ERROR_並結束(bridge: Bridge) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你"), {"error": "CUDA error: out of memory"}, chunk("不該出現")]))

    # Act
    status, lines, _ = await read_lines(bridge)

    # Assert
    assert status == 200
    assert len(lines) == 2 and lines[0] == chunk("你"), lines
    assert failure_code(lines[-1]) == "OLLAMA_SERVER_ERROR", lines
    assert [line for line in lines if isinstance(line.get("error"), str)] == []
    assert "CUDA" not in lines[-1]["error"]["message"]


# ---- 004 US2-API-19

BAD_LINES = [
    b"not json\n",
    b"[1]\n",
    {"model": MODEL, "message": {"role": "assistant", "content": "x"}, "done": "yes"},
    {"model": MODEL, "message": {"role": "assistant", "content": 1}, "done": False},
]


@pytest.mark.parametrize("bad", BAD_LINES, ids=["不是 JSON", "不是物件", "done 不是布林", "content 不是字串"])
async def test_某一行不是_JSON_物件或欄位型別不符時最後一行是_OLLAMA_BAD_RESPONSE(bridge: Bridge, bad: Any) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你"), bad, chunk("不該出現"), DONE]))

    # Act
    status, lines, _ = await read_lines(bridge)

    # Assert
    assert status == 200
    assert len(lines) == 2 and lines[0] == chunk("你"), lines
    assert failure_code(lines[-1]) == "OLLAMA_BAD_RESPONSE", lines


# ---- 004 US2-API-20


async def end_by_delete(bridge: Bridge) -> None:
    await bridge.ui.delete("/api/session")


async def end_by_restart(bridge: Bridge) -> None:
    bridge.fakes.remote_ollama.list_local_models.returns({"models": []})
    await bridge.ui.post("/api/session/restart", json={"runtimeType": {"gpu": "L4", "highMem": False}})


async def end_by_lost(bridge: Bridge) -> None:
    bridge.fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
    bridge.fakes.tunnel.open_tunnel.raises("TUNNEL_UNREACHABLE", "連不到")


@pytest.mark.parametrize("end", [end_by_delete, end_by_restart, end_by_lost], ids=["使用者結束", "變更類型", "判定失聯"])
async def test_回覆途中工作階段結束_變更類型或失聯時最後一行是_SESSION_ENDED(
    make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts, end: Any
) -> None:
    # Arrange:只有判定失聯會觸發健康檢查;區網程式另有一個進行中的 /api/generate 串流(失聯時照 001 不補行)
    health = {"health_interval": 0.05, "reconnect_limit": 0.3, "reconnect_backoff": (0.0,), "reconnect_interval": 0.1}
    async with timed_bridge(make_app, start_live_servers, fakes, test_timeouts, **health) as bridge:
        await bridge.ready()
        compat_release = Gate()
        compat_lines: list[bytes] = []
        bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你")], then="hang"))
        bridge.server.add(
            "POST",
            "/api/generate",
            NdjsonReply([{"model": MODEL, "response": "你", "done": False}], then="hang", release=compat_release),
        )

        async def read_compat() -> None:
            try:
                async with bridge.ollama.stream("POST", "/api/generate", json={"model": MODEL, "prompt": "你好"}) as response:
                    async for line in response.aiter_lines():
                        compat_lines.append(line.encode())
            except httpx.TransportError:
                pass

        compat = asyncio.create_task(read_compat())
        await wait_for(lambda: len(compat_lines) >= 1, timeout=2.0)

        # Act:讀到對話的第 1 行後結束
        chat_lines: list[dict[str, Any]] = []
        arrivals: list[float] = []

        async def read_chat() -> None:
            async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
                async for line in response.aiter_lines():
                    chat_lines.append(json.loads(line))
                    arrivals.append(time.monotonic())

        chat = asyncio.create_task(read_chat())
        try:
            await wait_for(lambda: len(chat_lines) >= 1, timeout=2.0)
            ended_at = time.monotonic()
            await end(bridge)
            lost_at = None
            if end is end_by_lost:
                await wait_for_state(bridge.ui, "lost", timeout=3.0)
                lost_at = time.monotonic()
            await asyncio.wait({chat}, timeout=1.0)
            models = await bridge.ui.get("/api/models") if end is end_by_delete else None
            lines_before = len(compat_lines)
            await asyncio.sleep(0.3)
        finally:
            compat_release.release()
            chat.cancel()
            await asyncio.gather(chat, compat, return_exceptions=True)

    # Assert
    assert chat_lines[:1] == [chunk("你")], chat_lines
    assert len(chat_lines) == 2 and failure_code(chat_lines[-1]) == "SESSION_ENDED", chat_lines
    reference = lost_at if lost_at is not None else ended_at
    assert arrivals[-1] - reference <= 0.3, arrivals[-1] - reference
    if models is not None:
        assert (models.status_code, models.json().get("code")) == (503, "NO_READY_SESSION")
    if end is end_by_lost:
        assert len(compat_lines) == lines_before == 1, compat_lines


# ---- 004 US2-API-21


async def test_對話串流進行中不計閒置_結束後才重設倒數並推送(bridge: Bridge, fake_clock: Any) -> None:
    # Arrange:閒置時限 1 分鐘;已訂閱 SSE;替身的第 1 行之前與第 2 行之前各等測試放行
    from datetime import timedelta

    from cgb.domain.session_state import parse_iso
    from integration.test_api_events import sse_events
    from integration.test_api_idle import set_idle_timeout

    await set_idle_timeout(bridge.ui, 1)
    await bridge.ready()
    g0, g1 = Gate(), Gate()
    bridge.server.add("POST", "/api/chat", NdjsonReply([g0, chunk("你"), g1, DONE]))
    updates: list[dict[str, Any]] = []

    async def subscribe() -> None:
        async with bridge.ui.stream("GET", "/api/events", timeout=30.0) as response:
            async for name, payload in sse_events(response):
                if name == "session.updated":
                    updates.append(payload["session"])

    async def session() -> dict[str, Any]:
        return (await bridge.ui.get("/api/session")).json()

    subscription = asyncio.create_task(subscribe())
    await wait_for(lambda: len(updates) >= 1, timeout=2.0)
    t = fake_clock.now()

    # Act
    chatting = asyncio.create_task(read_lines(bridge))
    try:
        await g0.wait_entered_async()
        during = (await session()).get("idle") or {}
        fake_clock.set(t + timedelta(seconds=90))
        g0.release()
        g1.release()
        await asyncio.wait_for(chatting, 5.0)
        for _ in range(200):
            if ((await session()).get("idle") or {}).get("activeRequests") == 0:
                break
            await asyncio.sleep(0.01)
        ended_at = fake_clock.now()
        after = (await session()).get("idle") or {}
        pushed = await wait_for(lambda: any((u.get("idle") or {}).get("deadline") == after.get("deadline") for u in updates[1:]), timeout=1.0)
    finally:
        g0.release()
        g1.release()
        subscription.cancel()
        await asyncio.gather(subscription, return_exceptions=True)

    # Assert
    assert (during.get("activeRequests"), during.get("deadline")) == (1, None), during
    deadline = parse_iso(after["deadline"])
    assert t + timedelta(seconds=150) <= deadline <= ended_at + timedelta(minutes=1), after
    assert after.get("activeRequests") == 0, after
    assert pushed, updates


# ---- 004 US2-API-22


async def test_檢查不過的請求不重設倒數_通過後失敗也不卡住進行中的請求數(bridge: Bridge, fake_clock: Any) -> None:
    # Arrange:閒置時限 1 分鐘,工作階段就緒於 T
    from datetime import timedelta

    from cgb.domain.session_state import parse_iso
    from integration.test_api_idle import set_idle_timeout

    await set_idle_timeout(bridge.ui, 1)
    t = parse_iso((await bridge.ready())["readyAt"])

    async def idle() -> dict[str, Any]:
        return ((await bridge.ui.get("/api/session")).json()).get("idle") or {}

    # Act:A 檢查不過(400);B 串流開始前失敗(502);C 串流中途斷線
    fake_clock.set(t + timedelta(seconds=20))
    before_a = await idle()
    await post_full(bridge, {"model": MODEL, "messages": []})
    after_a = await idle()
    fake_clock.set(t + timedelta(seconds=40))
    bridge.server.add("POST", "/api/chat", JsonReply({"error": "x"}, status=500), times=1)
    await post_full(bridge, CHAT_BODY)
    after_b = await idle()
    fake_clock.set(t + timedelta(seconds=50))
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你")], then="disconnect"), times=1)
    await read_lines(bridge)
    after_c = await idle()

    # Assert
    assert after_a["lastRequestAt"] == before_a["lastRequestAt"], (before_a, after_a)
    assert abs((parse_iso(after_b["lastRequestAt"]) - (t + timedelta(seconds=40))).total_seconds()) < 1.0, after_b
    assert after_b["activeRequests"] == 0, after_b
    assert after_c["activeRequests"] == 0, after_c


# ---- 004 US2-API-23


async def test_對話頁與區網程式同時用同一個模型時互不排隊(bridge: Bridge) -> None:
    # Arrange:替身先後加兩條 /api/chat 劇本(各用一次),共用同一道閘門
    await bridge.ready()
    g = Gate()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("一"), g, DONE]), times=1)
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("二"), g, DONE]), times=1)
    ui_lines: list[dict[str, Any]] = []
    lan_lines: list[dict[str, Any]] = []
    statuses: dict[str, int] = {}

    async def read_ui() -> None:
        async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
            statuses["ui"] = response.status_code
            async for line in response.aiter_lines():
                ui_lines.append(json.loads(line))

    async def read_lan() -> None:
        async with bridge.ollama.stream("POST", "/api/chat", json=CHAT_BODY) as response:
            statuses["lan"] = response.status_code
            async for line in response.aiter_lines():
                lan_lines.append(json.loads(line))

    # Act:對話頁先送,讀到第 1 行後區網程式再送;兩邊都讀到第 1 行後放行
    ui = asyncio.create_task(read_ui())
    try:
        await wait_for(lambda: len(ui_lines) >= 1, timeout=2.0)
        lan = asyncio.create_task(read_lan())
        both_started = await wait_for(lambda: len(lan_lines) >= 1, timeout=2.0)
        requests_before_release = len(bridge.server.requests_to("POST", "/api/chat"))
    finally:
        g.release()
    await asyncio.wait_for(asyncio.gather(ui, lan), 5.0)

    # Assert
    assert both_started, "區網程式的請求被對話頁的串流擋住(排隊或被拒)"
    assert requests_before_release == 2
    assert statuses == {"ui": 200, "lan": 200}
    assert ui_lines[-1].get("done") is True and lan_lines[-1].get("done") is True


# ---- 004 US2-API-24


async def test_模型沒載入時不先預先載入_載入時間算在第一段之前(bridge: Bridge) -> None:
    # Arrange:模型在執行環境上、還沒載入;替身的第一段之前等測試放行(代表載入的時間)
    set_tags(bridge.fakes, tag(MODEL, 397_821_319))
    set_loaded(bridge.fakes)
    await bridge.ready()
    catalog = (await bridge.ui.get("/api/models")).json()
    loaded_before = [m["loaded"] for m in catalog["items"] if m["name"] == MODEL]
    g = Gate()
    bridge.server.add("POST", "/api/chat", NdjsonReply([g, chunk("你"), DONE]))
    bridge.fakes.remote_ollama.preload.reset_calls()

    async def release_later() -> None:
        await asyncio.sleep(0.1)
        g.release()

    # Act
    releasing = asyncio.create_task(release_later())
    status, lines, _ = await read_lines(bridge)
    await releasing

    # Assert
    assert loaded_before == [False]
    assert status == 200
    assert lines == [chunk("你"), DONE]
    assert len(bridge.server.requests_to("POST", "/api/chat")) == 1
    assert bridge.fakes.remote_ollama.preload.call_count == 0
    assert bridge.server.requests_to("POST", "/api/generate") == []


# ---- 004 US2-API-25


async def test_每一段在遠端送出後立刻傳到_不緩衝(bridge: Bridge) -> None:
    # Arrange:替身每一行之前各等一道閘門(共 11 道),看每一行是不是在放行下一道之前就已經讀到
    await bridge.ready()
    gates = [Gate() for _ in range(11)]
    items: list[Any] = []
    for i in range(10):
        items += [gates[i], chunk(str(i))]
    items += [gates[10], DONE]
    bridge.server.add("POST", "/api/chat", NdjsonReply(items))
    lines: list[dict[str, Any]] = []

    async def consume() -> None:
        async with bridge.ui.stream("POST", "/api/chat", json=CHAT_BODY) as response:
            async for line in response.aiter_lines():
                lines.append(json.loads(line))

    # Act
    reading = asyncio.create_task(consume())
    early: list[bool] = []
    try:
        await gates[0].wait_entered_async()
        gates[0].release()
        started = time.monotonic()
        first_quick = await wait_for(lambda: len(lines) >= 1, timeout=0.2)
        first_delay = time.monotonic() - started
        for i in range(10):
            await wait_for(lambda i=i: len(lines) >= i + 1, timeout=1.0)
            await asyncio.sleep(0.02)
            early.append(len(lines) >= i + 1)
            gates[i + 1].release()
    finally:
        for gate in gates:
            gate.release()
    await asyncio.wait({reading}, timeout=5.0)  # 讀不完時以下面的斷言指出,不在這裡拋例外
    reading.cancel()
    await asyncio.gather(reading, return_exceptions=True)

    # Assert
    assert first_quick, first_delay
    assert early == [True] * 10
    assert len(lines) == 11 and lines[-1] == DONE


# ---- 004 US2-API-26

USER_MARK = "cgb-test-使用者訊息-不該留下"
REPLY_MARK = "cgb-test-模型回覆-不該留下"


async def test_對話內容不寫進日誌與資料庫(bridge: Bridge, caplog: pytest.LogCaptureFixture, db_path: Any) -> None:
    # Arrange:根 logger 設到 DEBUG(含 httpx、httpcore、uvicorn、asyncio);替身依序回三種結果
    import sqlite3
    from pathlib import Path

    await bridge.ready()
    caplog.set_level(logging.DEBUG)
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk(REPLY_MARK), DONE]), times=1)
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk(REPLY_MARK), {"error": REPLY_MARK}]), times=1)
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk(REPLY_MARK)], then="disconnect"), times=1)
    messages = [
        {"role": "user", "content": USER_MARK},
        {"role": "assistant", "content": REPLY_MARK},
        {"role": "user", "content": USER_MARK},
    ]
    responses: list[str] = []

    # Act:三次串流讀完,再送一次第二則是 system 的(400)
    for _ in range(3):
        async with bridge.ui.stream("POST", "/api/chat", json={"model": MODEL, "messages": messages}) as response:
            try:
                responses.append("".join([line async for line in response.aiter_lines()]))
            except httpx.TransportError:
                responses.append("")
    rejected = await bridge.ui.post("/api/chat", json={"model": MODEL, "messages": [messages[0], {"role": "system", "content": USER_MARK}]})
    responses.append(rejected.text)
    await asyncio.sleep(0.2)

    # Assert
    assert rejected.status_code == 400
    assert USER_MARK not in caplog.text
    assert REPLY_MARK not in caplog.text
    stored = ""
    with sqlite3.connect(db_path) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            stored += repr(conn.execute(f'SELECT * FROM "{table}"').fetchall())
    assert USER_MARK not in stored and REPLY_MARK not in stored
    for suffix in ("", "-wal", "-journal"):
        path = Path(str(db_path) + suffix)
        raw = path.read_bytes() if path.exists() else b""
        assert USER_MARK.encode() not in raw and REPLY_MARK.encode() not in raw, suffix
    assert all(USER_MARK not in text for text in responses)


# ---- 004 US2-API-27

ERROR_CODES = {
    400: {"INVALID_REQUEST_BODY", "INVALID_MODEL_NAME", "EMPTY_CHAT_MESSAGES", "INVALID_CHAT_MESSAGE"},
    404: {"OLLAMA_NOT_FOUND"},
    502: {"OLLAMA_UNREACHABLE", "OLLAMA_BAD_REQUEST", "OLLAMA_SERVER_ERROR", "OLLAMA_BAD_RESPONSE"},
    503: {"NO_READY_SESSION"},
    504: {"OLLAMA_TIMEOUT"},
}
STREAM_CODES = {"OLLAMA_TIMEOUT", "OLLAMA_STREAM_INTERRUPTED", "OLLAMA_SERVER_ERROR", "OLLAMA_BAD_RESPONSE", "SESSION_ENDED"}
USER_MESSAGE = {"role": "user", "content": "你好"}


def raw(body: Any) -> bytes:
    return json.dumps(body).encode()


def with_messages(*extra: Any) -> bytes:
    return raw({"model": MODEL, "messages": [USER_MESSAGE, *extra]})


def ready_with(reply: Any) -> Any:
    async def prepare(bridge: Bridge) -> None:
        await bridge.ready()
        bridge.server.add("POST", "/api/chat", reply)

    return prepare


async def prepare_hang(bridge: Bridge) -> None:
    await ready_with(HangReply())(bridge)


async def prepare_no_session(bridge: Bridge) -> None:
    bridge.server.add("POST", "/api/chat", HangReply())


async def prepare_closed_port(bridge: Bridge) -> None:
    await point_to_closed_port(bridge)
    await bridge.ready()


async def prepare_opening(bridge: Bridge) -> None:
    bridge.server.add("POST", "/api/chat", HangReply())
    bridge.gate = await enter_opening(bridge)  # type: ignore[attr-defined]


async def prepare_reconnecting(bridge: Bridge) -> None:
    bridge.server.add("POST", "/api/chat", HangReply())
    bridge.gate = await enter_reconnecting(bridge)  # type: ignore[attr-defined]


async def prepare_ended(bridge: Bridge) -> None:
    bridge.server.add("POST", "/api/chat", HangReply())
    await enter_ended(bridge)


def json_status(status: int, body: Any = None, headers: dict[str, str] | None = None) -> Any:
    return ready_with(JsonReply({"error": "x"} if body is None else body, status=status, headers=headers or {}))


def stream_of(*lines: Any, then: Any = "end") -> Any:
    return ready_with(NdjsonReply([chunk("你"), *lines] if lines else [chunk("你")], then=then))


# (id, 準備, 送出的本文);id 前面是案例編號
FAILURE_CASES: list[tuple[str, Any, bytes]] = [
    # 400:16 組
    ("07-不是合法JSON", prepare_hang, b'{"model":'),
    ("07-不是物件", prepare_hang, b"[1, 2]"),
    ("07-沒有工作階段", prepare_no_session, b'{"model":'),
    ("08-缺model", prepare_hang, raw({"messages": [USER_MESSAGE]})),
    ("08-model不是字串", prepare_hang, raw({"model": 123, "messages": [USER_MESSAGE]})),
    ("08-官方名稱有大寫", prepare_hang, raw({"model": "Qwen2.5", "messages": [USER_MESSAGE]})),
    ("08-huggingface.co", prepare_hang, raw({"model": "huggingface.co/bartowski/x", "messages": [USER_MESSAGE]})),
    ("08-社群名稱", prepare_hang, raw({"model": "bartowski/x", "messages": [USER_MESSAGE]})),
    ("09-缺messages", prepare_hang, raw({"model": MODEL})),
    ("09-messages是字串", prepare_hang, raw({"model": MODEL, "messages": "你好"})),
    ("09-messages是空陣列", prepare_hang, raw({"model": MODEL, "messages": []})),
    ("10-元素是字串", prepare_hang, with_messages("hi")),
    ("10-system", prepare_hang, with_messages({"role": "system", "content": "x"})),
    ("10-缺role", prepare_hang, with_messages({"content": "x"})),
    ("10-content不是字串", prepare_hang, with_messages({"role": "user", "content": 1})),
    ("10-缺content", prepare_hang, with_messages({"role": "user"})),
    # 503:4 組
    ("11-沒有工作階段", prepare_no_session, raw(CHAT_BODY)),
    ("11-開啟中", prepare_opening, raw(CHAT_BODY)),
    ("11-重連中", prepare_reconnecting, raw(CHAT_BODY)),
    ("11-使用者結束之後", prepare_ended, raw(CHAT_BODY)),
    # 串流開始之前:9 組
    ("12-連不上轉發位址", prepare_closed_port, raw(CHAT_BODY)),
    ("12-遠端沒回就斷線", ready_with(DisconnectReply()), raw(CHAT_BODY)),
    ("13-遠端400", json_status(400), raw(CHAT_BODY)),
    ("13-遠端404", json_status(404), raw(CHAT_BODY)),
    ("13-遠端500", json_status(500), raw(CHAT_BODY)),
    ("14-302", ready_with(JsonReply({}, status=302, headers={"Location": "/api/other"})), raw(CHAT_BODY)),
    ("14-503", json_status(503), raw(CHAT_BODY)),
    ("14-200不是NDJSON", ready_with(JsonReply({"message": {"content": "hi"}, "done": True})), raw(CHAT_BODY)),
    ("15-標頭之前逾時", prepare_hang, raw(CHAT_BODY)),
    # 串流中:8 組
    ("16-兩段之間逾時", stream_of(then="hang"), raw(CHAT_BODY)),
    ("17-中途斷線", stream_of(then="disconnect"), raw(CHAT_BODY)),
    ("17-沒有done就結束", stream_of(), raw(CHAT_BODY)),
    ("18-error行", stream_of({"error": "CUDA error: out of memory"}, chunk("不該出現")), raw(CHAT_BODY)),
    ("19-不是JSON", stream_of(b"not json\n", chunk("不該出現"), DONE), raw(CHAT_BODY)),
    ("19-不是物件", stream_of(b"[1]\n", chunk("不該出現"), DONE), raw(CHAT_BODY)),
    ("19-done不是布林", stream_of({"model": MODEL, "message": {"role": "assistant", "content": "x"}, "done": "yes"}, DONE), raw(CHAT_BODY)),
    ("19-content不是字串", stream_of({"model": MODEL, "message": {"role": "assistant", "content": 1}, "done": False}, DONE), raw(CHAT_BODY)),
]


@pytest.mark.parametrize(("prepare", "content"), [pytest.param(p, c, id=i) for i, p, c in FAILURE_CASES])
async def test_每一種失敗都照合約回應_沒有_500_也沒有沒有最後一行的串流(
    make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts, prepare: Any, content: bytes
) -> None:
    # Arrange:每組各自一個暫存 SQLite、替身與後端;`chat_read` 注入同 US2-API-15(重連中那組要靠排程的健康檢查進入,所以健康檢查沿用測試的 0.2 秒)
    async with timed_bridge(make_app, start_live_servers, fakes, test_timeouts, chat_read=0.2, health_interval=test_timeouts.health_interval) as bridge:
        await prepare(bridge)
        status, lines, text = 0, [], ""
        try:
            # Act
            async with httpx.AsyncClient(base_url=bridge.ui.base_url, timeout=5.0) as client:
                async with client.stream("POST", "/api/chat", content=content, headers=JSON_HEADERS) as response:
                    status = response.status_code
                    ctype = response.headers.get("content-type", "")
                    text = (await response.aread()).decode()
                    lines = [json.loads(line) for line in text.splitlines() if line] if ctype.startswith("application/x-ndjson") else []
        except httpx.TransportError:
            status = status or 0
        finally:
            if getattr(bridge, "gate", None) is not None:
                bridge.gate.release()  # type: ignore[attr-defined]

    # Assert
    assert status != 500 and status != 0, (status, text)
    if status != 200:
        error = json.loads(text)
        assert error["code"] in ERROR_CODES[status], (status, error)
        assert has_cjk(error["message"])
    else:
        last = lines[-1]
        if failure_code(last) is not None:
            assert failure_code(last) in STREAM_CODES, last
            assert has_cjk(last["error"]["message"])
        else:
            assert last.get("done") is True, last


# ---- 004 US2-API-28


@pytest.mark.parametrize(
    ("prepare", "code", "status"),
    [
        (prepare_closed_port, "OLLAMA_UNREACHABLE", 502),
        (json_status(503), "OLLAMA_BAD_RESPONSE", 502),
        (prepare_hang, "OLLAMA_TIMEOUT", 504),
    ],
    ids=["連不上", "遠端回 503", "標頭之前逾時"],
)
async def test_串流開始前失敗的說明是模型目錄與對話頁都通的說法(
    make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts, prepare: Any, code: str, status: int
) -> None:
    # Arrange
    from cgb.domain.errors import MESSAGES

    async with timed_bridge(make_app, start_live_servers, fakes, test_timeouts, chat_read=0.2) as bridge:
        await prepare(bridge)

        # Act
        got_status, error, _ = await post_full(bridge, CHAT_BODY)

    # Assert
    assert (got_status, error.get("code")) == (status, code)
    assert "無法確認哪些模型已經下載" not in error["message"]
    assert error["message"] == MESSAGES[code]
    if code == "OLLAMA_UNREACHABLE":
        assert "連不到執行環境上的 Ollama" in error["message"]


# ---- 004 US2-API-29


@pytest.mark.parametrize(
    ("content_type", "accepted"),
    [("application/x-ndjson; charset=utf-8", True), ("Application/X-NDJSON", True), (None, False)],
    ids=["帶 charset", "大小寫不同", "沒有 Content-Type"],
)
async def test_Content_Type_只比_media_type_不分大小寫_沒有標頭算壞回應(bridge: Bridge, content_type: str | None, accepted: bool) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk("你"), DONE], headers={"Content-Type": content_type}))

    # Act:各送出一次(被接受的讀串流,不被接受的讀 JSON 錯誤)
    if accepted:
        status, lines, _ = await read_lines(bridge)
    else:
        status, error, _ = await post_full(bridge, CHAT_BODY)

    # Assert
    if accepted:
        assert status == 200
        assert lines == [chunk("你"), DONE]
    else:
        assert (status, error.get("code")) == (502, "OLLAMA_BAD_RESPONSE")
