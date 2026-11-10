"""E2 後端 UI API:用量(testplan.md § 5.1,`/api/usage` › 查詢、排程 › 讀用量)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身;時間由注入的假時鐘推進(不真的等 5 分鐘)。
`get_usage` 要在 app 啟動前設定好(啟動時就會讀第一次),所以各案例自己起 app。
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from cgb.app import AppPair
from cgb.domain.session_state import iso, parse_iso
from conftest import FakeClock
from integration.test_api_events import next_session_update, sse_events
from integration.test_api_session import ColabWorld, open_ready, wait_for_state

READ_AT = datetime(2026, 11, 10, 8, 0, 0, tzinfo=UTC)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock(start=READ_AT)


@asynccontextmanager
async def running(pair: AppPair) -> AsyncIterator[httpx.AsyncClient]:
    """跑一個 app(含 lifespan),離開時關掉它;app 內未處理的例外照 HTTP 500 回給測試。"""
    async with pair.ui.router.lifespan_context(pair.ui):
        transport = httpx.ASGITransport(app=pair.ui, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://cgb-ui.test") as client:
            yield client


def usage_of(clock: FakeClock, balance: float, rate: float, active: int = 1) -> Callable[..., dict[str, Any]]:
    """`get_usage` 的替身:回傳固定的數值,`readAt` 是被呼叫時注入時鐘的時間。"""

    def read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"balance": balance, "ratePerHour": rate, "activeAssignments": active, "readAt": iso(clock.now())}

    return read


async def get_usage(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get("/api/usage")


async def wait_usage(client: httpx.AsyncClient, predicate: Callable[[dict[str, Any]], bool], timeout: float = 2.0) -> dict[str, Any]:
    """一直查 `GET /api/usage`,直到 `predicate` 成立或逾時;回傳最後一次看到的(不是 200 時是空的 dict)。"""
    deadline = time.monotonic() + timeout
    while True:
        response = await get_usage(client)
        usage = response.json() if response.status_code == 200 else {}
        if predicate(usage) or time.monotonic() > deadline:
            return usage
        await asyncio.sleep(0.01)


async def next_event(
    events: AsyncIterator[tuple[str, dict[str, Any]]], name: str, predicate: Callable[[dict[str, Any]], bool], timeout: float = 2.0
) -> dict[str, Any] | None:
    """讀到第一則名稱是 `name`、且 `predicate(payload)` 成立的事件;逾時回 None。"""

    async def find() -> dict[str, Any] | None:
        async for event, payload in events:
            if event == name and predicate(payload):
                return payload
        return None

    try:
        return await asyncio.wait_for(find(), timeout)
    except TimeoutError:
        return None


def seconds_between(a: str | None, b: datetime) -> float:
    assert a is not None
    return abs((parse_iso(a) - b).total_seconds())


# ---------------------------------------------------------------- US4-API-01


async def test_查詢用量回最後一次讀到的值與讀取時間_估計時數是餘額除以耗用(
    make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock
) -> None:
    # Arrange
    fakes.colab.get_usage.side_effect(usage_of(fake_clock, 381.66, 1.15))

    async with running(make_app()) as client:
        await wait_usage(client, lambda u: u.get("state") == "known")

        # Act:啟動後把時鐘推進 10 秒再查
        fake_clock.advance(10)
        response = await get_usage(client)

    # Assert
    assert response.status_code == 200, response.text
    usage = response.json()
    assert (usage.get("state"), usage.get("balance"), usage.get("ratePerHour")) == ("known", 381.66, 1.15)
    assert 331.8 <= (usage.get("hoursRemaining") or 0) <= 331.9, usage.get("hoursRemaining")
    assert seconds_between(usage.get("readAt"), READ_AT) < 1.0, usage.get("readAt")
    assert usage.get("stale") is False


# ---------------------------------------------------------------- US4-API-02


@pytest.mark.parametrize(
    ("balance", "rate", "expected_hours"),
    [(381.66, 0.00, None), (-0.50, 1.15, 0)],
    ids=["情況A_耗用為0", "情況B_餘額為負"],
)
async def test_耗用為零時估計時數為_null_餘額為負時為_0(
    make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock, balance: float, rate: float, expected_hours: Any
) -> None:
    # Arrange
    fakes.colab.get_usage.side_effect(usage_of(fake_clock, balance, rate, active=0))

    async with running(make_app()) as client:
        # Act
        usage = await wait_usage(client, lambda u: u.get("state") == "known")

    # Assert:則1、則2
    assert "hoursRemaining" in usage and usage["hoursRemaining"] == expected_hours, usage
    # Assert:則3
    assert usage.get("balance") == balance


# ---------------------------------------------------------------- US4-API-03


async def test_從沒讀到用量時為未知並附原因_不擋開啟與結束(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:從 app 啟動起 get_usage 都連不到 Colab
    ColabWorld(fakes)
    fakes.colab.get_usage.raises("COLAB_UNREACHABLE", "ConnectionError")

    async with running(make_app()) as client:
        # Act
        usage = await wait_usage(client, lambda u: u.get("reasonCode") is not None)
        opened = await client.post("/api/session", json={"runtimeType": {"gpu": "T4", "highMem": False}})
        ready = await wait_for_state(client, "ready")
        ended = await client.delete("/api/session")
        final = await wait_for_state(client, "ended")

    # Assert:則1
    assert (usage.get("state"), usage.get("reasonCode")) == ("unknown", "COLAB_UNREACHABLE"), usage
    assert usage.get("message")
    # Assert:則2
    assert opened.status_code == 202, opened.text
    assert ready.get("state") == "ready"
    # Assert:則3
    assert ended.status_code == 202, ended.text
    assert final.get("state") == "ended"


# ---------------------------------------------------------------- US4-API-04


async def test_餘額低於門檻時警告但照樣能開啟_等於門檻不算低(
    make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock
) -> None:
    # Arrange:警告門檻是預設的 10;情況 A 回 9.50
    ColabWorld(fakes)
    fakes.colab.get_usage.side_effect(usage_of(fake_clock, 9.50, 1.15))

    async with running(make_app()) as client:
        # Act:情況 A
        low = await wait_usage(client, lambda u: u.get("state") == "known")
        opened = await client.post("/api/session", json={"runtimeType": {"gpu": "T4", "highMem": False}})
        ready = await wait_for_state(client, "ready")

    # Arrange:情況 B 回 10.00(另起一個 app,啟動時讀到)
    fakes.colab.get_usage.side_effect(usage_of(fake_clock, 10.00, 1.15))
    async with running(make_app()) as client:
        # Act:情況 B
        equal = await wait_usage(client, lambda u: u.get("balance") == 10.00)

    # Assert:則1、則2
    assert (low.get("warningThreshold"), low.get("lowBalance")) == (10, True), low
    assert (equal.get("balance"), equal.get("lowBalance")) == (10.00, False), equal
    # Assert:則3
    assert opened.status_code == 202, opened.text
    assert ready.get("state") == "ready"


# ---------------------------------------------------------------- US4-API-05


async def test_排程讀到低餘額時推送警告_不自動結束工作階段(
    make_app: Callable[..., AppPair], start_live_servers: Any, fakes: Any, fake_clock: FakeClock
) -> None:
    # Arrange:工作階段就緒;門檻 10;get_usage 第一次回 50.00,之後回 0.50
    ColabWorld(fakes)
    fakes.colab.get_usage.then(usage_of(fake_clock, 50.00, 1.15)())
    fakes.colab.get_usage.side_effect(usage_of(fake_clock, 0.50, 1.15))
    servers = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=5.0) as client:
        await wait_usage(client, lambda u: u.get("state") == "known")
        await open_ready(client)
        async with client.stream("GET", "/api/events") as response:
            events = sse_events(response)
            await next_session_update(events)  # 連上時的快照,確認已經訂閱

            # Act:時鐘推進 5 分鐘,讓下一次讀用量發生
            fake_clock.advance(5 * 60)
            updated = await next_event(events, "usage.updated", lambda p: p.get("usage", {}).get("balance") == 0.50)
        session = (await client.get("/api/session")).json()

    # Assert:則1
    assert updated is not None and updated["usage"].get("lowBalance") is True, updated
    # Assert:則2、則3
    assert session.get("state") == "ready"
    assert fakes.colab.stop_session.call_count == 0


# ---------------------------------------------------------------- US4-API-18


async def advance_to(clock: FakeClock, until: datetime, step: timedelta = timedelta(seconds=30)) -> None:
    """一步一步把時鐘推進到 `until`,每一步讓背景的排程有機會跑。"""
    while clock.now() + step < until:
        clock.advance(step.total_seconds())
        await asyncio.sleep(0.01)
    clock.set(until)
    await asyncio.sleep(0.02)


async def test_每_5_分鐘內讀一次用量_讀不到時保留快照並標過期_恢復後清掉失敗說明(
    make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock
) -> None:
    # Arrange:get_usage 第一次成功(readAt 為 T),之後一直連不到 Colab,直到測試讓它恢復
    calls: list[datetime] = []
    recovered = False

    def read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(fake_clock.now())
        if len(calls) > 1 and not recovered:
            from cgb.adapters.errors import AdapterError

            raise AdapterError("COLAB_UNREACHABLE", "ConnectionError")
        return {"balance": 381.66, "ratePerHour": 1.15, "activeAssignments": 1, "readAt": iso(fake_clock.now())}

    fakes.colab.get_usage.side_effect(read)
    async with running(make_app()) as client:
        first = await wait_usage(client, lambda u: u.get("state") == "known")
        t = parse_iso(first["readAt"])

        # Act:時鐘從 T 推進到 T+20 分鐘,中間在 T+14:59 與 T+15:01 各查一次
        await advance_to(fake_clock, t + timedelta(minutes=14, seconds=59))
        fresh = (await get_usage(client)).json()
        await advance_to(fake_clock, t + timedelta(minutes=15, seconds=1))
        stale = (await get_usage(client)).json()
        await advance_to(fake_clock, t + timedelta(minutes=20))
        recovered = True
        reads_before_recovery = len(calls)
        await advance_to(fake_clock, t + timedelta(minutes=25))
        await wait_usage(client, lambda u: u.get("reasonCode") is None and len(calls) > reads_before_recovery)
        await advance_to(fake_clock, t + timedelta(minutes=25, seconds=30))
        after = (await get_usage(client)).json()

    # Assert:則1 相鄰兩次 get_usage 的間隔都不超過 5 分鐘
    gaps = [(b - a).total_seconds() for a, b in zip(calls, calls[1:])]
    assert calls[-1] >= t + timedelta(minutes=20) and all(gap <= 300 for gap in gaps), gaps
    # Assert:則2、則3
    assert fresh.get("stale") is False, fresh
    assert stale.get("stale") is True, stale
    # Assert:則4
    assert (stale.get("state"), stale.get("balance"), stale.get("readAt")) == ("known", 381.66, first["readAt"]), stale
    # Assert:則5
    assert stale.get("reasonCode") == "COLAB_UNREACHABLE" and stale.get("lastFailedAt") is not None, stale
    # Assert:則6
    assert (after.get("reasonCode"), after.get("message"), after.get("lastFailedAt"), after.get("stale")) == (
        None,
        None,
        None,
        False,
    ), after
