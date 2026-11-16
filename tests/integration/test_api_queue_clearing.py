"""E2 後端 UI API:工作階段結束時清空下載佇列(004 testplan.md § 2.1,`/api/session` › 結束 → `/api/downloads` › 列出)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身(testplan.md § 接縫的取捨)。
下載佇列只屬於一個工作階段:結束、閒置結束、被收回、重連逾時、開啟失敗時同步清空,
每移除一筆推 `download.removed`,全部移除後推一則 `downloads.snapshot`(contracts/ui.openapi.yaml § info.x-queue-clearing)。
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.app import AppPair
from cgb.db.connection import connect
from cgb.domain.session_state import parse_iso
from conftest import TEST_TIMEOUTS, FakeClock
from fakes import Gate
from integration.test_api_downloads import (
    LATEST_SIZES,
    MANIFEST_SIZES,
    QWEN_MID,
    downloadable,
    enqueue_waiting,
    hold_pulls,
    queue,
    set_library,
    states,
    wait_queue,
)
from integration.test_api_events import sse_events
from integration.test_api_health import record_rounds
from integration.test_api_idle import is_idle_ended, set_idle_timeout
from integration.test_api_models import QWEN_7B, QWEN_SMALL, set_tags
from integration.test_api_recovery import reset_calls, running
from integration.test_api_session import T4, ColabWorld, error_code, open_ready, ui_client, wait_for_state, wait_until  # noqa: F401(ui_client 是 fixture)
from integration.test_api_switch import L4, with_loaded_model

QUEUE_EVENT_NAMES = frozenset({"download.removed", "downloads.snapshot", "download.updated", "autoDownload.updated"})


class EventFeed:
    """背景讀 SSE:把佇列的四種事件記成 (名稱, payload, 收到的 `time.monotonic()`),`queue_events` 一次取走一段。"""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict[str, Any], float]] = []
        self.connected = asyncio.Event()
        self.cursor = 0

    async def pump(self, stream: httpx.Response) -> None:
        async for name, payload in sse_events(stream):
            if not self.connected.is_set():
                if name == "autoDownload.updated":
                    self.connected.set()  # 連上時的快照(工作階段、佇列、自動下載結果)到這一則為止
            elif name in QUEUE_EVENT_NAMES:
                self.seen.append((name, payload, time.monotonic()))


@asynccontextmanager
async def subscribed(client: httpx.AsyncClient) -> AsyncIterator[EventFeed]:
    """訂閱 `GET /api/events` 並讀完連上時的快照,之後的佇列事件由 `queue_events` 取。"""
    async with client.stream("GET", "/api/events") as stream:
        feed = EventFeed()
        task = asyncio.create_task(feed.pump(stream))
        try:
            await asyncio.wait_for(feed.connected.wait(), 2.0)
            yield feed
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def queue_events(feed: EventFeed, seconds: float) -> list[tuple[str, dict[str, Any], float]]:
    """在一段真實時間內收下佇列的事件;回傳從上一次取走之後到這一段結束收到的全部。"""
    await asyncio.sleep(seconds)
    taken = feed.seen[feed.cursor :]
    feed.cursor = len(feed.seen)
    return taken


async def mixed_queue(client: httpx.AsyncClient, fakes: Any) -> tuple[Gate, list[int]]:
    """佇列依序鋪成完成、失敗、下載中、排隊中四種狀態;回傳 (`qwen2.5:7b` 的 pull 閘門, 四筆的 id)。"""
    set_library(fakes, LATEST_SIZES)
    hold = Gate()

    def pull(*args: Any, **kwargs: Any) -> list[Any]:
        model = kwargs["model"]
        if model == QWEN_7B:
            return [{"status": "pulling manifest"}, hold, {"status": "success"}]
        if model == QWEN_MID:
            return [{"status": "pulling manifest"}, AdapterError("OLLAMA_PULL_FAILED", "no space left on device")]
        return [{"status": "success"}]

    fakes.remote_ollama.pull_model.side_effect(pull)
    models = [QWEN_SMALL, QWEN_MID, QWEN_7B, "llama3.2:latest"]
    await client.post("/api/downloads", json={"models": models})
    expected = [(QWEN_SMALL, "completed"), (QWEN_MID, "failed"), (QWEN_7B, "downloading"), ("llama3.2:latest", "queued")]
    current = await wait_queue(client, lambda q: states(q) == expected)
    assert states(current) == expected
    return hold, [job["id"] for job in current["jobs"]]


# ---- 004 US1-API-01


async def test_結束時佇列立即清空_每一筆推移除_最後推一則空的快照(live_servers: Any, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    stop_gate = fakes.colab.stop_session.gate()
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        hold, ids = await mixed_queue(client, fakes)
        async with subscribed(client) as feed:
            # Act
            sent_at = time.monotonic()
            response = await client.delete("/api/session")
            ending_queue = await queue(client)
            events = await queue_events(feed, 0.5)
            stop_gate.release()
            await wait_for_state(client, "ended")
            ended_queue = await queue(client)
            hold.release()

    # Assert
    assert (response.status_code, response.json().get("state")) == (202, "ending")  # 則1
    assert ending_queue["jobs"] == []  # 則2
    assert ending_queue["paused"] is True  # 則3
    removed = [payload["id"] for name, payload, _ in events if name == "download.removed"]
    assert (len(removed), set(removed)) == (4, set(ids))  # 則4
    names = [name for name, _, _ in events if name in ("download.removed", "downloads.snapshot")]
    snapshots = [(payload, at) for name, payload, at in events if name == "downloads.snapshot"]
    assert names == ["download.removed"] * 4 + ["downloads.snapshot"]  # 則5
    assert snapshots[0][0]["queue"]["jobs"] == []  # 則6
    assert snapshots[0][1] - sent_at < 1.0  # 則7
    failed_7b = [p for name, p, _ in events if name == "download.updated" and p["job"]["state"] == "failed"]
    assert failed_7b == []  # 則8
    assert ended_queue["jobs"] == []  # 則9


# ---- 004 US1-API-02


async def test_結束後下載中的那筆不會復活_新的工作階段不接續上一台的項目(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, QWEN_7B, QWEN_SMALL)
    fakes.colab.probe_resources.reset_calls()

    # Act
    await ui_client.delete("/api/session")
    await wait_for_state(ui_client, "ended")
    hold.release()
    await asyncio.sleep(0.2)
    after_release = await queue(ui_client)
    set_tags(fakes)
    await open_ready(ui_client)
    await asyncio.sleep(0.3)
    after_ready = await queue(ui_client)
    probes = fakes.colab.probe_resources.call_count
    catalog = (await ui_client.get("/api/models")).json()

    # Assert
    assert after_release["jobs"] == []  # 則1
    assert after_ready["jobs"] == []  # 則2
    assert fakes.remote_ollama.pull_model.call_count == 1  # 則3
    assert probes == 0  # 則4
    assert QWEN_7B not in [item["name"] for item in catalog["items"]]  # 則5


# ---- 004 US1-API-03


async def test_閒置自動結束時佇列也立即清空(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange
    downloadable(fakes)
    async with running(make_app()) as client:
        await set_idle_timeout(client, 1)
        ready = await open_ready(client)
        hold, _ = await mixed_queue(client, fakes)
        deadline = parse_iso(ready["idle"]["deadline"])

        # Act
        advanced_at = time.monotonic()
        fake_clock.set(deadline + timedelta(seconds=1))
        ended = await wait_until(client, is_idle_ended, timeout=1.0)
        cleared = await queue(client)
        answered_at = time.monotonic()
        hold.release()

    # Assert
    assert (ended["state"], ended["endReason"]) == ("ended", "IDLE_TIMEOUT")  # 則1
    assert cleared["jobs"] == []  # 則2
    assert answered_at - advanced_at < 1.0  # 則3


# ---- 004 US1-API-04


async def test_被_Colab_收回時佇列也立即清空(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = downloadable(fakes)
    name = (await open_ready(ui_client))["name"]
    hold, _ = await mixed_queue(ui_client, fakes)

    # Act
    world.alive.remove(name)
    fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
    failing_since = time.monotonic()
    lost = await wait_until(ui_client, lambda s: s.get("state") == "lost", timeout=1.0)
    cleared = await queue(ui_client)
    answered_at = time.monotonic()
    hold.release()

    # Assert
    assert (lost["state"], lost["endReason"]) == ("lost", "RECLAIMED_BY_COLAB")  # 則1
    assert cleared["jobs"] == []  # 則2
    assert answered_at - failing_since < 1.0  # 則3


# ---- 004 US1-API-05


async def test_重連中佇列照舊_重連逾時失聯時才清空(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange
    world = downloadable(fakes)
    async with running(make_app(timeouts=replace(TEST_TIMEOUTS, reconnect_limit=0.3))) as client:
        await open_ready(client)
        hold, _ = await mixed_queue(client, fakes)
        record_rounds(world, fakes)

        # Act
        fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
        await wait_until(client, lambda s: s.get("state") == "reconnecting", timeout=1.0)
        while_reconnecting = await queue(client)
        lost = await wait_until(client, lambda s: s.get("state") == "lost", timeout=1.0)
        cleared = await queue(client)
        hold.release()

    # Assert
    assert states(while_reconnecting) == [
        (QWEN_SMALL, "completed"),
        (QWEN_MID, "failed"),
        (QWEN_7B, "downloading"),
        ("llama3.2:latest", "queued"),
    ]  # 則1
    assert (lost["state"], lost["endReason"]) == ("lost", "RECONNECT_TIMEOUT")  # 則2
    assert cleared["jobs"] == []  # 則3


# ---- 004 US1-API-06


async def test_開啟中按結束時重新載入的項目也清空_之後不下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    with_loaded_model(world, fakes)
    await open_ready(ui_client)
    create_gate = fakes.colab.create_session.gate()
    await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    await create_gate.wait_entered_async()

    # Act
    while_opening = await queue(ui_client)
    response = await ui_client.delete("/api/session")
    right_after = await queue(ui_client)
    create_gate.release()
    await wait_for_state(ui_client, "ended")
    await asyncio.sleep(0.2)
    after_ended = await queue(ui_client)

    # Assert
    assert [(job["model"], job["state"], job["origin"]) for job in while_opening["jobs"]] == [(QWEN_SMALL, "queued", "restore")]  # 則1
    assert response.status_code == 202  # 則2
    assert right_after["jobs"] == []  # 則3
    assert after_ended["jobs"] == []  # 則4
    assert fakes.remote_ollama.pull_model.call_count == 0  # 則5


# ---- 004 US1-API-07


async def test_新類型開不起來時重新載入的項目也清空_之後的工作階段不下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    with_loaded_model(world, fakes)
    old = (await open_ready(ui_client))["name"]

    def reject_l4(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["gpu"] == "L4":
            world.log.append(("create_session", kwargs["name"]))
            raise AdapterError("COLAB_ACCELERATOR_REJECTED", "帳號沒有這種加速器的額度")
        return world._create(*args, **kwargs)

    fakes.colab.create_session.side_effect(reject_l4)

    # Act
    await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    failed = await wait_until(ui_client, lambda s: s.get("name") != old and s.get("state") == "open_failed")
    after_failed = await queue(ui_client)
    await open_ready(ui_client, T4)
    await asyncio.sleep(0.3)
    after_ready = await queue(ui_client)

    # Assert
    assert (failed["state"], failed["reasonCode"]) == ("open_failed", "COLAB_ACCELERATOR_REJECTED")  # 則1
    assert after_failed["jobs"] == []  # 則2
    assert after_ready["jobs"] == []  # 則3
    assert fakes.remote_ollama.pull_model.call_count == 0  # 則4


# ---- 004 US1-API-08


async def test_變更類型時舊的項目清空_只留重新載入的項目_先推空快照再推那一筆(live_servers: Any, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    with_loaded_model(world, fakes)
    set_library(fakes, LATEST_SIZES)
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        old = (await open_ready(client))["name"]
        await client.post("/api/downloads", json={"models": [QWEN_7B]})
        done = await wait_queue(client, lambda q: states(q) == [(QWEN_7B, "completed")])
        old_id = done["jobs"][0]["id"]
        async with subscribed(client) as feed:
            stop_gate = fakes.colab.stop_session.gate()
            world.log.clear()

            # Act
            await client.post("/api/session/restart", json={"runtimeType": L4})
            right_after = await queue(client)
            events = await queue_events(feed, 0.3)
            stop_gate.release()
            await wait_until(client, lambda s: s.get("state") == "ready" and s.get("name") != old)
            await wait_until(client, lambda s: bool(world.calls("preload")))
            final = await queue(client)

    # Assert
    assert [(job["model"], job["state"], job["origin"]) for job in right_after["jobs"]] == [(QWEN_SMALL, "queued", "restore")]  # 則1
    restore_id = right_after["jobs"][0]["id"]
    order = [(name, payload) for name, payload, _ in events]
    removed_at = [i for i, (name, p) in enumerate(order) if name == "download.removed" and p["id"] == old_id]
    assert len(removed_at) == 1  # 則2
    restored_at = [
        i
        for i, (name, p) in enumerate(order)
        if name == "download.updated" and p["job"]["model"] == QWEN_SMALL and p["job"]["origin"] == "restore"
    ]
    assert restored_at and restored_at[0] > removed_at[0]  # 則3
    assert [p for name, p in order if name == "download.removed" and p["id"] == restore_id] == []  # 則4
    assert [(job["model"], job["state"]) for job in final["jobs"]] == [(QWEN_SMALL, "completed")]  # 則5
    assert [(m, a) for m, a in world.log if m in ("pull_model", "preload")] == [("pull_model", QWEN_SMALL), ("preload", QWEN_SMALL)]  # 則6
    snapshots_at = [i for i, (name, _) in enumerate(order) if name == "downloads.snapshot"]
    assert len(snapshots_at) == 1 and removed_at[0] < snapshots_at[0] < restored_at[0]  # 則7
    assert order[snapshots_at[0]][1]["queue"]["jobs"] == []  # 則7、則8


# ---- 004 US1-API-09


async def test_連續兩次變更類型時只留這一次的重新載入項目(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    with_loaded_model(world, fakes)
    set_library(fakes, LATEST_SIZES)
    old = (await open_ready(ui_client))["name"]
    await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    first = await wait_until(ui_client, lambda s: s.get("state") == "ready" and s.get("name") != old)
    await wait_until(ui_client, lambda s: bool(world.calls("preload")))
    first_queue = await wait_queue(ui_client, lambda q: states(q) == [(QWEN_SMALL, "completed")])

    # Act
    response = await ui_client.post("/api/session/restart", json={"runtimeType": T4})
    right_after = await queue(ui_client)

    # Assert
    assert (response.status_code, first["state"]) == (202, "ready")
    assert states(right_after) == [(QWEN_SMALL, "queued")]  # 則1
    assert right_after["jobs"][0]["id"] != first_queue["jobs"][0]["id"]  # 則2


# ---- 004 US1-API-10


async def test_重啟時發現停機期間被收回_佇列清空_之後的工作階段不下載(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:第一個 app 關掉時下載中的那筆留在資料庫為 downloading
    world = downloadable(fakes)
    async with running(make_app()) as client:
        name = (await open_ready(client))["name"]
        hold, _ = await mixed_queue(client, fakes)
    hold.release()
    world.alive.remove(name)
    reset_calls(fakes)
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "success"}])

    # Act
    async with running(make_app()) as client:
        lost = await wait_until(client, lambda s: s.get("state") == "lost", timeout=1.0)
        cleared = await queue(client)
        await open_ready(client)
        await asyncio.sleep(0.3)
        after_ready = await queue(client)

    # Assert
    assert (lost["state"], lost["endReason"]) == ("lost", "RECLAIMED_BY_COLAB")  # 則1
    assert cleared["jobs"] == []  # 則2
    assert after_ready["jobs"] == []  # 則3
    assert fakes.remote_ollama.pull_model.call_count == 0  # 則4


# ---- 004 US1-API-11


async def test_重啟後接回同一個工作階段時佇列不清_中斷的下載接回後繼續(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:第一個 app 關掉時下載中的那筆留在資料庫為 downloading;工作階段仍在
    downloadable(fakes)
    async with running(make_app()) as client:
        await open_ready(client)
        hold, first_ids = await mixed_queue(client, fakes)
    hold.release()
    reset_calls(fakes)
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "success"}])
    reattach = fakes.tunnel.open_tunnel.gate()

    # Act
    async with running(make_app()) as client:
        await reattach.wait_entered_async()
        while_reattaching = await queue(client)
        reattach.release()
        await wait_for_state(client, "ready")
        after_reattach = await wait_queue(client, lambda q: all(job["state"] not in ("queued", "downloading") for job in q["jobs"]))

    # Assert
    assert states(while_reattaching) == [
        (QWEN_SMALL, "completed"),
        (QWEN_MID, "failed"),
        (QWEN_7B, "queued"),
        ("llama3.2:latest", "queued"),
    ]  # 則1
    assert states(after_reattach) == [
        (QWEN_SMALL, "completed"),
        (QWEN_MID, "failed"),
        (QWEN_7B, "completed"),
        ("llama3.2:latest", "completed"),
    ]  # 則2
    assert [job["id"] for job in after_reattach["jobs"]] == first_ids  # 則3
    assert [call.kwargs["model"] for call in fakes.remote_ollama.pull_model.calls] == [QWEN_7B, "llama3.2:latest"]  # 則4


# ---- 004 US1-API-12


def insert_legacy_jobs(db_path: Path, *jobs: tuple[str, str]) -> None:
    """直接寫入升級前留下的項目(`session_name` 為 NULL),(模型, 狀態) 依序排在佇列最後面。"""
    conn = connect(db_path)
    for model, state in jobs:
        pending = model if state in ("queued", "downloading") else None
        conn.execute(
            "INSERT INTO download_jobs (session_name, model, pending_model, queue_position, size_bytes, state, added_at)"
            " VALUES (NULL, ?, ?, (SELECT COALESCE(MAX(queue_position), 0) + 1 FROM download_jobs), ?, ?,"
            " '2026-11-01T09:00:00Z')",
            (model, pending, MANIFEST_SIZES[model], state),
        )
    conn.close()


async def test_升級前沒有所屬工作階段的項目在啟動時清掉_不論有沒有工作階段可接回(
    make_app: Callable[..., AppPair], fakes: Any, db_path: Path, tmp_path: Path
) -> None:
    # Arrange 情況 A:第一個 app 開到就緒、`qwen2.5:1.5b` 下載中時關掉;再寫入兩筆沒有所屬工作階段的項目
    downloadable(fakes)
    hold = hold_pulls(fakes)
    async with running(make_app()) as client:
        await open_ready(client)
        await client.post("/api/downloads", json={"models": [QWEN_MID]})
        await wait_queue(client, lambda q: states(q) == [(QWEN_MID, "downloading")])
    hold.release()
    insert_legacy_jobs(db_path, (QWEN_SMALL, "completed"), (QWEN_7B, "queued"))
    reset_calls(fakes)
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "success"}])
    # Arrange 情況 B:資料庫沒有任何工作階段,只有同樣兩筆沒有所屬工作階段的項目
    db_b = tmp_path / "no-session.sqlite3"
    async with running(make_app(db_path=db_b)):
        pass
    insert_legacy_jobs(db_b, (QWEN_SMALL, "completed"), (QWEN_7B, "queued"))

    # Act
    async with running(make_app()) as client:
        await wait_for_state(client, "ready")
        queue_a = await wait_queue(client, lambda q: (QWEN_MID, "completed") in states(q))
        await asyncio.sleep(0.2)
        pulled_a = [call.kwargs["model"] for call in fakes.remote_ollama.pull_model.calls]
    async with running(make_app(db_path=db_b)) as client:
        await asyncio.sleep(0.3)
        queue_b = await queue(client)

    # Assert
    assert states(queue_a) == [(QWEN_MID, "completed")]  # 則1
    assert pulled_a == [QWEN_MID]  # 則2
    assert queue_b["jobs"] == []  # 則3


# ---- 004 US1-API-13


async def wait_auto_result(client: httpx.AsyncClient, predicate: Callable[[Any], bool], timeout: float = 1.0) -> Any:
    """一直查 `GET /api/downloads/auto-result`,直到 `predicate(result)` 成立或逾時;回傳最後一次的 `result`。"""
    deadline = time.monotonic() + timeout
    result = (await client.get("/api/downloads/auto-result")).json().get("result")
    while not predicate(result) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
        result = (await client.get("/api/downloads/auto-result")).json().get("result")
    return result


@pytest.mark.parametrize("how", ["使用者結束", "被收回"])
async def test_結束時自動下載的結果一併清掉_推_result_為_null_的_autoDownload_updated(
    live_servers: Any, fakes: Any, how: str
) -> None:
    # Arrange:精選清單有一項設了自動下載;開到就緒、等自動下載判定完成
    world = downloadable(fakes)
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "success"}])
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await client.post("/api/curated", json={"name": QWEN_MID, "autoDownload": True})
        name = (await open_ready(client))["name"]
        done = await wait_auto_result(client, lambda result: result is not None and result["state"] == "done")
        assert done is not None and done["enqueued"] == [QWEN_MID]  # 鋪陳:自動下載已經排入
        auto_ids = [job["id"] for job in (await queue(client))["jobs"] if job["origin"] == "auto"]
        async with subscribed(client) as feed:
            # Act
            if how == "使用者結束":
                await client.delete("/api/session")
            else:
                world.alive.remove(name)
                fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
                await wait_for_state(client, "lost")
            after = await client.get("/api/downloads/auto-result")
            events = await queue_events(feed, 0.5)

    # Assert
    assert (after.status_code, after.json()["result"]) == (200, None)  # 則1、則3
    updated = [payload["result"] for name, payload, _ in events if name == "autoDownload.updated"]
    assert updated == [None]  # 則2、則4
    removed = [payload["id"] for name, payload, _ in events if name == "download.removed"]
    assert len(auto_ids) == 1 and auto_ids[0] in removed  # 則5


# ---- 004 US1-API-14


def reject_runtime(world: ColabWorld, fakes: Any) -> None:
    """要 `L4` 的 `colab new` 被帳號拒絕,其他類型照常(照 US1-API-07)。"""

    def create(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["gpu"] == "L4":
            world.log.append(("create_session", kwargs["name"]))
            raise AdapterError("COLAB_ACCELERATOR_REJECTED", "帳號沒有這種加速器的額度")
        return world._create(*args, **kwargs)

    fakes.colab.create_session.side_effect(create)


@pytest.mark.parametrize("how", ["使用者結束", "閒置自動結束", "被收回", "重連逾時", "開啟失敗"])
async def test_每一種結束方式都立即推每一筆的移除_最後推一則空的快照(
    make_app: Callable[..., AppPair], start_live_servers: Callable[..., Any], fakes: Any, fake_clock: FakeClock, how: str
) -> None:
    # Arrange
    timeouts = replace(TEST_TIMEOUTS, reconnect_limit=0.3) if how == "重連逾時" else TEST_TIMEOUTS
    servers = start_live_servers(make_app(timeouts=timeouts))
    hold: Gate | None = None
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=5.0) as client:
        if how == "開啟失敗":
            world = ColabWorld(fakes)
            with_loaded_model(world, fakes)
            reject_runtime(world, fakes)
            old = (await open_ready(client))["name"]
            async with subscribed(client) as feed:
                # Act
                started_at = time.monotonic()
                await client.post("/api/session/restart", json={"runtimeType": L4})
                await wait_until(client, lambda s: s.get("name") != old and s.get("state") == "open_failed", timeout=1.0)
                events = await queue_events(feed, 1.0)
            queued_ids = {payload["job"]["id"] for name, payload, _ in events if name == "download.updated"}
        else:
            world = downloadable(fakes)
            if how == "閒置自動結束":
                await set_idle_timeout(client, 1)
            ready = await open_ready(client)
            hold, ids = await mixed_queue(client, fakes)
            queued_ids = set(ids)
            async with subscribed(client) as feed:
                # Act
                started_at = time.monotonic()
                if how == "使用者結束":
                    await client.delete("/api/session")
                elif how == "閒置自動結束":
                    fake_clock.set(parse_iso(ready["idle"]["deadline"]) + timedelta(seconds=1))
                elif how == "被收回":
                    world.alive.remove(ready["name"])
                    fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
                else:
                    record_rounds(world, fakes)
                    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
                    await wait_until(client, lambda s: s.get("state") == "reconnecting", timeout=1.0)
                    started_at = time.monotonic()
                events = await queue_events(feed, 1.0)
        after = await queue(client)
        if hold is not None:
            hold.release()

    # Assert
    removed = [(index, payload["id"]) for index, (name, payload, _) in enumerate(events) if name == "download.removed"]
    snapshots = [(index, payload, at) for index, (name, payload, at) in enumerate(events) if name == "downloads.snapshot"]
    assert {job_id for _, job_id in removed} == queued_ids  # 則1
    assert len(snapshots) == 1 and snapshots[0][0] > removed[-1][0]  # 則2
    assert snapshots[0][1]["queue"]["jobs"] == []  # 則3
    assert snapshots[0][2] - started_at < 1.0  # 則4
    failed = [p for name, p, _ in events if name == "download.updated" and p["job"]["reasonCode"] == "SESSION_ENDED"]
    assert failed == []  # 則5
    assert after["jobs"] == []  # 則6


# ---- 004 US1-API-15


async def test_結束中與結束後的各種操作都有明確的回應_不回_500(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:佇列有四種狀態的項目;結束停在結束中
    downloadable(fakes)
    stop_gate = fakes.colab.stop_session.gate()
    await open_ready(ui_client)
    hold, ids = await mixed_queue(ui_client, fakes)
    failed_id = ids[1]

    # Act
    await ui_client.delete("/api/session")
    listed = await ui_client.get("/api/downloads")
    retried = await ui_client.post(f"/api/downloads/{failed_id}/retry")
    enqueued = await ui_client.post("/api/downloads", json={"models": [QWEN_7B]})
    auto_result = await ui_client.get("/api/downloads/auto-result")
    fakes.colab.stop_session.raises("COLAB_UNREACHABLE", "連不到")
    stop_gate.release()
    ended = await wait_for_state(ui_client, "ended")
    after_ended = await ui_client.get("/api/downloads")
    hold.release()

    # Assert
    assert (listed.status_code, listed.json()["jobs"]) == (200, [])  # 則1
    assert (retried.status_code, error_code(retried)) == (404, "DOWNLOAD_NOT_FOUND")  # 則2
    assert (enqueued.status_code, error_code(enqueued)) == (503, "NO_READY_SESSION")  # 則3
    assert (auto_result.status_code, auto_result.json()["result"]) == (200, None)  # 則4
    assert ended["releaseWarning"] is not None  # 則5
    assert (after_ended.status_code, after_ended.json()["jobs"]) == (200, [])  # 則6
    statuses = [response.status_code for response in (listed, retried, enqueued, auto_result, after_ended)]
    assert all(status != 500 for status in statuses)  # 則7


# ---- 004 US1-API-競爭:取大小期間工作階段結束或換成另一個


async def post_while_sizing(client: httpx.AsyncClient, fakes: Any) -> tuple[Gate, "asyncio.Task[httpx.Response]"]:
    """加入 `qwen2.5:7b`,停在取 manifest 的閘門前(請求已通過開頭的就緒檢查);回傳 (閘門, 那個請求)。"""
    gate = fakes.model_library.get_manifest.gate()
    request = asyncio.create_task(client.post("/api/downloads", json={"models": [QWEN_7B]}))
    await gate.wait_entered_async(timeout=3.0)
    return gate, request


async def test_取大小期間結束工作階段_舊請求被拒_不重建佇列也不向舊通道下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    await open_ready(ui_client)
    gate, request = await post_while_sizing(ui_client, fakes)

    # Act:請求還在取大小時結束工作階段,再放行
    await ui_client.delete("/api/session")
    await wait_for_state(ui_client, "ended")
    gate.release()
    response = await request
    await asyncio.sleep(0.2)

    # Assert
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")  # 則1
    assert (await queue(ui_client))["jobs"] == []  # 則2
    assert fakes.remote_ollama.pull_model.call_count == 0  # 則3


async def test_取大小期間換成另一個工作階段_舊請求被拒_項目不會記到新的工作階段(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    old = (await open_ready(ui_client))["name"]
    gate, request = await post_while_sizing(ui_client, fakes)

    # Act:結束舊的、開好新的,再放行舊請求
    await ui_client.delete("/api/session")
    await wait_for_state(ui_client, "ended")
    new = await open_ready(ui_client)
    gate.release()
    response = await request
    await asyncio.sleep(0.2)

    # Assert
    assert new["name"] != old  # 前提:真的是另一個工作階段
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")  # 則1
    assert (await queue(ui_client))["jobs"] == []  # 則2
    assert fakes.remote_ollama.pull_model.call_count == 0  # 則3
