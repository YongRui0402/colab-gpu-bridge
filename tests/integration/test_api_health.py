"""E2 後端 UI API:健康檢查與重連(testplan.md § 2.1,排程 › 健康檢查、排程 › 重連)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身;時限與節奏照 conftest 注入的縮短值
(健康檢查間隔 0.2 秒、重連時限 2 秒、節奏「立即、0.05、0.1、0.2 秒,之後每 0.3 秒」)。
"""

import asyncio
import time
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    get_session,
    open_ready,
    ui_client,
    wait_until,
)


# ---------------------------------------------------------------- US1-API-17


async def test_健康檢查失敗且執行環境已不在時判定被_Colab_收回(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    opens_before = fakes.tunnel.open_tunnel.call_count

    # Act
    world.alive.remove(name)
    fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
    failing_since = time.monotonic()
    final = await wait_until(ui_client, lambda s: s.get("state") == "lost", timeout=2.0)
    elapsed = time.monotonic() - failing_since
    await asyncio.sleep(0.2)

    # Assert
    assert final.get("state") == "lost" and elapsed <= 1.0, (final.get("state"), elapsed)
    assert final.get("endReason") == "RECLAIMED_BY_COLAB"
    assert "重新開啟" in (final.get("message") or "")
    assert fakes.tunnel.open_tunnel.call_count == opens_before


def record_rounds(world: ColabWorld, fakes: Any) -> list[tuple[float, str]]:
    """把每一次 close_tunnel、list_sessions、open_tunnel 依序記下(時間,方法);`open_tunnel` 一直失敗。"""
    events: list[tuple[float, str]] = []

    def close(*args: Any, **kwargs: Any) -> dict[str, Any]:
        events.append((time.monotonic(), "close_tunnel"))
        return world._close_tunnel(*args, **kwargs)

    def listing(*args: Any, **kwargs: Any) -> dict[str, Any]:
        events.append((time.monotonic(), "list_sessions"))
        return world._list(*args, **kwargs)

    def open_failing(*args: Any, **kwargs: Any) -> None:
        events.append((time.monotonic(), "open_tunnel"))
        raise AdapterError("TUNNEL_UNREACHABLE", "連不到")

    fakes.tunnel.close_tunnel.side_effect(close)
    fakes.colab.list_sessions.side_effect(listing)
    fakes.tunnel.open_tunnel.side_effect(open_failing)
    return events


# ---------------------------------------------------------------- US1-API-19


async def test_重連每一輪先關通道再確認再建立_照節奏直到時限(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:重連時限 2 秒、節奏「立即、0.05、0.1、0.2,之後每 0.3 秒」(conftest 注入)
    world = ColabWorld(fakes)
    await open_ready(ui_client)
    events = record_rounds(world, fakes)

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
    await wait_until(ui_client, lambda s: s.get("state") == "lost", timeout=4.0)

    # Assert
    rounds = [events[i : i + 3] for i in range(0, len(events), 3)]
    assert all([method for _, method in r] == ["close_tunnel", "list_sessions", "open_tunnel"] for r in rounds), events
    starts = [r[0][0] - rounds[0][0][0] for r in rounds]
    expected = [0.0, 0.05, 0.15, 0.35, 0.65]
    assert len(starts) >= 5 and all(abs(a - e) <= 0.03 for a, e in zip(starts, expected, strict=False)), starts
    assert max(starts) <= 2.0, starts


# ---------------------------------------------------------------- US1-API-20


async def test_colab_sessions_本身失敗時不判定被收回_接回後恢復就緒(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await open_ready(ui_client)
    fakes.colab.list_sessions.raises("COLAB_UNREACHABLE", "連不到 Colab")
    fakes.tunnel.open_tunnel.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
    seen: list[dict[str, Any]] = []
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        seen.append(await get_session(ui_client))
        if seen[-1].get("state") == "ready" and any(s.get("state") == "reconnecting" for s in seen):
            break
        await asyncio.sleep(0.01)

    # Assert
    assert seen[-1].get("state") == "ready", [s.get("state") for s in seen[-5:]]
    assert all(s.get("endReason") != "RECLAIMED_BY_COLAB" for s in seen)
    assert world.alive  # 執行環境沒有被結束


# ---------------------------------------------------------------- US1-API-21


async def test_重連時限到仍接不回時判定失聯並釋放執行環境(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:重連時限 2 秒;open_tunnel 一直回 TUNNEL_UNREACHABLE
    world = ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    events = record_rounds(world, fakes)

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
    final = await wait_until(ui_client, lambda s: s.get("state") == "lost", timeout=4.0)
    lost_after = time.monotonic() - events[0][0] if events else None
    await wait_until(ui_client, lambda s: bool(world.calls("stop_session")), timeout=1.0)

    # Assert
    assert final.get("state") == "lost" and lost_after is not None and 1.8 <= lost_after <= 2.5, (final.get("state"), lost_after)
    assert (final.get("endReason"), final.get("reasonCode")) == ("RECONNECT_TIMEOUT", "TUNNEL_UNREACHABLE")
    assert world.calls("stop_session") == [name]


# ---------------------------------------------------------------- US1-API-22


async def test_重連逾時後釋放失敗時留下警告(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await open_ready(ui_client)
    record_rounds(world, fakes)
    fakes.colab.stop_session.raises("COLAB_STOP_UNCONFIRMED", "兩次結束後仍看得到這個執行環境")

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
    final = await wait_until(
        ui_client, lambda s: s.get("state") == "lost" and s.get("releaseWarning") is not None, timeout=4.0
    )

    # Assert
    assert final.get("state") == "lost"
    assert (final.get("releaseWarning") or {}).get("message") is not None


# ---------------------------------------------------------------- US1-API-37


async def test_健康檢查不重設閒置計時(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:健康檢查間隔 0.2 秒
    ColabWorld(fakes)
    await open_ready(ui_client)
    checks_before = fakes.tunnel.check_health.call_count

    # Act:等 1.1 秒,不送任何 Ollama 相容端點的請求
    await asyncio.sleep(1.1)
    session = await get_session(ui_client)

    # Assert
    assert (session.get("idle") or {}).get("lastRequestAt") == session.get("readyAt") is not None
    assert fakes.tunnel.check_health.call_count - checks_before >= 5


# ---------------------------------------------------------------- US1-API-18


async def test_斷線後重連接回同一個執行環境_不另開新的(live_servers: Any, fakes: Any) -> None:
    # Arrange:就緒;已載入 qwen2.5:0.5b
    from datetime import datetime

    from integration.test_api_events import sse_events

    world = ColabWorld(fakes)
    fakes.remote_ollama.list_loaded_models.side_effect(
        lambda *a, **k: {"models": [{"name": "qwen2.5:0.5b", "model": "qwen2.5:0.5b", "size": 397_821_319}]}
    )
    seen: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        name = (await open_ready(client))["name"]
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)

            # Act:健康檢查失敗 1 次;重連第 1 輪 open_tunnel 撞上舊連線、第 2 輪成功
            fakes.tunnel.open_tunnel.then(AdapterError("TUNNEL_ALREADY_CONNECTED", "已有另一條連線"))
            fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))

            async def collect() -> None:
                async for event, payload in events:
                    if event != "session.updated":
                        continue
                    seen.append(payload["session"])
                    states = [s.get("state") for s in seen]
                    if "reconnecting" in states and states[-1] == "ready":
                        return

            try:
                await asyncio.wait_for(collect(), 3.0)
            except TimeoutError:
                pass

    # Assert
    states = [s.get("state") for s in seen]
    collapsed = [state for i, state in enumerate(states) if i == 0 or states[i - 1] != state]
    assert collapsed[-2:] == ["reconnecting", "ready"], states
    assert seen[-1].get("name") == name
    assert fakes.colab.create_session.call_count == 1
    reconnecting = [s for s in seen if s.get("state") == "reconnecting"]
    windows = [
        (datetime.fromisoformat(r["deadline"].replace("Z", "+00:00")) - datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00"))).total_seconds()
        for s in reconnecting
        if (r := s.get("reconnect"))
    ]
    assert reconnecting and windows == [2.0] * len(reconnecting), windows
