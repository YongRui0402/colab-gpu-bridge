"""E2 後端 UI API:變更執行階段類型並重開(testplan.md § 2.1,`/api/session` › 變更類型;FR-010)。

接縫:HTTP `/api/*`,五個轉接層用替身。
"""

import asyncio
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError

from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
    wait_until,
)

L4 = {"gpu": "L4", "highMem": False}
QWEN_SMALL = "qwen2.5:0.5b"
QWEN_SMALL_BYTES = 397_821_319


def with_loaded_model(world: ColabWorld, fakes: Any) -> None:
    """執行環境上已下載並載入 `qwen2.5:0.5b`;下載與預先載入的呼叫記進 `world.log`。"""
    remote = fakes.remote_ollama
    remote.list_loaded_models.side_effect(
        lambda *a, **k: {"models": [{"name": QWEN_SMALL, "model": QWEN_SMALL, "size": QWEN_SMALL_BYTES}]}
    )
    remote.list_local_models.side_effect(
        lambda *a, **k: {"models": [{"name": QWEN_SMALL, "model": QWEN_SMALL, "size": QWEN_SMALL_BYTES}]}
    )

    def pull(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        world.log.append(("pull_model", kwargs.get("model")))
        return [{"status": "pulling manifest"}, {"status": "success"}]

    def preload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        world.log.append(("preload", kwargs.get("model")))
        return {"model": kwargs.get("model"), "done": True}

    remote.pull_model.side_effect(pull)
    remote.preload.side_effect(preload)


async def history_record(client: httpx.AsyncClient, name: str) -> dict[str, Any]:
    items = (await client.get("/api/sessions")).json().get("items", [])
    return next((item for item in items if item.get("name") == name), {})


# ---------------------------------------------------------------- US1-API-27


async def test_變更類型先關舊的再開新的_並重新下載原本載入的模型(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    with_loaded_model(world, fakes)
    old = (await open_ready(ui_client))["name"]

    # Act
    response = await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    accepted = response.json()
    final = await wait_until(ui_client, lambda s: s.get("state") == "ready" and s.get("name") != old)
    await wait_until(ui_client, lambda s: bool(world.calls("preload")))
    old_record = await history_record(ui_client, old)
    queue = (await ui_client.get("/api/downloads")).json()

    # Assert
    assert (response.status_code, accepted.get("state"), accepted.get("step")) == (202, "opening", "ending_previous")
    assert old_record.get("endReason") == "RUNTIME_TYPE_CHANGED"
    stopped_then_created = [(m, a) for m, a in world.log if (m, a) == ("stop_session", old) or m == "create_session"]
    assert stopped_then_created[-2:] == [("stop_session", old), ("create_session", final.get("name"))]
    assert fakes.colab.create_session.last_call.kwargs["gpu"] == "L4"
    jobs = [job for job in queue.get("jobs", []) if job.get("model") == QWEN_SMALL]
    assert [(job.get("origin"), job.get("preloadOnComplete")) for job in jobs] == [("restore", True)]
    assert [(m, a) for m, a in world.log if m in ("pull_model", "preload")] == [("pull_model", QWEN_SMALL), ("preload", QWEN_SMALL)]


# ---------------------------------------------------------------- US1-API-28


async def test_新類型開不起來時舊的已結束_要重新下載的項目留在佇列(ui_client: httpx.AsyncClient, fakes: Any) -> None:
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
    final = await wait_until(ui_client, lambda s: s.get("name") != old and s.get("state") == "open_failed")
    listed = await fakes.colab.list_sessions()
    queue = (await ui_client.get("/api/downloads")).json()

    # Assert
    assert (final.get("state"), final.get("reasonCode")) == ("open_failed", "COLAB_ACCELERATOR_REJECTED")
    assert old in world.calls("stop_session")
    assert old not in [entry["name"] for entry in listed["named"]]
    restore = [job for job in queue.get("jobs", []) if job.get("model") == QWEN_SMALL and job.get("origin") == "restore"]
    assert [job.get("state") for job in restore] == ["queued"]


# ---------------------------------------------------------------- US1-API-29


async def test_沒有工作階段時變更類型回錯誤_不當成開啟(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)

    # Act
    response = await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    await asyncio.sleep(0.1)

    # Assert
    assert (response.status_code, error_code(response)) == (409, "NO_ACTIVE_SESSION")
    assert fakes.colab.create_session.call_count == 0
