"""E2 後端 UI API:自動下載(testplan.md § 4.1,`/api/session` 就緒時排入、`/api/downloads`、`/api/downloads/auto-result`)。

接縫:HTTP `/api/*`,五個轉接層與 Hugging Face 替身(`FakeHuggingFaceHub`);精選清單與自動下載結果存在 SQLite。
`set_hf`、`curate`、`wait_auto` 與 `HF_SMOL` 取自 `test_api_curated.py`(testplan.md § 4.1)。
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError
from integration.test_api_curated import HF_SMOL, HF_SMOL_BYTES, curate, set_hf, wait_auto
from integration.test_api_downloads import LATEST_SIZES, downloadable, hold_pulls, queue, set_library
from integration.test_api_events import sse_events
from integration.test_api_models import L4, VRAM_TOTAL, resources, set_loaded, set_tags, tag
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    open_ready,
    ui_client,
    wait_until,
)


@asynccontextmanager
async def collect_events(base_url: str) -> AsyncIterator[list[tuple[str, dict[str, Any]]]]:
    """背景讀 `GET /api/events`,把每一則事件(名稱、內容)依序記進回傳的清單;連上時的快照到齊之後才交出清單。"""
    received: list[tuple[str, dict[str, Any]]] = []

    async def read() -> None:
        async with httpx.AsyncClient(base_url=base_url, timeout=None) as client, client.stream("GET", "/api/events") as response:
            async for event in sse_events(response):
                received.append(event)

    task = asyncio.create_task(read())
    try:
        deadline = time.monotonic() + 1.0
        while not received and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        received.clear()
        yield received
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def wait_event(
    events: list[tuple[str, dict[str, Any]]], name: str, predicate: Callable[[dict[str, Any]], bool] = lambda _: True, timeout: float = 1.0
) -> dict[str, Any] | None:
    """等 `events` 出現名稱為 `name` 且 `predicate(內容)` 成立的事件;逾時回 None。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event_name, payload in list(events):
            if event_name == name and predicate(payload):
                return payload
        await asyncio.sleep(0.01)
    return None


async def wait_calls(method: Any, count: int = 1, timeout: float = 1.0) -> None:
    """等替身方法被呼叫到 `count` 次(下載在背景開始)。"""
    deadline = time.monotonic() + timeout
    while method.call_count < count and time.monotonic() < deadline:
        await asyncio.sleep(0.01)


# ---- 004 US3-API-12


async def test_第一次就緒時依清單順序排入設了自動下載的項目_hf_名稱向_Hugging_Face_取大小(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange:沒有工作階段時依序新增三項
    downloadable(fakes)
    set_library(fakes)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:7b", auto=True)
    await curate(ui_client, "qwen2.5:1.5b", auto=False)
    await curate(ui_client, HF_SMOL, auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    await wait_calls(fakes.remote_ollama.pull_model)
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert [job["model"] for job in jobs] == ["qwen2.5:7b", HF_SMOL]  # 則1
    assert [job["origin"] for job in jobs] == ["auto", "auto"]  # 則2
    assert [job["preloadOnComplete"] for job in jobs] == [False, False]  # 則3
    assert [job.get("source") for job in jobs] == ["library", "huggingface"]  # 則4
    assert result is not None and result["enqueued"] == ["qwen2.5:7b", HF_SMOL]  # 則5
    assert result["skipped"] == []  # 則6
    library_calls = fakes.model_library.get_manifest.calls
    assert not [c for c in library_calls if c.kwargs.get("tag") == "1.5b"]  # 則7
    hf_calls = fakes.huggingface.get_manifest.calls
    assert [c.kwargs.get("tag") for c in hf_calls] == ["Q4_K_M"]  # 則8
    assert not [c for c in library_calls if str(c.kwargs.get("name")).startswith("hf.co/")]  # 則9
    assert fakes.remote_ollama.pull_model.calls[0].kwargs.get("model") == "qwen2.5:7b"  # 則10


# ---- 004 US3-API-13


async def test_執行環境上已有的項目不排_大小寫不同也算已有_也不取大小(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:執行環境上已有 `hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m`(和精選清單的寫法大小寫不同)
    downloadable(fakes)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})
    set_tags(fakes, tag("hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m", HF_SMOL_BYTES))
    hold_pulls(fakes)
    await curate(ui_client, HF_SMOL, auto=True)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert result is not None and result["enqueued"] == ["qwen2.5:0.5b"]  # 則1
    assert result["skipped"] == []  # 則2
    assert [job["model"] for job in jobs] == ["qwen2.5:0.5b"]  # 則3
    assert fakes.huggingface.get_manifest.call_count == 0  # 則4


# ---- 004 US3-API-14


async def test_變更類型重新載入的模型已在佇列_自動下載不再排一次(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:第一個工作階段已判定過;新的工作階段要重新載入 `qwen2.5:7b`(`restore`),它同時設了自動下載
    downloadable(fakes)
    set_loaded(fakes, "qwen2.5:7b")
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:7b", auto=True)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)
    old = (await open_ready(ui_client))["name"]
    await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Act
    await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    new = await wait_until(ui_client, lambda s: s.get("state") == "ready" and s.get("name") != old)
    result = await wait_auto(ui_client, lambda r: r is not None and r["sessionName"] == new["name"] and r["state"] == "done")
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    seven = [job for job in jobs if job["model"] == "qwen2.5:7b"]
    assert len(seven) == 1  # 則1
    assert seven[0]["origin"] == "restore"  # 則2
    half = [job for job in jobs if job["model"] == "qwen2.5:0.5b"]
    assert [job["origin"] for job in half] == ["auto"]  # 則3
    assert result is not None and result["sessionName"] == new["name"]  # 則4
    assert result["enqueued"] == ["qwen2.5:0.5b"]  # 則5
    assert result["skipped"] == []  # 則6


# ---- 004 US3-API-15


async def test_空間放不下的項目跳過_後面較小的照順序排入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:剩餘 5,200,000,000,`qwen2.5:7b` 排入後只剩 516,912,668,放不下 `llama3.2`、放得下 `qwen2.5:0.5b`
    downloadable(fakes, disk_free=5_200_000_000)
    set_library(fakes, LATEST_SIZES)
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:7b", auto=True)
    await curate(ui_client, "llama3.2", auto=True)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert result is not None and result["enqueued"] == ["qwen2.5:7b", "qwen2.5:0.5b"]  # 則1
    assert [(s["model"], s["reason"], s["reasonCode"]) for s in result["skipped"]] == [
        ("llama3.2:latest", "DISK_SPACE_INSUFFICIENT", None)
    ]  # 則2
    assert "空間不足" in result["skipped"][0]["message"]  # 則3
    assert [job["model"] for job in jobs] == ["qwen2.5:7b", "qwen2.5:0.5b"]  # 則4


# ---- 004 US3-API-16


async def test_空間判定加上佇列裡還沒下載完的大小(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:重新載入排入、還在下載的 `qwen2.5:7b` 佔 4,683,087,332;`llama3.2` 單獨看放得下剩餘 5,000,000,000
    downloadable(fakes, disk_free=5_000_000_000)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes, tag("qwen2.5:7b", 4_683_087_332))
    set_loaded(fakes, "qwen2.5:7b")
    hold_pulls(fakes)
    await open_ready(ui_client)
    await curate(ui_client, "llama3.2", auto=True)

    # Act
    await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert result is not None and result["enqueued"] == []  # 則1
    assert [(s["model"], s["reason"]) for s in result["skipped"]] == [("llama3.2:latest", "DISK_SPACE_INSUFFICIENT")]  # 則2


# ---- 004 US3-API-17


def set_size_failures(fakes: Any) -> None:
    """四個取大小的失敗,轉接層的 `message` 都是英文原文 `upstream said no`;其他照 `LATEST_SIZES`。"""

    def library(*args: Any, **kwargs: Any) -> dict[str, Any]:
        code = {"999b": "LIBRARY_NOT_FOUND", "1.5b": "LIBRARY_TIMEOUT"}.get(kwargs["tag"])
        if code is not None:
            raise AdapterError(code, "upstream said no")
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": LATEST_SIZES[f"{kwargs['name']}:{kwargs['tag']}"]}

    def hugging_face(*args: Any, **kwargs: Any) -> dict[str, Any]:
        code = {"Private-GGUF": "HF_AUTH_REQUIRED", "Llama-GGUF": "HF_QUANT_UNAVAILABLE"}[kwargs["model"]]
        raise AdapterError(code, "upstream said no")

    fakes.model_library.get_manifest.side_effect(library)
    fakes.huggingface.get_manifest.side_effect(hugging_face)


async def test_取不到大小的項目跳過並帶來源的代碼_不影響後面的項目_也不外洩英文原文(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange:五項都設自動下載,前四項取大小失敗
    downloadable(fakes)
    set_size_failures(fakes)
    hold_pulls(fakes)
    for name in (
        "qwen2.5:999b",
        "hf.co/TheBloke/Private-GGUF",
        "hf.co/bartowski/Llama-GGUF:IQ1_XX",
        "qwen2.5:1.5b",
        "qwen2.5:0.5b",
    ):
        await curate(ui_client, name, auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert result is not None
    assert [s["reason"] for s in result["skipped"]] == ["SIZE_UNAVAILABLE"] * 4  # 則1
    assert [s["reasonCode"] for s in result["skipped"]] == [
        "LIBRARY_NOT_FOUND",
        "HF_AUTH_REQUIRED",
        "HF_QUANT_UNAVAILABLE",
        "LIBRARY_TIMEOUT",
    ]  # 則2
    assert all("upstream said no" not in s["message"] for s in result["skipped"])  # 則3
    assert result["enqueued"] == ["qwen2.5:0.5b"]  # 則4
    assert [job["model"] for job in jobs] == ["qwen2.5:0.5b"]  # 則5


# ---- 004 US3-API-18

QWEN_32B_BYTES = 19_851_336_256
VRAM_SIZES = {**LATEST_SIZES, "qwen2.5:32b": QWEN_32B_BYTES, "qwen2.5:16g": VRAM_TOTAL}


async def test_大小超過顯示記憶體總量的項目跳過_剛好等於總量的照常排入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:`qwen2.5:16g` 的大小剛好等於顯示記憶體總量
    downloadable(fakes)
    set_library(fakes, VRAM_SIZES)
    hold_pulls(fakes)
    for name in ("qwen2.5:32b", "qwen2.5:16g", "qwen2.5:0.5b"):
        await curate(ui_client, name, auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert result is not None
    assert [(s["model"], s["reason"], s["reasonCode"]) for s in result["skipped"]] == [
        ("qwen2.5:32b", "MAY_NOT_FIT", None)
    ]  # 則1
    assert "這台可能無法載入" in result["skipped"][0]["message"]  # 則2
    assert result["enqueued"] == ["qwen2.5:16g", "qwen2.5:0.5b"]  # 則3


# ---- 004 US3-API-19


async def test_讀不到顯示記憶體時不以可能無法載入跳過(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:同 US3-API-18 的精選清單,讀不到顯示記憶體總量(剩餘磁碟讀得到)
    downloadable(fakes)
    set_library(fakes, VRAM_SIZES)
    fakes.colab.probe_resources.returns(resources(vram_total=None))
    hold_pulls(fakes)
    for name in ("qwen2.5:32b", "qwen2.5:16g", "qwen2.5:0.5b"):
        await curate(ui_client, name, auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert result is not None and result["enqueued"] == ["qwen2.5:32b", "qwen2.5:16g", "qwen2.5:0.5b"]  # 則1
    assert result["skipped"] == []  # 則2


# ---- 004 US3-API-20


async def test_讀不到剩餘空間時其餘還沒判定的項目都跳過_取不到大小的照原因(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:`qwen2.5:999b` 取不到大小;開啟前讀不到執行環境的剩餘磁碟空間
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})
    fakes.colab.probe_resources.raises("COLAB_UNREACHABLE", "連不到執行環境")
    hold_pulls(fakes)
    for name in ("qwen2.5:999b", "qwen2.5:7b", HF_SMOL):
        await curate(ui_client, name, auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert result is not None and len(result["skipped"]) == 3  # 則1
    first, second, third = result["skipped"]
    assert (first["model"], first["reason"], first["reasonCode"]) == ("qwen2.5:999b", "SIZE_UNAVAILABLE", "LIBRARY_NOT_FOUND")  # 則2
    assert [(s["reason"], s["reasonCode"]) for s in (second, third)] == [("DISK_SPACE_UNKNOWN", "COLAB_UNREACHABLE")] * 2  # 則3
    assert result["enqueued"] == []  # 則4
    assert jobs == []  # 則5


# ---- 004 US3-API-21


async def test_讀不到執行環境上的模型清單時視為沒有任何模型_照常排入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:開啟前讀不到執行環境上的模型清單
    downloadable(fakes)
    hold_pulls(fakes)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")
    await curate(ui_client, "qwen2.5:0.5b", auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert result is not None and result["enqueued"] == ["qwen2.5:0.5b"]  # 則1
    assert result["skipped"] == []  # 則2


# ---- 004 US3-API-22


async def test_沒有要排的項目時結果仍是完成_和沒設自動下載分得出來(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:設了自動下載的 `qwen2.5:0.5b` 已在執行環境上
    downloadable(fakes)
    set_tags(fakes, tag("qwen2.5:0.5b", 397_821_319))
    await curate(ui_client, "qwen2.5:0.5b", auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert result is not None  # 則1
    assert result["enqueued"] == []  # 則2
    assert result["skipped"] == []  # 則3
    assert result["finishedAt"] is not None  # 則4


# ---- 004 US3-API-23


async def test_沒有設自動下載的項目時不判定_不推送_也不留下做過的痕跡讓之後重連誤排(
    make_app: Callable[..., Any], start_live_servers: Callable[..., Any], fakes: Any, tmp_path: Path
) -> None:
    # Arrange:情況 A 精選清單是空的;情況 B 有 `qwen2.5:0.5b`(`autoDownload` 為 false),各用自己的資料庫
    downloadable(fakes)
    hold_pulls(fakes)
    servers_a = start_live_servers(make_app())
    servers_b = start_live_servers(make_app(db_path=tmp_path / "b.sqlite3"))

    # Act:情況 A
    async with httpx.AsyncClient(base_url=servers_a.ui_url, timeout=5.0) as client_a, collect_events(servers_a.ui_url) as events_a:
        await open_ready(client_a)
        await asyncio.sleep(0.3)
        result_a = (await client_a.get("/api/downloads/auto-result")).json()["result"]
        await client_a.delete("/api/session")
        await wait_until(client_a, lambda s: s.get("state") != "ready" and s.get("state") != "ending")
    # Act:情況 B
    async with httpx.AsyncClient(base_url=servers_b.ui_url, timeout=5.0) as client_b, collect_events(servers_b.ui_url) as events_b:
        item = await curate(client_b, "qwen2.5:0.5b", auto=False)
        await open_ready(client_b)
        await asyncio.sleep(0.3)
        result_b = (await client_b.get("/api/downloads/auto-result")).json()["result"]
        edited = await client_b.put(f"/api/curated/{item['id']}", json={"name": "qwen2.5:0.5b", "autoDownload": True})
        opens_before = fakes.tunnel.open_tunnel.call_count
        fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
        await wait_until(
            client_b, lambda s: fakes.tunnel.open_tunnel.call_count > opens_before and s.get("state") == "ready", timeout=2.5
        )
        await asyncio.sleep(0.3)
        jobs_b = (await queue(client_b))["jobs"]
        result_b_after = (await client_b.get("/api/downloads/auto-result")).json()["result"]

    # Assert
    assert edited.status_code == 200
    assert fakes.tunnel.open_tunnel.call_count > opens_before  # 前提:真的重連過
    assert (result_a, result_b) == (None, None)  # 則1
    assert [name for name, _ in events_a + events_b if name == "autoDownload.updated"] == []  # 則2
    assert jobs_b == []  # 則3
    assert result_b_after is None  # 則4
    assert fakes.model_library.get_manifest.call_count == 0  # 則5


# ---- 004 US3-API-24

SIX_SIZES = {
    "qwen2.5:0.5b": 397_821_319,
    "qwen2.5:1.5b": 986_061_892,
    "qwen2.5:3b": 1_929_912_432,
    "qwen2.5:7b": 4_683_087_332,
    "llama3.2:1b": 1_321_098_329,
    "llama3.2:3b": 2_019_393_189,
}


async def test_取大小同時最多_4_個_排入的順序照精選清單(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:6 個官方名稱都設自動下載,取大小全部停在閘門前
    downloadable(fakes)
    set_library(fakes, SIX_SIZES)
    hold_pulls(fakes)
    for name in SIX_SIZES:
        await curate(ui_client, name, auto=True)
    gate = fakes.model_library.get_manifest.gate()

    # Act
    await open_ready(ui_client)
    await asyncio.sleep(0.2)
    calls_while_held = fakes.model_library.get_manifest.call_count
    gate.release()
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert calls_while_held == 4  # 則1
    assert fakes.model_library.get_manifest.call_count == 6  # 則2
    assert result is not None and result["enqueued"] == list(SIX_SIZES)  # 則3


# ---- 004 US3-API-25


async def test_判定中就先推送進行中的結果_判定完再推送完成_排入的每一筆都推送(live_servers: Any, fakes: Any) -> None:
    # Arrange:`HF_SMOL` 取大小停在閘門前
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})
    hold_pulls(fakes)
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await curate(client, "qwen2.5:7b", auto=True)
        await curate(client, HF_SMOL, auto=True)
        gate = fakes.huggingface.get_manifest.gate()
        async with collect_events(live_servers.ui_url) as events:
            # Act
            await open_ready(client)
            await gate.wait_entered_async(1)
            running = (await client.get("/api/downloads/auto-result")).json()["result"]
            first = await wait_event(events, "autoDownload.updated")
            gate.release()
            done = await wait_event(events, "autoDownload.updated", lambda p: p["result"] is not None and p["result"]["state"] == "done")
            seven = await wait_event(events, "download.updated", lambda p: p["job"]["model"] == "qwen2.5:7b")
            smol = await wait_event(events, "download.updated", lambda p: p["job"]["model"] == HF_SMOL)

    # Assert
    assert first is not None and first["result"] is not None
    assert (first["result"]["state"], first["result"]["enqueued"], first["result"]["finishedAt"]) == ("running", [], None)  # 則1
    assert running is not None and running["state"] == "running"  # 則2
    assert done is not None and done["result"]["enqueued"] == ["qwen2.5:7b", HF_SMOL]  # 則3
    assert seven is not None and seven["job"]["origin"] == "auto"  # 則4
    assert smol is not None and (smol["job"]["origin"], smol["job"]["source"]) == ("auto", "huggingface")  # 則5
