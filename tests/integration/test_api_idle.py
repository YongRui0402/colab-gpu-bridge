"""E2 後端 UI API:閒置自動結束(testplan.md § 5.1,排程 › 閒置到期)。

接縫:HTTP `/api/*`(UI)與 Ollama 相容端點的 HTTP,五個轉接層用替身;閒置時限改成 1 分鐘,
時間由注入的假時鐘推進(不真的等)。
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import httpx

from cgb.app import AppPair
from cgb.domain.session_state import iso, parse_iso
from conftest import FakeClock
from fakes import JsonReply
from integration.test_api_session import ColabWorld, get_session, open_ready, wait_until
from integration.test_api_usage import running, wait_usage


async def set_idle_timeout(client: httpx.AsyncClient, minutes: int) -> None:
    response = await client.put("/api/settings", json={"idleTimeoutMinutes": minutes, "lowBalanceThreshold": 10})
    assert response.status_code == 200, response.text


async def states_for(client: httpx.AsyncClient, seconds: float) -> list[str]:
    """在一段真實時間內一直查 `GET /api/session`,回傳看到的每一個 `state`。"""
    seen: list[str] = []
    loop = asyncio.get_running_loop()
    until = loop.time() + seconds
    while loop.time() < until:
        seen.append((await get_session(client)).get("state"))
        await asyncio.sleep(0.02)
    return seen


def is_idle_ended(session: dict[str, Any]) -> bool:
    return session.get("state") == "ended" and session.get("endReason") == "IDLE_TIMEOUT"


# ---------------------------------------------------------------- US4-API-12


async def test_閒置到期時在背景自動結束_關通道並釋放(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:工作階段就緒,閒置時限 1 分鐘,沒有任何請求
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        await set_idle_timeout(client, 1)
        ready = await open_ready(client)
        deadline = parse_iso(ready["idle"]["deadline"])

        # Act:時鐘推進到 deadline 之前,再推進到 deadline 之後(SC-006:1 分鐘之內)
        fake_clock.set(deadline - timedelta(seconds=1))
        before = await states_for(client, 0.3)
        fake_clock.set(deadline + timedelta(seconds=1))
        ended = await wait_until(client, is_idle_ended, timeout=2.0)
        ended_by = fake_clock.now()
        history = (await client.get("/api/sessions")).json()

    # Assert:則1
    assert set(before) == {"ready"}, before
    # Assert:則2
    assert is_idle_ended(ended), ended
    assert ended_by <= deadline + timedelta(minutes=1)
    # Assert:則3
    assert world.calls("close_tunnel") == [ready["name"]]
    assert world.calls("stop_session") == [ready["name"]]
    # Assert:則4
    record = next(item for item in history["items"] if item["name"] == ready["name"])
    assert record.get("endReason") == "IDLE_TIMEOUT"


@asynccontextmanager
async def running_pair(pair: AppPair) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient]]:
    """跑 UI 與 Ollama 相容端點兩個 app(含 lifespan);回傳兩個 ASGI 用戶端。"""
    async with AsyncExitStack() as stack:
        for app in (pair.ui, pair.ollama):
            await stack.enter_async_context(app.router.lifespan_context(app))
        ui = await stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=pair.ui, raise_app_exceptions=False), base_url="http://cgb-ui.test"
            )
        )
        ollama = await stack.enter_async_context(
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=pair.ollama, raise_app_exceptions=False), base_url="http://cgb-ollama.test"
            )
        )
        yield ui, ollama


# ---------------------------------------------------------------- US4-API-13


async def test_經_Ollama_相容端點的請求重設閒置計時(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:工作階段就緒,閒置時限 1 分鐘,readyAt 為 T
    ColabWorld(fakes)
    fakes.server.add("GET", "/api/tags", JsonReply({"models": []}))
    async with running_pair(make_app()) as (ui, ollama):
        await set_idle_timeout(ui, 1)
        t = parse_iso((await open_ready(ui))["readyAt"])

        # Act:T+50 秒經 Ollama 相容端點送 GET /api/tags,再推進到 T+80 秒
        fake_clock.set(t + timedelta(seconds=50))
        tags = await ollama.get("/api/tags")
        idle = (await get_session(ui)).get("idle") or {}
        fake_clock.set(t + timedelta(seconds=80))
        later = await states_for(ui, 0.3)

    # Assert:則1
    assert tags.status_code == 200, tags.text
    assert abs((parse_iso(idle["lastRequestAt"]) - (t + timedelta(seconds=50))).total_seconds()) < 1.0, idle
    assert parse_iso(idle["deadline"]) - parse_iso(idle["lastRequestAt"]) == timedelta(minutes=1), idle
    # Assert:則2
    assert set(later) == {"ready"}, later


# ---------------------------------------------------------------- US4-API-14


async def test_UI_API_的請求不重設閒置計時(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:工作階段就緒,閒置時限 1 分鐘,readyAt 為 T
    ColabWorld(fakes)
    fakes.remote_ollama.list_local_models.side_effect(lambda *a, **k: {"models": []})
    async with running_pair(make_app()) as (ui, _):
        await set_idle_timeout(ui, 1)
        t = parse_iso((await open_ready(ui))["readyAt"])

        # Act:T+50 秒時送 UI API 的查詢,再推進到 T+70 秒
        fake_clock.set(t + timedelta(seconds=50))
        for path in ("/api/session", "/api/models", "/api/usage"):
            await ui.get(path)
        idle = (await get_session(ui)).get("idle") or {}
        fake_clock.set(t + timedelta(seconds=70))
        ended = await wait_until(
            ui, lambda s: s.get("state") in ("ending", "ended") and s.get("endReason") == "IDLE_TIMEOUT", timeout=2.0
        )

    # Assert:則1
    assert parse_iso(idle["lastRequestAt"]) == t, idle
    # Assert:則2
    assert ended.get("state") in ("ending", "ended") and ended.get("endReason") == "IDLE_TIMEOUT", ended


# ---------------------------------------------------------------- US4-API-15


async def test_後端重啟後閒置倒數接著算_不從重啟的時間重算(
    make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock
) -> None:
    # Arrange:工作階段就緒,閒置時限 10 分鐘;就緒 30 秒後經 Ollama 相容端點送一個請求,idle.lastRequestAt 為 T
    ColabWorld(fakes)
    fakes.server.add("GET", "/api/tags", JsonReply({"models": []}))
    async with running_pair(make_app()) as (ui, ollama):
        await set_idle_timeout(ui, 10)
        ready_at = parse_iso((await open_ready(ui))["readyAt"])
        fake_clock.set(ready_at + timedelta(seconds=30))
        await ollama.get("/api/tags")
        t = parse_iso((await get_session(ui))["idle"]["lastRequestAt"])

    # Act:時鐘在 T+6 分鐘時重建 app(list_sessions 仍列出這台)
    fake_clock.set(t + timedelta(minutes=6))
    async with running_pair(make_app()) as (ui, _):
        recovered = await wait_until(ui, lambda s: s.get("state") == "ready" and s.get("idle") is not None)
        fake_clock.set(t + timedelta(minutes=11))
        ended = await wait_until(ui, lambda s: s.get("endReason") == "IDLE_TIMEOUT", timeout=2.0)

    # Assert:則1
    assert recovered.get("idle") is not None and parse_iso(recovered["idle"]["deadline"]) == t + timedelta(minutes=10), recovered
    # Assert:則2
    assert ended.get("endReason") == "IDLE_TIMEOUT", ended


# ---------------------------------------------------------------- US4-API-16


async def test_閒置自動結束時釋放失敗要警告(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:同 US4-API-12,但 stop_session 回 COLAB_STOP_UNCONFIRMED
    ColabWorld(fakes)
    fakes.colab.stop_session.raises("COLAB_STOP_UNCONFIRMED", "兩次 colab stop 之後仍看得到")
    async with running(make_app()) as client:
        await set_idle_timeout(client, 1)
        ready = await open_ready(client)

        # Act:時鐘推進到 deadline 之後
        fake_clock.set(parse_iso(ready["idle"]["deadline"]) + timedelta(seconds=1))
        ended = await wait_until(client, is_idle_ended, timeout=2.0)

    # Assert:則1
    assert ended.get("endReason") == "IDLE_TIMEOUT", ended
    # Assert:則2
    assert (ended.get("releaseWarning") or {}).get("message"), ended.get("releaseWarning")


# ---------------------------------------------------------------- US4-API-20


class NowFailsOnceClock(FakeClock):
    """假時鐘;`fail_next_now()` 之後,下一次被讀現在時間時丟一次 `RuntimeError`(不是 `AdapterError`),之後恢復正常。"""

    def __init__(self) -> None:
        super().__init__()
        self._fail_next = False
        self.failures = 0

    def fail_next_now(self) -> None:
        self._fail_next = True

    def now(self) -> datetime:
        if self._fail_next:
            self._fail_next = False
            self.failures += 1
            raise RuntimeError("讀時鐘時的非預期錯誤(測試注入)")
        return super().now()


async def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    until = loop.time() + timeout
    while not predicate() and loop.time() < until:
        await asyncio.sleep(0.01)


async def test_讀用量遇到非預期的例外時下一輪照常讀取(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:情況 A,app 啟動時那次 get_usage 丟 RuntimeError,之後回 50.00
    def read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if fakes.colab.get_usage.call_count == 1:
            raise RuntimeError("讀用量時的非預期錯誤(測試注入)")
        return {"balance": 50.0, "ratePerHour": 1.15, "activeAssignments": 0, "readAt": iso(fake_clock.now())}

    fakes.colab.get_usage.side_effect(read)
    async with running(make_app()) as client:
        await wait_for(lambda: fakes.colab.get_usage.call_count >= 1)

        # Act:時鐘推進 5 分鐘,送 GET /api/usage
        fake_clock.advance(5 * 60)
        usage = await wait_usage(client, lambda u: u.get("state") == "known")

    # Assert:則1
    reads = fakes.colab.get_usage.call_count
    assert reads >= 2, f"get_usage 只被呼叫 {reads} 次"
    assert (usage.get("state"), usage.get("balance")) == ("known", 50.0), usage


async def test_閒置檢查遇到非預期的例外時下一輪照常自動結束(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:情況 B,工作階段就緒,閒置時限 1 分鐘,沒有任何請求
    clock = NowFailsOnceClock()
    world = ColabWorld(fakes)
    async with running(make_app(clock=clock)) as client:
        await set_idle_timeout(client, 1)
        ready = await open_ready(client)
        deadline = parse_iso(ready["idle"]["deadline"])

        # Act:時鐘推進到 deadline 加 1 秒;閒置檢查讀時間時丟一次例外,之後一直查 GET /api/session
        clock.set(deadline + timedelta(seconds=1))
        clock.fail_next_now()
        await wait_for(lambda: clock.failures == 1)
        ended = await wait_until(client, is_idle_ended, timeout=3.0)
        ended_by = clock.now()

    # Assert:則2
    assert clock.failures == 1
    assert is_idle_ended(ended), ended
    assert ended_by <= deadline + timedelta(minutes=1)
    # Assert:則3
    assert world.calls("stop_session") == [ready["name"]]
