"""E2 後端 UI API:SSE 的 `session.updated` 推送(testplan.md § 3.1,`GET /api/events`;contracts/ui.openapi.yaml § `paths./events.get`)。

007 不改推送:這一節的案例都由既有程式做到,測試是守住現況(對照組見各任務的紅燈紀錄)。
接縫:HTTP `/api/events` 經真的連線(測試行程內 uvicorn 的 `live_servers`、`start_live_servers`),五個轉接層用替身。
"""

import asyncio
import contextlib
import json
import logging
import re
import sqlite3
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.domain.session_state import parse_iso
from conftest import FakeClock
from fakes import NdjsonReply
from integration.test_api_chat import DONE, bridge, chunk  # noqa: F401(bridge 是 fixture)
from integration.test_api_events import sse_events
from integration.test_api_health import record_rounds
from integration.test_api_idle import set_idle_timeout
from integration.test_api_recovery import reset_calls
from integration.test_api_session import ColabWorld, open_ready, wait_until
from integration.test_api_switch import L4, with_loaded_model
from integration.test_ollama_compat import MODEL, Bridge, wait_for

# 一則 `session.updated` 的 `session` 與收到的時間
SessionUpdate = tuple[dict[str, Any], float]

# 結束之後不該再出現的「進行中」狀態
ACTIVE_STATES = ("opening", "ready", "applying_tuning", "reconnecting", "ending")


async def collect_session_updates(events: AsyncIterator[tuple[str, dict[str, Any]]], seconds: float) -> list[SessionUpdate]:
    """讀 `seconds` 秒,依序記下每一則 `session.updated` 的 `session` 與收到時的 `time.monotonic()`。"""
    seen: list[SessionUpdate] = []

    async def read() -> None:
        async for name, payload in events:
            if name == "session.updated":
                seen.append((payload["session"], time.monotonic()))

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(read(), seconds)
    return seen


async def first_event(events: AsyncIterator[tuple[str, dict[str, Any]]], timeout: float = 3.0) -> tuple[str, dict[str, Any]] | None:
    """只讀第一則(不跳過其他事件);`timeout` 秒內沒有就是 None。"""
    try:
        return await asyncio.wait_for(anext(events), timeout)
    except (TimeoutError, StopAsyncIteration):
        return None


# ---------------------------------------------------------------- US2-API-01


async def test_使用者結束工作階段時推出同一台的_ended_之後不再推進行中的狀態(start_live_servers: Any, make_app: Any, fakes: Any) -> None:
    # Arrange:真的 HTTP,工作階段開到就緒,`/api/events` 讀完快照
    ColabWorld(fakes)
    live = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=live.ui_url, timeout=5.0) as client:
        name = (await open_ready(client))["name"]
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            snapshot = await first_event(events)

            # Act
            await client.delete("/api/session")
            updates = await collect_session_updates(events, 2.0)

    # Assert
    assert snapshot is not None and snapshot[0] == "session.updated"
    ended = [(session, at) for session, at in updates if session.get("state") == "ended"]
    assert ended, f"2 秒內沒有收到 ended:{[s.get('state') for s, _ in updates]}"
    assert ended[0][0]["name"] == name
    ended_at = ended[0][1]
    after = [session["state"] for session, at in updates if ended_at < at <= ended_at + 0.5]
    assert [state for state in after if state in ACTIVE_STATES] == []


# ---------------------------------------------------------------- US2-API-02


async def test_閒置到期結束時推出同一台的_ended_與_IDLE_TIMEOUT(start_live_servers: Any, make_app: Any, fakes: Any, fake_clock: Any) -> None:
    # Arrange:閒置時限 1 分鐘,工作階段開到就緒,`/api/events` 讀完快照
    ColabWorld(fakes)
    live = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=live.ui_url, timeout=5.0) as client:
        await set_idle_timeout(client, 1)
        ready = await open_ready(client)
        name, deadline = ready["name"], parse_iso(ready["idle"]["deadline"])
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await first_event(events)

            # Act:時鐘推進到 deadline 之後
            fake_clock.set(deadline + timedelta(seconds=1))
            updates = await collect_session_updates(events, 2.0)

    # Assert
    ended = [session for session, _ in updates if session.get("state") == "ended"]
    assert ended, f"2 秒內沒有收到 ended:{[s.get('state') for s, _ in updates]}"
    assert (ended[0]["name"], ended[0]["endReason"]) == (name, "IDLE_TIMEOUT")


# ---------------------------------------------------------------- US2-API-03


async def test_被_Colab_收回時推出同一台的_lost_與_RECLAIMED_BY_COLAB(start_live_servers: Any, make_app: Any, fakes: Any) -> None:
    # Arrange:工作階段開到就緒,`/api/events` 讀完快照
    world = ColabWorld(fakes)
    live = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=live.ui_url, timeout=5.0) as client:
        name = (await open_ready(client))["name"]
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await first_event(events)

            # Act:`colab sessions` 列不到這台、通道也連不上
            world.alive.remove(name)
            fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
            updates = await collect_session_updates(events, 2.0)

    # Assert
    lost = [session for session, _ in updates if session.get("state") == "lost"]
    assert lost, f"2 秒內沒有收到 lost:{[s.get('state') for s, _ in updates]}"
    assert (lost[0]["name"], lost[0]["endReason"]) == (name, "RECLAIMED_BY_COLAB")


# ---------------------------------------------------------------- US2-API-04


async def test_重連時限到了推出同一台的_lost_與_RECONNECT_TIMEOUT(start_live_servers: Any, make_app: Any, fakes: Any) -> None:
    # Arrange:重連時限 2 秒(conftest 注入),工作階段開到就緒之後 `open_tunnel` 一直失敗
    world = ColabWorld(fakes)
    live = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=live.ui_url, timeout=5.0) as client:
        name = (await open_ready(client))["name"]
        rounds = record_rounds(world, fakes)
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await first_event(events)

            # Act:通道健康檢查失敗,讀 4 秒
            fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
            updates = await collect_session_updates(events, 4.0)

    # Assert
    reconnecting = [session for session, _ in updates if session.get("state") == "reconnecting"]
    assert reconnecting and reconnecting[0]["name"] == name
    first_close = next(at for at, method in rounds if method == "close_tunnel")
    lost = [(session, at) for session, at in updates if session.get("state") == "lost"]
    assert lost, f"4 秒內沒有收到 lost:{[s.get('state') for s, _ in updates]}"
    session, received = lost[0]
    assert (session["name"], session["endReason"]) == (name, "RECONNECT_TIMEOUT")
    assert 1.8 <= received - first_close <= 2.5, received - first_close


# ---------------------------------------------------------------- US2-API-05


async def test_換執行環境後推送的是新的那台_舊的那台結束時不再推出舊名稱(start_live_servers: Any, make_app: Any, fakes: Any) -> None:
    # Arrange:工作階段開到就緒記下 `old`,`/api/events` 讀完快照
    world = ColabWorld(fakes)
    with_loaded_model(world, fakes)
    live = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=live.ui_url, timeout=5.0) as client:
        old = (await open_ready(client))["name"]
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await first_event(events)

            # Act:換成 L4,讀到新名稱就緒或 4 秒
            started = time.monotonic()
            restart = await client.post("/api/session/restart", json={"runtimeType": L4})
            updates: list[SessionUpdate] = []
            while time.monotonic() - started < 4.0:
                updates += await collect_session_updates(events, 0.2)
                if any(s["name"] != old and s.get("state") == "ready" for s, _ in updates):
                    break

    # Assert
    assert restart.status_code == 202, restart.text
    new_names = [(session["name"], at) for session, at in updates if session["name"] != old]
    assert new_names, f"沒有收到新名稱:{[(s['name'], s.get('state')) for s, _ in updates]}"
    assert new_names[0][1] - started <= 2.0
    assert new_names[0][0] == restart.json()["name"]
    first_new_index = next(i for i, (session, _) in enumerate(updates) if session["name"] != old)
    assert [s["name"] for s, _ in updates[first_new_index:] if s["name"] == old] == []


# ---------------------------------------------------------------- US2-API-06


async def test_重連中新連上的第一則是完整的_reconnecting_現況(start_live_servers: Any, make_app: Any, fakes: Any) -> None:
    # Arrange:工作階段就緒,通道檢查失敗後重連一直失敗,等到 `GET /api/session` 是 `reconnecting`
    world = ColabWorld(fakes)
    live = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=live.ui_url, timeout=5.0) as client:
        name = (await open_ready(client))["name"]
        record_rounds(world, fakes)
        fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
        await wait_until(client, lambda s: s.get("state") == "reconnecting", timeout=3.0)

        # Act:這時才新開一條 `/api/events`,只讀第一則
        async with client.stream("GET", "/api/events") as stream:
            first = await first_event(sse_events(stream))

    # Assert
    assert first is not None
    event, payload = first
    assert event == "session.updated"
    assert (payload["session"]["state"], payload["session"]["name"]) == ("reconnecting", name)


# ---------------------------------------------------------------- US2-API-07


async def test_後端重新啟動後新連上的第一則是重啟前那台_3_秒內回到就緒(start_live_servers: Any, make_app: Any, fakes: Any) -> None:
    # Arrange:第一個後端把工作階段開到就緒、停掉(同一個 SQLite 檔與替身狀態)
    ColabWorld(fakes)
    first = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=first.ui_url, timeout=5.0) as client:
        name = (await open_ready(client))["name"]
    first.stop()
    reset_calls(fakes)

    # Act:重新啟動後端,立刻開 `/api/events` 讀 3 秒
    second = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=second.ui_url, timeout=5.0) as client:
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            head = await first_event(events)
            updates = await collect_session_updates(events, 3.0)

    # Assert
    assert head is not None
    event, payload = head
    assert event == "session.updated"
    assert payload["session"]["name"] == name
    assert payload["session"]["state"] in ("ready", "reconnecting", "applying_tuning", "ending")
    states = [payload["session"]["state"]] + [session["state"] for session, _ in updates if session["name"] == name]
    assert "ready" in states, states


# ---------------------------------------------------------------- US2-API-08


class FrozenClock(FakeClock):
    """現在的時間固定不動(monotonic 仍照真實時間走,等待與時限照常):兩台的 `opened_at` 因此相同。

    `FakeClock` 的 `now()` 照真實時間往前走,連續開兩台的 `opened_at` 會差幾毫秒,測不到 `rowid` 的分次序。
    """

    def now(self) -> Any:
        return self._start


async def test_開啟時間相同的兩台新連上推的是後寫入的那一台(start_live_servers: Any, make_app: Any, fakes: Any) -> None:
    # Arrange:時鐘固定,兩台的 `opened_at` 相同;第一台開到就緒再結束,再開第二台
    ColabWorld(fakes)
    live = start_live_servers(make_app(clock=FrozenClock()))
    async with httpx.AsyncClient(base_url=live.ui_url, timeout=5.0) as client:
        a = (await open_ready(client))["name"]
        await client.delete("/api/session")
        await wait_until(client, lambda s: s.get("state") == "ended", timeout=3.0)
        b = (await open_ready(client))["name"]

        # Act:新開一條 `/api/events`,只讀第一則
        async with client.stream("GET", "/api/events") as stream:
            first = await first_event(sse_events(stream))

    # Assert
    assert a != b
    assert first is not None
    event, payload = first
    assert event == "session.updated"
    assert (payload["session"]["name"], payload["session"]["state"]) == (b, "ready")


# ---------------------------------------------------------------- US2-API-09

CHAT_MARK = "cgb-test-007-對話-不該留下"
CONTROL_MARK = "cgb-test-007-對照-應找得到"


def count_mark(text_or_bytes: str | bytes, mark: str) -> int:
    """`mark` 在 `text_or_bytes` 出現幾次:字串與 UTF-8 位元組都搜,也搜 JSON 把中文轉成 `\\uXXXX` 的寫法。"""
    data = text_or_bytes.encode("utf-8") if isinstance(text_or_bytes, str) else text_or_bytes
    escaped = json.dumps(mark)[1:-1].encode("utf-8")
    return data.count(mark.encode("utf-8")) + data.count(escaped)


def database_bytes(path: Path) -> bytes:
    """SQLite 檔與同名 `-wal`、`-journal` 的位元組(沒有的算空)。"""
    return b"".join(Path(f"{path}{suffix}").read_bytes() if Path(f"{path}{suffix}").exists() else b"" for suffix in ("", "-wal", "-journal"))


def table_text(path: Path) -> str:
    """`sqlite_master` 每張表的全表內容。"""
    with sqlite3.connect(path) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return "".join(repr(conn.execute(f'SELECT * FROM "{table}"').fetchall()) for table in tables)


def ended_updates(sse_text: str) -> list[dict[str, Any]]:
    """從 SSE 原文取出 `state` 為 `ended` 的 `session.updated`。"""
    found = []
    for block in sse_text.split("\n\n"):
        match = re.search(r"^event: ?session\.updated$", block, re.MULTILINE)
        data = re.search(r"^data: ?(.*)$", block, re.MULTILINE)
        if match and data and json.loads(data.group(1))["session"].get("state") == "ended":
            found.append(json.loads(data.group(1))["session"])
    return found


async def test_對話內容不會出現在日誌_資料庫與_SSE_推送(bridge: Bridge, caplog: pytest.LogCaptureFixture, db_path: Path, tmp_path: Path) -> None:  # noqa: F811(bridge 是 fixture)
    # Arrange:工作階段就緒,日誌開到 DEBUG;`/api/events` 在背景把每一行原文記下
    await bridge.ready()
    caplog.set_level(logging.DEBUG)
    bridge.server.add("POST", "/api/chat", NdjsonReply([chunk(CHAT_MARK), DONE]))
    sse_lines: list[str] = []

    async def read_events() -> None:
        async with bridge.ui.stream("GET", "/api/events") as stream:
            async for line in stream.aiter_lines():
                sse_lines.append(line)

    reading = asyncio.create_task(read_events())
    control_db = sqlite3.connect(tmp_path / "control.sqlite")  # 對照組的資料庫:WAL、不 checkpoint、不碰 `db_path`
    try:
        control_db.execute("PRAGMA journal_mode=WAL")
        control_db.execute("PRAGMA wal_autocheckpoint=0")
        control_db.execute("CREATE TABLE control (text TEXT)")
        control_db.execute("INSERT INTO control VALUES (?)", (CONTROL_MARK,))
        control_db.commit()
        assert await wait_for(lambda: any(line.startswith("event: session.updated") for line in sse_lines), timeout=3.0)

        # Act:寫一行對照日誌,送一則對話讀完,結束工作階段並等到 SSE 收到 `ended`
        logging.getLogger("cgb").info(CONTROL_MARK)
        async with bridge.ui.stream("POST", "/api/chat", json={"model": MODEL, "messages": [{"role": "user", "content": CHAT_MARK}]}) as response:
            reply = "".join([line async for line in response.aiter_lines()])
        await bridge.ui.delete("/api/session")
        got_ended = await wait_for(lambda: bool(ended_updates("\n".join(sse_lines) + "\n\n")), timeout=3.0)
        await asyncio.sleep(0.2)

        # Assert
        sse_text = "\n".join(sse_lines) + "\n\n"
        assert count_mark(reply, CHAT_MARK) >= 1  # 對話本身有走過(替身的回覆就是這一句)
        assert count_mark(caplog.text, CONTROL_MARK) >= 1  # 則1:對照組找得到
        assert count_mark(database_bytes(tmp_path / "control.sqlite"), CONTROL_MARK) >= 1  # 則2
        assert count_mark(caplog.text, CHAT_MARK) == 0  # 則3
        assert count_mark(database_bytes(db_path), CHAT_MARK) == 0  # 則4
        assert count_mark(table_text(db_path), CHAT_MARK) == 0  # 則5
        assert count_mark(sse_text, CHAT_MARK) == 0  # 則6
        assert got_ended and ended_updates(sse_text)  # 則7
    finally:
        reading.cancel()
        with contextlib.suppress(asyncio.CancelledError, httpx.HTTPError):
            await reading
        control_db.close()
