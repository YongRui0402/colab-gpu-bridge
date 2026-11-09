"""E3 Ollama 相容端點(testplan.md § 3.1;contracts/ollama-compat.openapi.yaml)。

接縫:Ollama 相容端點的 HTTP;工作階段經 UI 的 `/api/session` 開到就緒,五個轉接層用替身,
轉送真的經過 httpx 打到測試行程內的假 Ollama 伺服器(`FakeTunnel.open_tunnel` 回報的 `baseUrl`)。
串流的案例看得出逐段傳回,所以全部用測試行程內的 uvicorn(127.0.0.1 隨機 port,Q97)。
"""

import asyncio
import json
import socket
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.app import Timeouts
from fakes import FakeOllamaServer, Gate, HangReply, JsonReply, NdjsonReply
from integration.test_api_session import ColabWorld, open_ready

MODEL = "qwen2.5:0.5b"


@dataclass
class Bridge:
    """一組跑起來的後端:UI 與 Ollama 相容端點兩個用戶端、替身背後的 Colab 帳號與假 Ollama 伺服器。"""

    ui: httpx.AsyncClient
    ollama: httpx.AsyncClient
    world: ColabWorld
    server: FakeOllamaServer
    fakes: Any

    async def ready(self) -> dict[str, Any]:
        return await open_ready(self.ui)


@asynccontextmanager
async def connect(servers: Any, fakes: Any) -> AsyncIterator[Bridge]:
    world = ColabWorld(fakes)
    async with (
        httpx.AsyncClient(base_url=servers.ui_url, timeout=5.0) as ui,
        httpx.AsyncClient(base_url=servers.ollama_url, timeout=5.0) as ollama,
    ):
        yield Bridge(ui=ui, ollama=ollama, world=world, server=fakes.server, fakes=fakes)


@pytest.fixture
async def bridge(live_servers: Any, fakes: Any) -> AsyncIterator[Bridge]:
    async with connect(live_servers, fakes) as connected:
        yield connected


def ndjson(*items: dict[str, Any]) -> bytes:
    """假伺服器送出的位元組(`tests/fakes/ollama_server.py` 一行一個 `json.dumps`)。"""
    return b"".join((json.dumps(item) + "\n").encode() for item in items)


async def wait_for(predicate: Callable[[], bool], timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            return False
        await asyncio.sleep(0.005)
    return True


# ---------------------------------------------------------------- US2-OC-01


async def test_generate_串流逐段原樣傳回(bridge: Bridge) -> None:
    # Arrange:假伺服器送 3 行 NDJSON,第 2、3 行之前各等測試放行
    await bridge.ready()
    lines = [
        {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "response": "你", "done": False},
        {"model": MODEL, "created_at": "2026-11-09T09:00:01Z", "response": "好", "done": False},
        {"model": MODEL, "created_at": "2026-11-09T09:00:02Z", "response": "", "done": True},
    ]
    before_second, before_third = Gate(), Gate()
    bridge.server.add("POST", "/api/generate", NdjsonReply([lines[0], before_second, lines[1], before_third, lines[2]]))
    received: list[bytes] = []
    meta: dict[str, Any] = {}

    async def consume() -> None:
        async with bridge.ollama.stream("POST", "/api/generate", json={"model": MODEL, "prompt": "你好"}) as response:
            meta["status"] = response.status_code
            meta["content_type"] = response.headers.get("content-type")
            async for chunk in response.aiter_raw():
                received.append(chunk)

    # Act
    reading = asyncio.create_task(consume())
    try:
        first_line_early = await wait_for(lambda: b"\n" in b"".join(received), timeout=2.0)
    finally:
        before_second.release()
        before_third.release()
    await asyncio.wait_for(reading, 5.0)

    # Assert
    assert first_line_early, "放行第 2 行之前,用戶端沒有讀到第 1 行(串流被緩衝成一次傳回)"
    assert b"".join(received) == ndjson(*lines)
    assert meta["status"] == 200
    assert (meta["content_type"] or "").startswith("application/x-ndjson")


# ---------------------------------------------------------------- US2-OC-02


async def test_generate_非串流照轉_query_標頭與本文_不轉_hop_by_hop(bridge: Bridge) -> None:
    # Arrange:假伺服器對 stream:false 回一個 JSON 與標頭 X-Cgb-Test: 1
    await bridge.ready()
    reply = {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "response": "你好!", "done": True}
    bridge.server.add("POST", "/api/generate", JsonReply(reply, headers={"X-Cgb-Test": "1"}), json={"stream": False})
    body = {"model": MODEL, "prompt": "你好", "stream": False}

    # Act
    response = await bridge.ollama.post(
        "/api/generate", params={"x": "1"}, content=json.dumps(body), headers={"Content-Type": "application/json", "Connection": "keep-alive"}
    )

    # Assert
    bridge.server.assert_all_matched()
    received = bridge.server.requests_to("POST", "/api/generate")
    assert len(received) == 1
    assert (response.status_code, response.content) == (200, json.dumps(reply).encode())
    assert response.headers.get("x-cgb-test") == "1"
    assert received[0].query == {"x": ["1"]}
    assert received[0].headers.get("host") == f"127.0.0.1:{bridge.server.port}"
    assert received[0].json() == body
    assert "connection" not in received[0].headers


# ---------------------------------------------------------------- US2-OC-03

PLAIN = {"Content-Type": "text/plain; charset=utf-8"}

# (方法, 路徑, 請求本文, 假伺服器回的本文, 假伺服器回的標頭)
WHITELISTED = [
    ("GET", "/", None, b"Ollama is running", PLAIN),
    ("HEAD", "/", None, b"Ollama is running", PLAIN),
    ("GET", "/api/version", None, {"version": "0.40.15"}, {}),
    ("GET", "/api/tags", None, {"models": []}, {}),
    ("GET", "/api/ps", None, {"models": []}, {}),
    ("POST", "/api/show", {"model": MODEL}, {"modelfile": "FROM qwen2.5:0.5b", "details": {"family": "qwen2"}}, {}),
    (
        "POST",
        "/api/chat",
        {"model": MODEL, "messages": [{"role": "user", "content": "你好"}], "stream": False},
        {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "message": {"role": "assistant", "content": "你好!"}, "done": True},
        {},
    ),
    ("POST", "/api/embed", {"model": MODEL, "input": "你好"}, {"model": MODEL, "embeddings": [[0.1, 0.2]]}, {}),
    ("POST", "/api/embeddings", {"model": MODEL, "prompt": "你好"}, {"embedding": [0.1, 0.2]}, {}),
]


@pytest.mark.parametrize(("method", "path", "body", "reply", "reply_headers"), WHITELISTED, ids=[f"{m} {p}" for m, p, *_ in WHITELISTED])
async def test_白名單的推論與查詢路徑都原樣轉送(
    bridge: Bridge, method: str, path: str, body: Any, reply: Any, reply_headers: dict[str, str]
) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add(method, path, JsonReply(reply, headers=reply_headers))
    content = json.dumps(body).encode() if body is not None else b""
    reply_bytes = reply if isinstance(reply, bytes) else json.dumps(reply).encode()

    # Act
    response = await bridge.ollama.request(method, path, content=content or None)

    # Assert
    bridge.server.assert_all_matched()
    received = bridge.server.requests_to(method, path)
    assert [(r.method, r.path, r.body) for r in received] == [(method, path, content)]
    expected_body = b"" if method == "HEAD" else reply_bytes
    assert (response.status_code, response.content) == (200, expected_body)


# ---------------------------------------------------------------- US2-OC-04

MANAGED = [
    ("POST", "/api/pull", {"model": MODEL}),
    ("POST", "/api/push", {"model": MODEL}),
    ("POST", "/api/create", {"model": "my-model", "from": MODEL}),
    ("POST", "/api/copy", {"source": MODEL, "destination": "my-copy"}),
    ("DELETE", "/api/delete", {"model": MODEL}),
    ("HEAD", "/api/blobs/sha256:00", None),
    ("POST", "/api/blobs/sha256:00", None),
]


def has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


@pytest.mark.parametrize(("method", "path", "body"), MANAGED, ids=[f"{m} {p}" for m, p, _ in MANAGED])
async def test_管理操作一律回_403_請到_UI_不轉送(bridge: Bridge, method: str, path: str, body: Any) -> None:
    # Arrange
    await bridge.ready()

    # Act
    response = await bridge.ollama.request(method, path, content=json.dumps(body).encode() if body is not None else None)

    # Assert
    assert response.status_code == 403
    if method != "HEAD":  # HEAD 的回應沒有本文
        error = response.json().get("error")
        assert isinstance(error, str) and has_cjk(error) and "UI" in error, response.text
    assert bridge.server.requests == []


# ---------------------------------------------------------------- US2-OC-05


async def test_沒有工作階段時管理操作仍回_403_不回_503(bridge: Bridge) -> None:
    # Arrange:沒有工作階段

    # Act
    response = await bridge.ollama.post("/api/pull", json={"model": MODEL})

    # Assert
    assert response.status_code == 403
    assert "UI" in (response.json().get("error") or ""), response.text


# ---------------------------------------------------------------- US2-OC-06


@pytest.mark.parametrize(("method", "path"), [("POST", "/v1/chat/completions"), ("GET", "/api/me")])
async def test_白名單外的路徑回_404_不轉送(bridge: Bridge, method: str, path: str) -> None:
    # Arrange
    await bridge.ready()
    body = {"model": MODEL, "messages": [{"role": "user", "content": "你好"}]} if method == "POST" else None

    # Act
    response = await bridge.ollama.request(method, path, content=json.dumps(body).encode() if body is not None else None)

    # Assert
    assert response.status_code == 404
    error = response.json().get("error") if response.headers.get("content-type", "").startswith("application/json") else None
    assert isinstance(error, str) and has_cjk(error), response.text
    assert bridge.server.requests == []


# ---------------------------------------------------------------- US2-OC-07

NO_READY = "沒有可用的工作階段"


async def timed_request(client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> tuple[httpx.Response | None, float]:
    """送出請求並量花了多久;用戶端逾時(5 秒)時回應是 None。"""
    started = time.monotonic()
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.TimeoutException:
        response = None
    return response, time.monotonic() - started


async def test_沒有工作階段時_1_秒內回_503_不轉送(bridge: Bridge) -> None:
    # Arrange:沒有工作階段;假伺服器若收到請求就一直不回
    bridge.server.add("POST", "/api/generate", HangReply())

    # Act
    response, elapsed = await timed_request(bridge.ollama, "POST", "/api/generate", json={"model": MODEL, "prompt": "你好"})

    # Assert
    assert response is not None and elapsed <= 1.0, elapsed
    assert response.status_code == 503, response.text
    assert NO_READY in (response.json().get("error") or "")
    assert bridge.server.requests == []


# ---------------------------------------------------------------- US2-OC-08

CHAT = {"model": MODEL, "messages": [{"role": "user", "content": "你好"}]}


async def enter_opening(bridge: Bridge) -> Gate:
    gate = bridge.fakes.colab.create_session.gate()
    await bridge.ui.post("/api/session", json={"runtimeType": {"gpu": "T4", "highMem": False}})
    await gate.wait_entered_async()
    return gate


async def enter_reconnecting(bridge: Bridge) -> Gate:
    await bridge.ready()
    gate = bridge.fakes.tunnel.open_tunnel.gate()
    bridge.fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
    await gate.wait_entered_async()
    return gate


async def enter_ending(bridge: Bridge) -> Gate:
    await bridge.ready()
    gate = bridge.fakes.colab.stop_session.gate()
    await bridge.ui.delete("/api/session")
    await gate.wait_entered_async()
    return gate


@pytest.mark.parametrize(
    ("expected_state", "enter"),
    [("opening", enter_opening), ("reconnecting", enter_reconnecting), ("ending", enter_ending)],
    ids=["opening", "reconnecting", "ending"],
)
async def test_開啟中_重連中_結束中都_1_秒內回_503_不轉送(bridge: Bridge, expected_state: str, enter: Any) -> None:
    # Arrange:假伺服器若收到請求就一直不回
    bridge.server.add("POST", "/api/chat", HangReply())
    gate = await enter(bridge)
    try:
        state = (await bridge.ui.get("/api/session")).json().get("state")

        # Act
        response, elapsed = await timed_request(bridge.ollama, "POST", "/api/chat", json=CHAT)
    finally:
        gate.release()

    # Assert
    assert state == expected_state
    assert response is not None and elapsed <= 1.0, elapsed
    assert response.status_code == 503, response.text
    assert bridge.server.requests == []


# ---------------------------------------------------------------- US2-OC-09


async def test_新的工作階段就緒後_同一個用戶端不必重設就轉到新的(bridge: Bridge) -> None:
    # Arrange:第一個工作階段接假伺服器 A,第二個接假伺服器 B
    from integration.test_api_session import wait_for_state

    server_b = FakeOllamaServer().start()
    try:
        targets = [bridge.server, server_b]
        opened = bridge.world._open_tunnel

        def open_next(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return {**opened(*args, **kwargs), "baseUrl": targets[0].base_url}

        bridge.fakes.tunnel.open_tunnel.side_effect(open_next)
        bridge.server.add("GET", "/api/version", JsonReply({"version": "cgb-test-a"}))
        server_b.add("GET", "/api/version", JsonReply({"version": "cgb-test-b"}))

        # Act
        await bridge.ready()
        first = await bridge.ollama.get("/api/version")
        await bridge.ui.delete("/api/session")
        await wait_for_state(bridge.ui, "ended")
        targets.pop(0)
        await bridge.ready()
        second = await bridge.ollama.get("/api/version")
    finally:
        server_b.stop()

    # Assert
    assert first.json() == {"version": "cgb-test-a"}
    assert second.json() == {"version": "cgb-test-b"}


# ---------------------------------------------------------------- US2-OC-10


async def test_變更類型的過程中_1_秒內回_503_不排隊等新的工作階段(bridge: Bridge) -> None:
    # Arrange:工作階段就緒;結束舊的與 `create_session`(新類型)都等測試放行
    await bridge.ready()
    bridge.fakes.remote_ollama.list_local_models.returns({"models": []})
    bridge.server.add("POST", "/api/generate", HangReply())
    stop_gate = bridge.fakes.colab.stop_session.gate()
    create_gate = bridge.fakes.colab.create_session.gate()
    generate = {"model": MODEL, "prompt": "你好"}
    seen: list[tuple[str | None, httpx.Response | None, float]] = []

    # Act
    try:
        restart = await bridge.ui.post("/api/session/restart", json={"runtimeType": {"gpu": "L4", "highMem": False}})
        assert restart.status_code == 202, restart.text
        await stop_gate.wait_entered_async()
        step = (await bridge.ui.get("/api/session")).json().get("step")
        seen.append((step, *(await timed_request(bridge.ollama, "POST", "/api/generate", json=generate))))
        stop_gate.release()
        await create_gate.wait_entered_async()
        step = (await bridge.ui.get("/api/session")).json().get("step")
        seen.append((step, *(await timed_request(bridge.ollama, "POST", "/api/generate", json=generate))))
    finally:
        stop_gate.release()
        create_gate.release()

    # Assert
    assert [step for step, _, _ in seen] == ["ending_previous", "allocating"]
    for _, response, elapsed in seen:
        assert response is not None and elapsed <= 1.0, elapsed
        assert response.status_code == 503, response.text
        assert NO_READY in (response.json().get("error") or "")
    assert bridge.server.requests == []


# ---------------------------------------------------------------- US2-OC-11


async def read_stream(client: httpx.AsyncClient, path: str, body: dict[str, Any], lines: list[bytes]) -> bool:
    """串流讀完;每一行放進 `lines`。回應正常結束回 True,中途斷線(本文不完整)回 False。"""
    try:
        async with client.stream("POST", path, json=body) as response:
            async for line in response.aiter_lines():
                lines.append(line.encode())
    except (httpx.RemoteProtocolError, httpx.ReadError):
        return False
    return True


async def test_串流中途斷線時補一行串流中斷_並立刻做健康檢查進入重連(
    make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts
) -> None:
    # Arrange:排程的健康檢查拉長到測試期間不會發生,看得出是斷線觸發的那一次
    servers = start_live_servers(make_app(timeouts=replace(test_timeouts, health_interval=60.0)))
    async with connect(servers, fakes) as bridge:
        await bridge.ready()
        checks: list[float] = []

        def unhealthy(*args: Any, **kwargs: Any) -> None:
            checks.append(time.monotonic())
            raise AdapterError("TUNNEL_UNREACHABLE", "連不到")

        bridge.fakes.tunnel.check_health.side_effect(unhealthy)
        reopen_gate = bridge.fakes.tunnel.open_tunnel.gate()
        sent = [
            {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "response": "你", "done": False},
            {"model": MODEL, "created_at": "2026-11-09T09:00:01Z", "response": "好", "done": False},
        ]
        bridge.server.add("POST", "/api/generate", NdjsonReply(sent, then="disconnect"))
        lines: list[bytes] = []

        try:
            # Act
            completed = await read_stream(bridge.ollama, "/api/generate", {"model": MODEL, "prompt": "你好"}, lines)
            ended_at = time.monotonic()
            await wait_for(lambda: bool(checks), timeout=1.0)
            state = (await bridge.ui.get("/api/session")).json().get("state")
        finally:
            reopen_gate.release()

    # Assert
    assert completed, f"串流沒有正常收尾,讀到 {lines!r}"
    assert [json.loads(line) for line in lines[:2]] == sent
    assert len(lines) == 3 and "串流中斷" in (json.loads(lines[2]).get("error") or ""), lines
    assert checks and checks[0] - ended_at <= 0.2, (checks, ended_at)
    assert state == "reconnecting"


# ---------------------------------------------------------------- US2-OC-12


async def test_串流中使用者結束工作階段時補一行已結束_不當成斷線(
    make_app: Any, start_live_servers: Any, fakes: Any, test_timeouts: Timeouts
) -> None:
    # Arrange:排程的健康檢查拉長到測試期間不會發生;假伺服器送 1 行後等測試放行
    servers = start_live_servers(make_app(timeouts=replace(test_timeouts, health_interval=60.0)))
    async with connect(servers, fakes) as bridge:
        await bridge.ready()
        first = {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "response": "你", "done": False}
        last = {"model": MODEL, "created_at": "2026-11-09T09:00:01Z", "response": "", "done": True}
        release = Gate()
        bridge.server.add("POST", "/api/generate", NdjsonReply([first, release, last]))
        lines: list[bytes] = []
        checks_before = bridge.fakes.tunnel.check_health.call_count

        # Act
        reading = asyncio.create_task(read_stream(bridge.ollama, "/api/generate", {"model": MODEL, "prompt": "你好"}, lines))
        try:
            await wait_for(lambda: bool(lines), timeout=2.0)
            await bridge.ui.delete("/api/session")
            await wait_for(reading.done, timeout=1.0)
        finally:
            release.release()
        await asyncio.wait_for(reading, 5.0)
        await asyncio.sleep(0.3)
        checks_after = bridge.fakes.tunnel.check_health.call_count

    # Assert
    error = (json.loads(lines[-1]).get("error") or "") if lines else ""
    assert "工作階段已結束" in error, lines
    assert "串流中斷" not in error
    assert checks_after == checks_before


# ---------------------------------------------------------------- US2-OC-13


def closed_port() -> int:
    """一個剛關掉、沒有在聽的 127.0.0.1 port。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_連不到遠端時回_502_中文說明不含轉發位址(bridge: Bridge) -> None:
    # Arrange:工作階段就緒,但轉發位址的 port 沒有在聽
    port = closed_port()
    opened = bridge.world._open_tunnel
    bridge.fakes.tunnel.open_tunnel.side_effect(lambda *a, **k: {**opened(*a, **k), "baseUrl": f"http://127.0.0.1:{port}"})
    await bridge.ready()

    # Act
    response = await bridge.ollama.post("/api/generate", json={"model": MODEL, "prompt": "你好"})

    # Assert
    assert response.status_code == 502, response.text
    error = response.json().get("error") if response.headers.get("content-type", "").startswith("application/json") else None
    assert isinstance(error, str) and has_cjk(error), response.text
    assert "127.0.0.1" not in error and str(port) not in error


# ---------------------------------------------------------------- US2-OC-14


async def test_轉送時照送_Origin(bridge: Bridge) -> None:
    # Arrange
    await bridge.ready()
    reply = {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "message": {"role": "assistant", "content": "你好!"}, "done": True}
    bridge.server.add("POST", "/api/chat", JsonReply(reply))

    # Act
    await bridge.ollama.post("/api/chat", json={**CHAT, "stream": False}, headers={"Origin": "http://192.168.0.50:3000"})

    # Assert
    received = bridge.server.requests_to("POST", "/api/chat")
    assert [r.headers.get("origin") for r in received] == ["http://192.168.0.50:3000"]


# ---------------------------------------------------------------- US2-OC-15


def everything_of(response: httpx.Response) -> str:
    """用戶端收到的全部標頭與本文。"""
    headers = "\n".join(f"{name}: {value}" for name, value in response.headers.multi_items())
    return headers + "\n" + response.content.decode(errors="replace")


async def test_不把轉發位址傳回用戶端_轉址與錯誤都不帶_port(bridge: Bridge) -> None:
    # Arrange:假伺服器對 /api/tags 回 302 轉址到轉發位址自己;/api/generate 回 500
    await bridge.ready()
    forward_port = str(bridge.server.port)
    bridge.server.add(
        "GET", "/api/tags", JsonReply(b"", status=302, headers={"Location": f"http://127.0.0.1:{forward_port}/x"})
    )
    bridge.server.add("POST", "/api/generate", JsonReply({"error": "model runner has unexpectedly stopped"}, status=500))

    # Act
    tags = await bridge.ollama.get("/api/tags")
    generate = await bridge.ollama.post("/api/generate", json={"model": MODEL, "prompt": "你好", "stream": False})

    # Assert
    bridge.server.assert_all_matched()
    for response in (tags, generate):
        assert forward_port not in everything_of(response), everything_of(response)
    assert generate.status_code == 500
    assert "127.0.0.1" not in (generate.json().get("error") or "")


# ================================================================ 故事 3(testplan.md § 4.1)

BIG = "qwen2.5:7b"
BIG_BYTES = 4_683_087_332


def counts_of(fakes: Any) -> dict[str, int]:
    """轉接層裡會讓遠端多一次載入或下載的方法,各被呼叫幾次(預先載入與下載不經假伺服器,另外看)。"""
    remote = fakes.remote_ollama
    return {"pull_model": remote.pull_model.call_count, "preload": remote.preload.call_count}


def release_after(gate: Gate, seconds: float) -> None:
    """假伺服器「回應前睡 N 秒」:N 秒後放行閘門(閘門是 threading 的,假伺服器在自己的執行緒等)。"""
    asyncio.get_running_loop().call_later(seconds, gate.release)


# ---------------------------------------------------------------- US3-OC-01


async def test_指名沒下載的模型_原樣回_404_不自動排下載(bridge: Bridge) -> None:
    # Arrange:工作階段就緒;假伺服器對 qwen2.5:7b 回 404
    await bridge.ready()
    not_found = json.dumps({"error": f"model '{BIG}' not found"}).encode()
    bridge.server.add("POST", "/api/generate", JsonReply(not_found, status=404), json={"model": BIG})
    jobs_before = (await bridge.ui.get("/api/downloads")).json().get("jobs")
    counts_before = counts_of(bridge.fakes)

    # Act
    response = await bridge.ollama.post("/api/generate", json={"model": BIG, "prompt": "你好"})
    await asyncio.sleep(0.1)  # 若有背景排下載,給它時間發生
    jobs_after = (await bridge.ui.get("/api/downloads")).json().get("jobs")

    # Assert
    bridge.server.assert_all_matched()
    assert (response.status_code, response.content) == (404, not_found)
    assert bridge.server.requests_to("POST", "/api/pull") == []
    assert counts_of(bridge.fakes)["pull_model"] == counts_before["pull_model"]
    assert jobs_after == jobs_before


# ---------------------------------------------------------------- US3-OC-02


async def test_指名已下載未載入的模型_只轉送一次_不另外預先載入(bridge: Bridge) -> None:
    # Arrange:tags 有 qwen2.5:7b、ps 沒有;假伺服器回應前睡 0.3 秒(代表載入)
    await bridge.ready()
    bridge.server.add("GET", "/api/tags", JsonReply({"models": [{"name": BIG, "model": BIG, "size": BIG_BYTES}]}))
    bridge.server.add("GET", "/api/ps", JsonReply({"models": []}))
    reply = {"model": BIG, "created_at": "2026-11-10T09:00:00Z", "message": {"role": "assistant", "content": "你好!"}, "done": True}
    loading = Gate()
    bridge.server.add("POST", "/api/chat", HangReply(release=loading, after=JsonReply(reply)), json={"model": BIG})
    already = len(bridge.server.requests)
    counts_before = counts_of(bridge.fakes)
    body = {"model": BIG, "messages": [{"role": "user", "content": "你好"}], "stream": False}

    # Act
    release_after(loading, 0.3)
    response = await bridge.ollama.post("/api/chat", json=body)

    # Assert
    bridge.server.assert_all_matched()
    assert (response.status_code, response.content) == (200, json.dumps(reply).encode())
    assert [(r.method, r.path) for r in bridge.server.requests[already:]] == [("POST", "/api/chat")]
    assert counts_of(bridge.fakes) == counts_before


# ---------------------------------------------------------------- US3-OC-03


async def test_tags_原樣轉送_不把下載中的模型列為可用(bridge: Bridge) -> None:
    # Arrange:工作階段就緒且 qwen2.5:7b 下載中(變更類型時重新下載原本載入的模型,下載停在閘門前)
    from integration.test_api_session import wait_until

    remote = bridge.fakes.remote_ollama
    loaded = {"models": [{"name": BIG, "model": BIG, "size": BIG_BYTES}]}
    remote.list_loaded_models.side_effect(lambda *a, **k: loaded)
    remote.list_local_models.side_effect(lambda *a, **k: loaded)
    remote.pull_model.side_effect(lambda *a, **k: [{"status": "success"}])
    remote.preload.side_effect(lambda *a, **k: {"model": BIG, "done": True})
    old = (await bridge.ready())["name"]
    pulling = remote.pull_model.gate()
    tags = {"models": [{"name": MODEL, "model": MODEL, "size": 397_821_319}]}
    bridge.server.add("GET", "/api/tags", JsonReply(tags))
    try:
        await bridge.ui.post("/api/session/restart", json={"runtimeType": {"gpu": "L4", "highMem": False}})
        await wait_until(bridge.ui, lambda s: s.get("state") == "ready" and s.get("name") != old)
        await pulling.wait_entered_async()
        queue = (await bridge.ui.get("/api/downloads")).json()
        assert [(j.get("model"), j.get("state")) for j in queue.get("jobs", [])] == [(BIG, "downloading")], queue

        # Act
        response = await bridge.ollama.get("/api/tags")
    finally:
        pulling.release()

    # Assert
    bridge.server.assert_all_matched()
    assert (response.status_code, response.content) == (200, json.dumps(tags).encode())
    assert [m["name"] for m in response.json()["models"]] == [MODEL]


# ---------------------------------------------------------------- US3-OC-04


async def test_同時兩個請求指名同一個未載入的模型_都照轉送_不排隊不預先載入(bridge: Bridge) -> None:
    # Arrange:ps 沒有 qwen2.5:7b;假伺服器回應前睡 0.5 秒
    await bridge.ready()
    reply = {"model": BIG, "created_at": "2026-11-10T09:00:00Z", "response": "你好!", "done": True}
    loading = Gate()
    bridge.server.add("GET", "/api/ps", JsonReply({"models": []}))
    bridge.server.add("POST", "/api/generate", HangReply(release=loading, after=JsonReply(reply)), json={"model": BIG})
    already = len(bridge.server.requests)
    counts_before = counts_of(bridge.fakes)
    body = {"model": BIG, "prompt": "你好", "stream": False}

    # Act
    release_after(loading, 0.5)
    first, second = await asyncio.gather(
        bridge.ollama.post("/api/generate", json=body), bridge.ollama.post("/api/generate", json=body)
    )

    # Assert
    bridge.server.assert_all_matched()
    assert [(r.status_code, r.content) for r in (first, second)] == [(200, json.dumps(reply).encode())] * 2
    assert [(r.method, r.path) for r in bridge.server.requests[already:]] == [("POST", "/api/generate")] * 2
    assert counts_of(bridge.fakes) == counts_before
