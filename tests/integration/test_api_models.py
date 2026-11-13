"""E2 後端 UI API:模型目錄與預先載入(testplan.md § 4.1,`/api/models` › 列出目錄、`/api/models` › 預先載入)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身(testplan.md § 接縫的取捨)。
「假伺服器的 tags、ps」是 `FakeRemoteOllama.list_local_models`、`list_loaded_models` 的回傳。
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.app import AppPair
from integration.test_api_events import sse_events
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
    wait_for_state,
    wait_until,
)

QWEN_SMALL = "qwen2.5:0.5b"
QWEN_SMALL_BYTES = 397_821_319
QWEN_7B = "qwen2.5:7b"
QWEN_7B_BYTES = 4_683_087_332
DISK_FREE = 225_485_783_040
VRAM_TOTAL = 16_106_127_360
L4_VRAM = 24_152_899_584
L4 = {"gpu": "L4", "highMem": False}


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


# ---------------------------------------------------------------- 003 US2-API-07(原 US3-API-26,Q18 原地改寫)


async def test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:這個工作階段第一次讀到 null、之後讀到 16,106,127,360;qwen2.5:7b 已載入
    big = "cgb-test-big:70b"
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES), tag(big, 20_000_000_000))
    set_loaded(fakes, QWEN_7B)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
    fakes.colab.probe_resources.then(resources(vram_total=None))
    fakes.colab.probe_resources.reset_calls()

    # Act
    responses = [await ui_client.get("/api/models") for _ in range(3)]
    first, second = (by_name(r.json()) for r in responses[:2])

    # Assert
    assert responses[0].status_code == 200
    assert responses[0].json()["vramBytes"] is None
    assert (first[big]["mayNotFit"], first[QWEN_7B]["mayNotFit"]) == (None, None)
    assert responses[1].json()["vramBytes"] == 16_106_127_360
    assert second[big]["mayNotFit"] is True
    assert second[QWEN_7B]["mayNotFit"] is False
    assert responses[2].json()["vramBytes"] == 16_106_127_360
    assert fakes.colab.probe_resources.call_count == 2


# ---------------------------------------------------------------- 003 US2-API-01


async def test_同一個工作階段連續列目錄只讀一次顯示記憶體(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
    fakes.colab.probe_resources.reset_calls()

    # Act
    responses = [await ui_client.get("/api/models") for _ in range(3)]

    # Assert
    assert responses[0].status_code == 200
    assert responses[0].json()["vramBytes"] == 16_106_127_360
    assert fakes.colab.probe_resources.call_count == 1
    assert fakes.colab.probe_resources.last_call.kwargs["name"] == name
    assert responses[2].json()["vramBytes"] == 16_106_127_360


# ---------------------------------------------------------------- 003 US2-API-02


async def test_沿用顯示記憶體時新下載與剛載入的模型照現況列出(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:已讀過一次顯示記憶體,目錄裡只有 qwen2.5:7b
    big = "cgb-test-big:70b"
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
    fakes.colab.probe_resources.reset_calls()
    await ui_client.get("/api/models")
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES), tag(big, 20_000_000_000))
    set_loaded(fakes, QWEN_7B)

    # Act
    items = by_name((await ui_client.get("/api/models")).json())

    # Assert
    assert big in items
    assert items[QWEN_7B]["loaded"] is True
    assert items[big]["mayNotFit"] is True
    assert fakes.colab.probe_resources.call_count == 1


# ---------------------------------------------------------------- 003 US2-API-03


async def test_預先載入結束的推送沿用顯示記憶體_不再讀一次(live_servers: Any, fakes: Any) -> None:
    # Arrange:已讀過一次顯示記憶體
    ColabWorld(fakes)
    remote = fakes.remote_ollama
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
        set_loaded(fakes)
        fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
        gate = remote.preload.gate()
        remote.preload.returns({"model": QWEN_7B, "done": True})
        await client.get("/api/models")
        fakes.colab.probe_resources.reset_calls()

        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await next_event(events, "session.updated")

            # Act
            response = await client.post("/api/models/preload", json={"name": QWEN_7B})
            await gate.wait_entered_async()
            set_loaded(fakes, QWEN_7B)
            gate.release()
            updated = await next_event(
                events, "models.updated", lambda p: by_name(p.get("catalog", {})).get(QWEN_7B, {}).get("loaded") is True
            )

    # Assert
    assert response.status_code == 202
    assert updated is not None
    assert updated["catalog"]["vramBytes"] == 16_106_127_360
    assert fakes.colab.probe_resources.call_count == 0


# ---------------------------------------------------------------- 003 US2-API-04


async def test_變更類型換了工作階段就重新讀顯示記憶體(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:T4 讀到 16,106,127,360;換成 L4 後新的工作階段顯示記憶體是 24,152,899,584
    big = "cgb-test-big:70b"
    ColabWorld(fakes)
    old = (await open_ready(ui_client))["name"]
    set_tags(fakes, tag(big, 20_000_000_000))
    set_loaded(fakes)
    fakes.colab.probe_resources.when(name=old).returns(resources(vram_total=VRAM_TOTAL))
    fakes.colab.probe_resources.returns(resources(vram_total=L4_VRAM))
    await ui_client.get("/api/models")
    await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    new = await wait_until(ui_client, lambda s: s.get("state") == "ready" and s.get("name") != old)
    fakes.colab.probe_resources.reset_calls()

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert fakes.colab.probe_resources.call_count == 1
    assert fakes.colab.probe_resources.last_call.kwargs["name"] == new["name"]
    assert response.json()["vramBytes"] == 24_152_899_584
    assert by_name(response.json())[big]["mayNotFit"] is False


# ---------------------------------------------------------------- 003 US2-API-05


async def test_新工作階段第一次讀不到顯示記憶體時回_null_不拿上一個工作階段的值頂替(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange:舊工作階段讀到 16,106,127,360 後結束,新的工作階段第一次讀逾時
    big = "cgb-test-big:70b"
    ColabWorld(fakes)
    old = (await open_ready(ui_client))["name"]
    set_tags(fakes, tag(big, 20_000_000_000))
    set_loaded(fakes)
    fakes.colab.probe_resources.when(name=old).returns(resources(vram_total=VRAM_TOTAL))
    fakes.colab.probe_resources.returns(resources(vram_total=L4_VRAM))
    await ui_client.get("/api/models")
    await ui_client.delete("/api/session")
    await wait_for_state(ui_client, "ended")
    await open_ready(ui_client)
    fakes.colab.probe_resources.reset_calls()
    fakes.colab.probe_resources.then(AdapterError("COLAB_TIMEOUT", "timed out"))

    # Act
    first = await ui_client.get("/api/models")
    second = await ui_client.get("/api/models")

    # Assert
    assert first.status_code == 200
    assert first.json()["vramBytes"] is None
    assert by_name(first.json())[big]["mayNotFit"] is None
    assert second.json()["vramBytes"] == 24_152_899_584
    assert fakes.colab.probe_resources.call_count == 2


# ---------------------------------------------------------------- 003 US2-API-06


async def test_重連中列目錄回_503_接回同一個工作階段後沿用顯示記憶體(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:讀過一次顯示記憶體後,健康檢查失敗進入重連,重建通道停在閘門前
    ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
    await ui_client.get("/api/models")
    gate = fakes.tunnel.open_tunnel.gate()
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
    await wait_for_state(ui_client, "reconnecting")
    fakes.colab.probe_resources.reset_calls()

    # Act
    during = await ui_client.get("/api/models")
    gate.release()
    session = await wait_for_state(ui_client, "ready")
    after = await ui_client.get("/api/models")

    # Assert
    assert (during.status_code, error_code(during)) == (503, "NO_READY_SESSION")
    assert session["name"] == name
    assert after.status_code == 200
    assert after.json()["vramBytes"] == 16_106_127_360
    assert fakes.colab.probe_resources.call_count == 0


# ---------------------------------------------------------------- 003 US2-API-08


@asynccontextmanager
async def running(pair: AppPair) -> AsyncIterator[httpx.AsyncClient]:
    """跑一個 app(含 lifespan),離開時關掉它(寫法同 `test_api_recovery.py`)。"""
    async with pair.ui.router.lifespan_context(pair.ui):
        transport = httpx.ASGITransport(app=pair.ui, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://cgb-ui.test") as client:
            yield client


async def test_後端重新啟動後接回同一個工作階段_重新讀一次顯示記憶體(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:第一個 app 讀過一次顯示記憶體後關掉
    world = ColabWorld(fakes)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
    async with running(make_app()) as client:
        name = (await open_ready(client))["name"]
        await client.get("/api/models")
    world.log.clear()

    # Act:接回的通道重建好之後才列目錄
    async with running(make_app()) as client:
        await wait_until(
            client, lambda s: s.get("state") == "ready" and s.get("name") == name and bool(world.calls("open_tunnel"))
        )
        fakes.colab.probe_resources.reset_calls()
        response = await client.get("/api/models")

    # Assert
    assert fakes.colab.probe_resources.call_count == 1
    assert fakes.colab.probe_resources.last_call.kwargs["name"] == name
    assert response.json()["vramBytes"] == 16_106_127_360


# ---------------------------------------------------------------- 003 US2-API-09


async def test_試算只讀剩餘空間_不動模型目錄沿用的顯示記憶體(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:第一次試算時 `probe_resources` 回顯示記憶體 8,000,000,000,之後回 16,106,127,360
    # 函式內才匯入:`test_api_downloads` 本身匯入這個模組,放在檔案開頭會循環匯入
    from integration.test_api_downloads import downloadable

    downloadable(fakes)
    await open_ready(ui_client)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
    fakes.colab.probe_resources.then(resources(vram_total=8_000_000_000))
    fakes.colab.probe_resources.reset_calls()

    # Act
    first = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5:7b"]})
    catalog = await ui_client.get("/api/models")
    calls_after_catalog = fakes.colab.probe_resources.call_count
    fakes.colab.probe_resources.returns(resources(disk_free=100_000_000_000, vram_total=VRAM_TOTAL))
    second = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5:7b"]})

    # Assert
    assert first.status_code == 200
    assert catalog.json()["vramBytes"] == 16_106_127_360
    assert calls_after_catalog == 2
    assert second.json()["freeDiskBytes"] == 100_000_000_000
    assert fakes.colab.probe_resources.call_count == 3


async def slow_probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """讀顯示記憶體要 0.3 秒的 `probe_resources`(`plan.md` Q9)。"""
    await asyncio.sleep(0.3)
    return resources(vram_total=VRAM_TOTAL)


# ---------------------------------------------------------------- 003 US2-API-10


async def test_同時兩個第一次列目錄都讀到顯示記憶體_之後沿用(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:讀一次要 0.3 秒
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.side_effect(slow_probe)
    fakes.colab.probe_resources.reset_calls()

    # Act
    together = await asyncio.gather(ui_client.get("/api/models"), ui_client.get("/api/models"))
    calls_after_together = fakes.colab.probe_resources.call_count
    await ui_client.get("/api/models")

    # Assert
    assert [r.status_code for r in together] == [200, 200]
    assert [r.json()["vramBytes"] for r in together] == [16_106_127_360, 16_106_127_360]
    assert 1 <= calls_after_together <= 2
    assert fakes.colab.probe_resources.call_count == calls_after_together


# ---------------------------------------------------------------- 003 US2-API-11

PROBE_ERROR_CODES = [
    "COLAB_TIMEOUT",
    "COLAB_REMOTE_ERROR",
    "COLAB_UNREACHABLE",
    "COLAB_FAILED",
    "COLAB_BAD_RESPONSE",
    "COLAB_NOT_FOUND",
    "COLAB_NOT_INSTALLED",
    "AUTH_REQUIRED",
]


@pytest.mark.parametrize("code", PROBE_ERROR_CODES)
async def test_讀顯示記憶體失敗時目錄照常列出_顯示記憶體是_null_下一次再讀(
    ui_client: httpx.AsyncClient, fakes: Any, code: str
) -> None:
    # Arrange:第一次讀顯示記憶體丟出這個代碼,之後讀到 16,106,127,360
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.returns(resources(vram_total=VRAM_TOTAL))
    fakes.colab.probe_resources.then(AdapterError(code, "Traceback (most recent call last)"))
    fakes.colab.probe_resources.reset_calls()

    # Act
    responses = [await ui_client.get("/api/models") for _ in range(3)]

    # Assert
    assert responses[0].status_code == 200
    assert responses[0].json()["vramBytes"] is None
    assert by_name(responses[0].json())[QWEN_7B]["mayNotFit"] is None
    assert [item["name"] for item in responses[0].json()["items"]] == [QWEN_7B]
    assert responses[1].json()["vramBytes"] == 16_106_127_360
    assert fakes.colab.probe_resources.call_count == 2


# ---------------------------------------------------------------- 003 US2-API-12


async def test_讀過顯示記憶體之後列目錄不再等_colab_exec(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:讀一次顯示記憶體要 0.3 秒
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.side_effect(slow_probe)
    fakes.colab.probe_resources.reset_calls()

    # Act
    elapsed: list[float] = []
    responses: list[httpx.Response] = []
    for _ in range(10):
        started = time.monotonic()
        responses.append(await ui_client.get("/api/models"))
        elapsed.append(time.monotonic() - started)

    # Assert
    assert elapsed[0] >= 0.3
    assert max(elapsed[1:]) < 0.15
    assert fakes.colab.probe_resources.call_count == 1
    assert {r.json()["vramBytes"] for r in responses} == {16_106_127_360}
