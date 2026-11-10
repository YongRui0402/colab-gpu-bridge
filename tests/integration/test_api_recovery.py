"""E2 後端 UI API:後端重新啟動後接回(testplan.md § 2.1,後端行程 › 重新啟動)。

接縫:HTTP `/api/*`;「重新啟動」是關掉 app,再以同一個 SQLite 檔與同一份轉接層替身狀態建立新的 app。
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from cgb.app import AppPair
from fakes import Gate
from integration.test_api_downloads import downloadable, queue, states, wait_queue
from integration.test_api_models import QWEN_7B, QWEN_SMALL
from integration.test_api_session import T4, ColabWorld, get_session, open_ready, wait_until


@asynccontextmanager
async def running(pair: AppPair) -> AsyncIterator[httpx.AsyncClient]:
    """跑一個 app(含 lifespan),離開時關掉它。"""
    async with pair.ui.router.lifespan_context(pair.ui):
        transport = httpx.ASGITransport(app=pair.ui, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://cgb-ui.test") as client:
            yield client


def reset_calls(fakes: Any) -> None:
    for adapter in (fakes.colab, fakes.tunnel, fakes.remote_ollama):
        for method in adapter.METHODS:
            adapter.method(method).reset_calls()


# ---------------------------------------------------------------- US1-API-23


async def test_重啟後接回仍在的工作階段_先清殘留再建立通道(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        name = (await open_ready(client))["name"]
    reset_calls(fakes)
    world.log.clear()

    # Act
    async with running(make_app()) as client:
        session = await wait_until(client, lambda s: s.get("state") == "ready" and bool(world.calls("open_tunnel")))

    # Assert
    assert (session.get("state"), session.get("name")) == ("ready", name)
    assert fakes.colab.create_session.call_count == 0
    order = [method for method, _ in world.log if method in ("cleanup_residual", "open_tunnel")]
    assert order == ["cleanup_residual", "open_tunnel"]


# ---------------------------------------------------------------- US1-API-24


async def test_重啟後執行環境已不在時判定被收回_不建立通道(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        name = (await open_ready(client))["name"]
    world.alive.remove(name)
    reset_calls(fakes)

    # Act
    async with running(make_app()) as client:
        session = await wait_until(client, lambda s: s.get("state") != "ready", timeout=1.0)

    # Assert
    assert (session.get("state"), session.get("endReason")) == ("lost", "RECLAIMED_BY_COLAB")
    assert fakes.tunnel.open_tunnel.call_count == 0


# ---------------------------------------------------------------- US1-API-25


async def test_重啟時發現不是本系統開的執行環境只提示_不接手不關閉(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:沒有未結束的工作階段;Colab 帳號下有一台名稱是 `?` 的 T4
    world = ColabWorld(fakes)
    world.unnamed.append({"hardware": "T4", "shape": "Standard", "variant": "GPU"})

    # Act
    async with running(make_app()) as client:
        session = await wait_until(client, lambda s: bool(s.get("unmanagedRuntimes")), timeout=1.0)

    # Assert
    runtimes = session.get("unmanagedRuntimes") or []
    assert [r.get("hardware") for r in runtimes] == ["T4"]
    assert fakes.colab.stop_session.call_count == 0
    assert fakes.tunnel.open_tunnel.call_count == 0


# ---------------------------------------------------------------- US1-API-26


async def test_重啟時只釋放資料庫認得且已結束的那台_資料庫不認得的只提示(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:資料庫有一筆已結束的與一筆就緒的;Colab 帳號下兩台都還在,另有一台別的實例開的
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        await open_ready(client)
        await client.delete("/api/session")
        ended = await wait_until(client, lambda s: s.get("state") == "ended")
        ready = await open_ready(client)
    world.alive += [ended["name"], "cgb-other-9"]
    world.hardware["cgb-other-9"] = "L4"
    reset_calls(fakes)
    world.log.clear()

    # Act
    async with running(make_app()) as client:
        session = await wait_until(
            client, lambda s: bool(s.get("unmanagedRuntimes")) and bool(world.calls("stop_session")), timeout=1.0
        )

    # Assert
    assert ended["name"] in world.calls("stop_session")
    assert ready["name"] not in world.calls("stop_session")
    assert "cgb-other-9" not in world.calls("stop_session")
    runtimes = session.get("unmanagedRuntimes") or []
    assert [r.get("hardware") for r in runtimes] == ["L4"]
    assert runtimes[0].get("detectedAt") is not None


# ---------------------------------------------------------------- US3-API-25


async def test_重啟時下載中的那筆回到排隊中_接回後重新下載且順序不變(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:qwen2.5:7b 下載中(pull 停在閘門前),qwen2.5:0.5b 排在它後面
    downloadable(fakes)
    hold = Gate()
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "pulling manifest"}, hold, {"status": "success"}])
    async with running(make_app()) as client:
        await open_ready(client)
        await client.post("/api/downloads", json={"models": [QWEN_7B, QWEN_SMALL]})
        before = await wait_queue(client, lambda q: states(q)[:1] == [(QWEN_7B, "downloading")])
    hold.release()
    fakes.remote_ollama.pull_model.reset_calls()
    reattach = fakes.tunnel.open_tunnel.gate()

    # Act
    async with running(make_app()) as client:
        after_restart = await queue(client)
        reattach.release()
        await wait_until(client, lambda s: s.get("state") == "ready")
        resumed = await wait_queue(client, lambda q: [s for _, s in states(q)] == ["completed", "completed"])

    # Assert
    assert states(after_restart)[:1] == [(QWEN_7B, "queued")]
    pulled = [call.kwargs.get("model") for call in fakes.remote_ollama.pull_model.calls]
    assert pulled[:1] == [QWEN_7B]
    assert [job["id"] for job in resumed["jobs"]] == [job["id"] for job in before["jobs"]]


# ---------------------------------------------------------------- US4-API-19


async def test_啟動期間開啟的工作階段不會被接回誤判為被收回(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:資料庫沒有未結束的工作階段;`colab sessions` 與 `colab new` 都停在閘門前
    world = ColabWorld(fakes)
    listing = fakes.colab.list_sessions.gate()
    creating = fakes.colab.create_session.gate()

    async with running(make_app()) as client:
        # Act:啟動時接回的那次 `colab sessions` 停住期間開啟;開啟流程的 `colab sessions` 也走到閘門前才放行
        await listing.wait_entered_async(1)
        response = await client.post("/api/session", json={"runtimeType": T4})
        await listing.wait_entered_async(2)
        listing.release()
        await creating.wait_entered_async(1)
        while_creating = await sessions_for(client, 0.3)
        creating.release()
        ready = await wait_until(client, lambda s: s.get("state") == "ready")
        history = (await client.get("/api/sessions")).json()

    # Assert:則1
    assert response.status_code == 202, response.text
    seen = [(s.get("state"), s.get("endReason")) for s in while_creating]
    assert [state for state, _ in seen if state == "lost"] == [], seen
    assert {reason for _, reason in seen} == {None}, seen
    # Assert:則2
    assert (ready.get("state"), ready.get("endReason")) == ("ready", None), ready
    # Assert:則3
    assert world.calls("stop_session") == []
    record = next(item for item in history["items"] if item["name"] == ready["name"])
    assert record.get("endReason") != "RECLAIMED_BY_COLAB", record


async def sessions_for(client: httpx.AsyncClient, seconds: float) -> list[dict[str, Any]]:
    """在一段真實時間內一直查 `GET /api/session`,回傳看到的每一份。"""
    seen: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    until = loop.time() + seconds
    while loop.time() < until:
        seen.append(await get_session(client))
        await asyncio.sleep(0.02)
    return seen
