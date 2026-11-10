"""E2 後端 UI API:設定(testplan.md § 5.1,`/api/settings` › 查詢、修改)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身;時間由注入的假時鐘推進。
"""

import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx

from cgb.app import AppPair
from cgb.domain.session_state import parse_iso
from conftest import FakeClock
from integration.test_api_events import next_session_update, sse_events
from integration.test_api_session import ColabWorld, open_ready, wait_until
from integration.test_api_usage import next_event, running, usage_of, wait_usage


async def get_settings(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get("/api/settings")


# ---------------------------------------------------------------- US4-API-06


async def test_全新的資料庫查設定回預設值(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:全新的 SQLite 檔(conftest 的 db_path)
    async with running(make_app()) as client:
        # Act
        response = await get_settings(client)

    # Assert:則1、則2
    assert response.status_code == 200, response.text
    assert response.json() == {"idleTimeoutMinutes": 30, "lowBalanceThreshold": 10}


# ---------------------------------------------------------------- US4-API-07


async def test_修改設定寫進資料庫並推送_重建後仍是新的值(
    make_app: Callable[..., AppPair], start_live_servers: Any, fakes: Any
) -> None:
    # Arrange:預設設定;訂閱 SSE
    servers = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=5.0) as client:
        async with client.stream("GET", "/api/events") as response:
            events = sse_events(response)
            await next_session_update(events)  # 連上時的快照,確認已經訂閱

            # Act
            put = await client.put("/api/settings", json={"idleTimeoutMinutes": 10, "lowBalanceThreshold": 5})
            pushed = await next_event(events, "settings.updated", lambda p: True)
        before = (await get_settings(client)).json()
    async with running(make_app()) as rebuilt:
        after = (await get_settings(rebuilt)).json()

    # Assert:則1
    assert put.status_code == 200, put.text
    assert put.json() == {"idleTimeoutMinutes": 10, "lowBalanceThreshold": 5}
    # Assert:則2
    assert pushed is not None and pushed.get("settings") == {"idleTimeoutMinutes": 10, "lowBalanceThreshold": 5}, pushed
    # Assert:則3
    assert before == after == {"idleTimeoutMinutes": 10, "lowBalanceThreshold": 5}


# ---------------------------------------------------------------- US4-API-08


async def test_設定超出範圍時回_400_兩個欄位都不寫入(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:設定為 30 與 10;另一個欄位用和現在不同的合法值,看得出有沒有被寫進去
    bad_idle = [{"idleTimeoutMinutes": v, "lowBalanceThreshold": 20} for v in (0, 1441, 10.5)]
    bad_threshold = [{"idleTimeoutMinutes": 45, "lowBalanceThreshold": v} for v in (-1, 10001)]

    async with running(make_app()) as client:
        # Act
        idle_results = [await client.put("/api/settings", json=body) for body in bad_idle]
        threshold_results = [await client.put("/api/settings", json=body) for body in bad_threshold]
        after = (await get_settings(client)).json()

    # Assert:則1
    assert [(r.status_code, r.json().get("code")) for r in idle_results] == [(400, "INVALID_IDLE_TIMEOUT")] * 3
    # Assert:則2
    assert [(r.status_code, r.json().get("code")) for r in threshold_results] == [(400, "INVALID_BALANCE_THRESHOLD")] * 2
    assert all(r.json().get("message") for r in idle_results + threshold_results)
    # Assert:則3
    assert after == {"idleTimeoutMinutes": 30, "lowBalanceThreshold": 10}


# ---------------------------------------------------------------- US4-API-09


async def test_修改閒置時限立即生效_倒數以最後一次請求起算(
    make_app: Callable[..., AppPair], start_live_servers: Any, fakes: Any, fake_clock: FakeClock
) -> None:
    # Arrange:工作階段就緒,閒置時限 30 分鐘,idle.lastRequestAt 為 T(就緒的時間,還沒有任何請求)
    ColabWorld(fakes)
    servers = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=5.0) as client:
        ready = await open_ready(client)
        t = parse_iso(ready["idle"]["lastRequestAt"])
        async with client.stream("GET", "/api/events") as response:
            events = sse_events(response)
            await next_session_update(events)  # 連上時的快照,確認已經訂閱

            # Act:時鐘在 T+3 分鐘時修改
            fake_clock.set(t + timedelta(minutes=3))
            put = await client.put("/api/settings", json={"idleTimeoutMinutes": 10, "lowBalanceThreshold": 10})
            pushed = await next_event(
                events, "session.updated", lambda p: (p["session"].get("idle") or {}).get("timeoutMinutes") == 10
            )
        session = (await client.get("/api/session")).json()

    # Assert:則1
    assert put.status_code == 200, put.text
    assert (session.get("idle") or {}).get("timeoutMinutes") == 10, session.get("idle")
    # Assert:則2
    assert parse_iso(session["idle"]["deadline"]) == t + timedelta(minutes=10), session["idle"]
    # Assert:則3
    assert pushed is not None, "沒有收到 session.updated"
    assert parse_iso(pushed["session"]["idle"]["deadline"]) == t + timedelta(minutes=10), pushed["session"]["idle"]


# ---------------------------------------------------------------- US4-API-10


async def test_新的閒置時限已經到了就立即自動結束(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:工作階段就緒,閒置時限 30 分鐘,時鐘已在 idle.lastRequestAt 之後 12 分鐘
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        ready = await open_ready(client)
        fake_clock.set(parse_iso(ready["idle"]["lastRequestAt"]) + timedelta(minutes=12))

        # Act
        put = await client.put("/api/settings", json={"idleTimeoutMinutes": 10, "lowBalanceThreshold": 10})
        changed_at = time.monotonic()
        ending = await wait_until(
            client, lambda s: s.get("state") in ("ending", "ended") and s.get("endReason") == "IDLE_TIMEOUT", timeout=2.0
        )
        elapsed = time.monotonic() - changed_at
        await wait_until(client, lambda s: s.get("state") == "ended", timeout=2.0)

    # Assert:則1
    assert put.status_code == 200, put.text
    # Assert:則2
    assert ending.get("state") in ("ending", "ended") and ending.get("endReason") == "IDLE_TIMEOUT", ending
    assert elapsed <= 1.0, elapsed
    # Assert:則3
    assert world.calls("stop_session") == [ready["name"]]


# ---------------------------------------------------------------- US4-API-11


async def test_修改警告門檻立即反映在用量警告上_不必重新讀用量(
    make_app: Callable[..., AppPair], start_live_servers: Any, fakes: Any, fake_clock: FakeClock
) -> None:
    # Arrange:最後讀到的餘額 15.00,門檻 10
    fakes.colab.get_usage.side_effect(usage_of(fake_clock, 15.00, 1.15))
    servers = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=5.0) as client:
        before = await wait_usage(client, lambda u: u.get("state") == "known")
        async with client.stream("GET", "/api/events") as response:
            events = sse_events(response)
            await next_session_update(events)  # 連上時的快照,確認已經訂閱
            reads_before = fakes.colab.get_usage.call_count

            # Act
            put = await client.put("/api/settings", json={"idleTimeoutMinutes": 30, "lowBalanceThreshold": 20})
            pushed = await next_event(events, "usage.updated", lambda p: True)
            usage = (await client.get("/api/usage")).json()
        reads_after = fakes.colab.get_usage.call_count

    # Assert:則1
    assert put.status_code == 200, put.text
    assert before.get("lowBalance") is False
    assert (usage.get("lowBalance"), usage.get("warningThreshold")) == (True, 20), usage
    # Assert:則2
    assert pushed is not None and pushed["usage"].get("lowBalance") is True, pushed
    # Assert:則3
    assert reads_after == reads_before
