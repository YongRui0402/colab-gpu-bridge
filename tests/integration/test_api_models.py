"""E2 後端 UI API:模型目錄與預先載入(testplan.md § 4.1,`/api/models` › 列出目錄、`/api/models` › 預先載入)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身(testplan.md § 接縫的取捨)。
「假伺服器的 tags、ps」是 `FakeRemoteOllama.list_local_models`、`list_loaded_models` 的回傳。
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from integration.test_api_events import sse_events
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
    wait_for_state,
)

QWEN_SMALL = "qwen2.5:0.5b"
QWEN_SMALL_BYTES = 397_821_319
QWEN_7B = "qwen2.5:7b"
QWEN_7B_BYTES = 4_683_087_332
DISK_FREE = 225_485_783_040
VRAM_TOTAL = 16_106_127_360


def tag(name: str, size: int) -> dict[str, Any]:
    """`/api/tags` 的一筆模型(remote-ollama.openapi.yaml § LocalModel)。"""
    return {"name": name, "model": name, "size": size, "modified_at": "2026-11-09T09:10:00Z"}


def resources(disk_free: int = DISK_FREE, vram_total: int | None = VRAM_TOTAL) -> dict[str, Any]:
    """S8 `probe_resources` 的回傳(colab-cli.openapi.yaml § RuntimeResources)。"""
    return {
        "diskFreeBytes": disk_free,
        "diskTotalBytes": 253_338_115_072,
        "gpuName": "Tesla T4" if vram_total is not None else None,
        "vramTotalBytes": vram_total,
        "vramFreeBytes": 15_727_591_424 if vram_total is not None else None,
        "checkedAt": "2026-11-09T09:00:00Z",
    }


def set_tags(fakes: Any, *models: dict[str, Any]) -> None:
    fakes.remote_ollama.list_local_models.side_effect(lambda *a, **k: {"models": list(models)})


def set_loaded(fakes: Any, *names: str) -> None:
    fakes.remote_ollama.list_loaded_models.side_effect(
        lambda *a, **k: {"models": [{"name": n, "model": n, "size": 0} for n in names]}
    )


async def next_event(
    events: AsyncIterator[tuple[str, dict[str, Any]]],
    name: str,
    predicate: Callable[[dict[str, Any]], bool] = lambda _: True,
    timeout: float = 3.0,
) -> dict[str, Any] | None:
    """讀到下一則名稱是 `name`、且 `predicate(payload)` 成立的事件;逾時回 None。"""

    async def find() -> dict[str, Any] | None:
        async for event, payload in events:
            if event == name and predicate(payload):
                return payload
        return None

    try:
        return await asyncio.wait_for(find(), timeout)
    except TimeoutError:
        return None


def by_name(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in catalog.get("items", [])}


# ---------------------------------------------------------------- US3-API-01


async def test_目錄列出已下載的模型_大小照實_載入狀態照_ps(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES), tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes, QWEN_SMALL)

    # Act
    response = await ui_client.get("/api/models")
    items = by_name(response.json())

    # Assert
    assert response.status_code == 200
    assert {name: item["sizeBytes"] for name, item in items.items()} == {QWEN_SMALL: QWEN_SMALL_BYTES, QWEN_7B: QWEN_7B_BYTES}
    assert items[QWEN_SMALL]["loaded"] is True
    assert items[QWEN_7B]["loaded"] is False


# ---------------------------------------------------------------- US3-API-02


async def test_重連中列目錄回_503_不去連轉發位址(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:健康檢查失敗進入重連,重建通道停在閘門前
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))
    set_loaded(fakes)
    fakes.tunnel.open_tunnel.gate()
    fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
    session = await wait_for_state(ui_client, "reconnecting")
    remote = fakes.remote_ollama
    remote.list_local_models.reset_calls()
    remote.list_loaded_models.reset_calls()

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert session.get("state") == "reconnecting"
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")
    assert (remote.list_local_models.call_count, remote.list_loaded_models.call_count) == (0, 0)


# ---------------------------------------------------------------- US3-API-03


async def test_預先載入只送_model_與_keep_alive_負一_載入後推送已載入(live_servers: Any, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    remote = fakes.remote_ollama
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
        set_loaded(fakes)
        gate = remote.preload.gate()
        remote.preload.returns({"model": QWEN_7B, "done": True})

        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await next_event(events, "session.updated")

            # Act
            response = await client.post("/api/models/preload", json={"name": QWEN_7B})
            await gate.wait_entered_async()
            preload_call = remote.preload.last_call.kwargs
            set_loaded(fakes, QWEN_7B)
            gate.release()
            updated = await next_event(
                events, "models.updated", lambda p: by_name(p.get("catalog", {})).get(QWEN_7B, {}).get("loaded") is True
            )

    # Assert
    assert (response.status_code, response.json().get("preload", {}).get("state")) == (202, "loading")
    assert {k: v for k, v in preload_call.items() if k != "base_url"} == {"model": QWEN_7B}
    assert remote.generate.call_count == 0
    assert updated is not None


# ---------------------------------------------------------------- US3-API-04


async def test_目錄沒有的模型不能預先載入_也不會順手下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))
    set_loaded(fakes)
    remote = fakes.remote_ollama
    remote.preload.returns({"model": QWEN_7B, "done": True})
    remote.pull_model.returns([{"status": "success"}])

    # Act
    response = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})
    await asyncio.sleep(0.1)

    # Assert
    assert (response.status_code, error_code(response)) == (404, "OLLAMA_NOT_FOUND")
    assert remote.pull_model.call_count == 0


async def poll_catalog(client: httpx.AsyncClient, predicate: Callable[[dict[str, Any]], bool], timeout: float = 3.0) -> dict[str, Any]:
    """一直查 `GET /api/models`,直到 `predicate(目錄)` 成立或逾時;回傳最後一次看到的。"""
    deadline = asyncio.get_running_loop().time() + timeout
    catalog = (await client.get("/api/models")).json()
    while not predicate(catalog) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
        catalog = (await client.get("/api/models")).json()
    return catalog


# ---------------------------------------------------------------- US3-API-05


async def test_預先載入失敗只標那個模型_其他已載入的不受影響(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES), tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes, QWEN_SMALL)
    fakes.remote_ollama.preload.raises("OLLAMA_SERVER_ERROR", "model requires more system memory")

    # Act
    await ui_client.post("/api/models/preload", json={"name": QWEN_7B})
    catalog = await poll_catalog(ui_client, lambda c: by_name(c).get(QWEN_7B, {}).get("preload", {}).get("state") == "failed")
    items = by_name(catalog)

    # Assert
    preload = items.get(QWEN_7B, {}).get("preload", {})
    assert (preload.get("state"), preload.get("reasonCode")) == ("failed", "OLLAMA_SERVER_ERROR")
    assert items.get(QWEN_SMALL, {}).get("loaded") is True


# ---------------------------------------------------------------- US3-API-06


async def test_連按兩次預先載入只送一次載入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    remote = fakes.remote_ollama
    gate = remote.preload.gate()
    remote.preload.returns({"model": QWEN_7B, "done": True})

    # Act
    first = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})
    await gate.wait_entered_async()
    second = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})
    await asyncio.sleep(0.1)
    gate.release()

    # Assert
    assert (first.status_code, second.status_code) == (202, 202)
    assert remote.preload.call_count == 1


# ---------------------------------------------------------------- US3-API-26


async def test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:顯示記憶體總量 16,106,127,360;qwen2.5:7b 已載入
    big = "cgb-test-big:70b"
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES), tag(big, 20_000_000_000))
    set_loaded(fakes, QWEN_7B)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))

    # Act
    first = by_name((await ui_client.get("/api/models")).json())
    fakes.colab.probe_resources.returns(resources(vram_total=None))
    second = by_name((await ui_client.get("/api/models")).json())

    # Assert
    assert first.get(big, {}).get("mayNotFit") is True
    assert first.get(QWEN_7B, {}).get("mayNotFit") is False
    assert (second.get(big, {}).get("mayNotFit"), second.get(QWEN_7B, {}).get("mayNotFit")) == (None, None)
