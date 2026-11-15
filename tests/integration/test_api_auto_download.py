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
from fakes import Gate
from integration.test_api_curated import HF_SMOL, HF_SMOL_BYTES, curate, set_hf, wait_auto
from integration.test_api_downloads import LATEST_SIZES, MANIFEST_SIZES, downloadable, hold_pulls, queue, set_library, states, wait_queue
from integration.test_api_events import sse_events
from integration.test_api_models import L4, VRAM_TOTAL, resources, set_loaded, set_tags, tag
from integration.test_api_recovery import reset_calls, running
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    T4,
    error_code,
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


# ---- 004 US3-API-26


async def events_until_auto_download(base_url: str, timeout: float = 2.0) -> list[tuple[str, dict[str, Any]]]:
    """開一條 `GET /api/events`,依序記下事件,讀到 `autoDownload.updated`(或逾時)為止。"""
    received: list[tuple[str, dict[str, Any]]] = []

    async def read(response: httpx.Response) -> None:
        async for event in sse_events(response):
            received.append(event)
            if event[0] == "autoDownload.updated":
                return

    async with httpx.AsyncClient(base_url=base_url, timeout=None) as client, client.stream("GET", "/api/events") as response:
        try:
            await asyncio.wait_for(read(response), timeout)
        except TimeoutError:
            pass
    return received


async def test_連上時的快照在佇列之後帶自動下載結果_沒有結果時是_null(
    make_app: Callable[..., Any], start_live_servers: Callable[..., Any], fakes: Any, tmp_path: Path
) -> None:
    # Arrange:情況 A 沒有工作階段;情況 B 有設自動下載的 `qwen2.5:0.5b`,各用自己的資料庫
    downloadable(fakes)
    hold_pulls(fakes)
    servers_a = start_live_servers(make_app())
    servers_b = start_live_servers(make_app(db_path=tmp_path / "b.sqlite3"))

    # Act
    events_a = await events_until_auto_download(servers_a.ui_url)
    async with httpx.AsyncClient(base_url=servers_b.ui_url, timeout=5.0) as client_b:
        await curate(client_b, "qwen2.5:0.5b", auto=True)
        await open_ready(client_b)
        await wait_auto(client_b, lambda r: r is not None and r["state"] == "done")
    events_b = await events_until_auto_download(servers_b.ui_url)

    # Assert
    names_a = [name for name, _ in events_a]
    names_b = [name for name, _ in events_b]
    assert "downloads.snapshot" in names_a and "autoDownload.updated" in names_a  # 前提:兩則都收到了
    assert names_a.index("autoDownload.updated") > names_a.index("downloads.snapshot")  # 則1
    assert events_a[-1][1]["result"] is None  # 則2
    assert "downloads.snapshot" in names_b and "autoDownload.updated" in names_b  # 前提:兩則都收到了
    assert names_b.index("autoDownload.updated") > names_b.index("downloads.snapshot")  # 則3
    result_b = events_b[-1][1]["result"]
    assert result_b is not None and (result_b["state"], result_b["enqueued"]) == ("done", ["qwen2.5:0.5b"])  # 則4


# ---- 004 US3-API-27


async def test_重連接回同一個工作階段不重排_結果與完成時間不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:第一次就緒已判定完成
    downloadable(fakes)
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:7b", auto=True)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)
    await open_ready(ui_client)
    before = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    fakes.model_library.get_manifest.reset_calls()

    # Act:健康檢查失敗一次,重連接回同一個工作階段
    opens_before = fakes.tunnel.open_tunnel.call_count
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))
    await wait_until(
        ui_client, lambda s: fakes.tunnel.open_tunnel.call_count > opens_before and s.get("state") == "ready", timeout=2.5
    )
    await asyncio.sleep(0.3)
    jobs = (await queue(ui_client))["jobs"]
    after = (await ui_client.get("/api/downloads/auto-result")).json()["result"]

    # Assert
    assert fakes.tunnel.open_tunnel.call_count > opens_before  # 前提:真的重連過
    assert [job["model"] for job in jobs].count("qwen2.5:7b") == 1  # 則1
    assert [job["model"] for job in jobs].count("qwen2.5:0.5b") == 1  # 則2
    assert fakes.model_library.get_manifest.call_count == 0  # 則3
    assert after == before  # 則4


# ---- 004 US3-API-28


async def test_後端重新啟動接回同一個工作階段不重排_結果與關閉狀態都還在(make_app: Callable[..., Any], fakes: Any) -> None:
    # Arrange:第一個 app 裡就緒、判定完成、使用者關掉提示
    downloadable(fakes)
    hold_pulls(fakes)
    async with running(make_app()) as client:
        await curate(client, "qwen2.5:7b", auto=True)
        await curate(client, "qwen2.5:0.5b", auto=True)
        name = (await open_ready(client))["name"]
        before = await wait_auto(client, lambda r: r is not None and r["state"] == "done")
        dismissed = await client.post("/api/downloads/auto-result/dismiss")
    reset_calls(fakes)
    fakes.model_library.get_manifest.reset_calls()

    # Act:以同一個 SQLite 檔再起一個 app,等接回同一個工作階段就緒
    async with running(make_app()) as client:
        await wait_until(client, lambda s: s.get("state") == "ready" and s.get("name") == name)
        await asyncio.sleep(0.3)
        after = (await client.get("/api/downloads/auto-result")).json()["result"]
        jobs = (await queue(client))["jobs"]

    # Assert
    assert dismissed.status_code == 200  # 前提:關閉成功
    assert before is not None
    assert after is not None and after["sessionName"] == name  # 則1
    assert after["enqueued"] == before["enqueued"] == ["qwen2.5:7b", "qwen2.5:0.5b"]  # 則2
    assert after["dismissed"] is True  # 則3
    assert [job["model"] for job in jobs if job["model"] == "qwen2.5:7b" and job["state"] in ("queued", "downloading")] == ["qwen2.5:7b"]  # 則4
    assert fakes.model_library.get_manifest.call_count == 0  # 則5


# ---- 004 US3-API-29


async def test_關閉提示只標記已關閉_結果與已排入的下載都留著_重複關閉照樣成功_也推送給其他分頁(
    live_servers: Any, fakes: Any
) -> None:
    # Arrange:`qwen2.5:7b` 排入、`llama3.2` 空間不足被跳過
    downloadable(fakes, disk_free=5_000_000_000)
    hold_pulls(fakes)
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await curate(client, "qwen2.5:7b", auto=True)
        await curate(client, "llama3.2", auto=True)
        await open_ready(client)
        await wait_auto(client, lambda r: r is not None and r["state"] == "done")
        async with collect_events(live_servers.ui_url) as events:
            # Act
            first = await client.post("/api/downloads/auto-result/dismiss")
            after = (await client.get("/api/downloads/auto-result")).json()["result"]
            second = await client.post("/api/downloads/auto-result/dismiss")
            pushed = await wait_event(events, "autoDownload.updated", lambda p: p["result"] is not None and p["result"]["dismissed"])
            jobs = (await queue(client))["jobs"]

    # Assert
    assert first.status_code == 200 and first.json()["dismissed"] is True  # 則1
    assert [item["model"] for item in first.json()["skipped"]] == ["llama3.2:latest"]  # 則2
    assert after is not None and after["dismissed"] is True  # 則3
    assert second.status_code == 200 and second.json()["dismissed"] is True  # 則4
    assert pushed is not None  # 則5
    assert [job["model"] for job in jobs] == ["qwen2.5:7b"]  # 則6


# ---- 004 US3-API-30


async def test_判定中就能關閉提示_判定完成後仍是已關閉(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:取大小停在閘門前
    downloadable(fakes)
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)
    gate = fakes.model_library.get_manifest.gate()
    await open_ready(ui_client)
    await gate.wait_entered_async(1)

    # Act
    dismissed = await ui_client.post("/api/downloads/auto-result/dismiss")
    gate.release()
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert dismissed.status_code == 200  # 則1
    assert (dismissed.json()["state"], dismissed.json()["dismissed"]) == ("running", True)  # 則1
    assert result is not None and result["dismissed"] is True  # 則2
    assert result["enqueued"] == ["qwen2.5:0.5b"]  # 則3


# ---- 004 US3-API-31


async def test_沒有結果時關閉提示回_404_沒有工作階段_沒設自動下載_工作階段已結束都一樣(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange
    downloadable(fakes)
    hold_pulls(fakes)

    # Act:A 沒有工作階段
    response_a = await ui_client.post("/api/downloads/auto-result/dismiss")
    # Act:B 精選清單只有一項沒設自動下載,就緒後送關閉
    item = await curate(ui_client, "qwen2.5:1.5b", auto=False)
    await open_ready(ui_client)
    response_b = await ui_client.post("/api/downloads/auto-result/dismiss")
    await ui_client.delete("/api/session")
    await wait_until(ui_client, lambda s: s.get("state") == "ended")
    # Act:C 改成設自動下載,新的工作階段判定完成後結束,再送關閉
    await ui_client.put(f"/api/curated/{item['id']}", json={"name": "qwen2.5:1.5b", "autoDownload": True})
    await open_ready(ui_client)
    await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    await ui_client.delete("/api/session")
    await wait_until(ui_client, lambda s: s.get("state") == "ended")
    response_c = await ui_client.post("/api/downloads/auto-result/dismiss")

    # Assert
    assert response_a.status_code == 404  # 則1
    assert error_code(response_a) == "AUTO_DOWNLOAD_RESULT_NOT_FOUND"  # 則1
    assert response_b.status_code == 404  # 則2
    assert error_code(response_b) == "AUTO_DOWNLOAD_RESULT_NOT_FOUND"  # 則2
    assert response_c.status_code == 404  # 則3
    assert error_code(response_c) == "AUTO_DOWNLOAD_RESULT_NOT_FOUND"  # 則3


# ---- 004 US3-API-32


async def test_工作階段結束時自動下載的結果一併清掉並推送_result_為_null(live_servers: Any, fakes: Any) -> None:
    # Arrange:判定已完成
    downloadable(fakes)
    hold_pulls(fakes)
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await curate(client, "qwen2.5:0.5b", auto=True)
        await open_ready(client)
        await wait_auto(client, lambda r: r is not None and r["state"] == "done")
        async with collect_events(live_servers.ui_url) as events:
            # Act
            await client.delete("/api/session")
            pushed = await wait_event(events, "autoDownload.updated", lambda p: p["result"] is None, timeout=1.0)
            await wait_until(client, lambda s: s.get("state") == "ended")
            result = (await client.get("/api/downloads/auto-result")).json()["result"]

    # Assert
    assert pushed is not None  # 則1
    assert result is None  # 則2


# ---- 004 US3-API-33


async def test_開啟中結束或開啟失敗都不自動下載_結果是_null_佇列是空的(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)

    async def observe() -> tuple[Any, list[Any]]:
        await asyncio.sleep(0.3)
        result = (await ui_client.get("/api/downloads/auto-result")).json()["result"]
        return result, (await queue(ui_client))["jobs"]

    # Act:A 開啟停在配置時按結束
    creating = fakes.colab.create_session.gate()
    await ui_client.post("/api/session", json={"runtimeType": T4})
    await wait_until(ui_client, lambda s: s.get("state") == "opening")
    await ui_client.delete("/api/session")
    creating.release()
    await wait_until(ui_client, lambda s: s.get("state") == "ended")
    observed_a = await observe()
    # Act:B 開啟時建通道失敗
    fakes.tunnel.open_tunnel.raises("TUNNEL_UNREACHABLE", "連不到")
    await ui_client.post("/api/session", json={"runtimeType": T4})
    await wait_until(ui_client, lambda s: s.get("state") == "open_failed")
    observed_b = await observe()

    # Assert
    assert (observed_a[0], observed_b[0]) == (None, None)  # 則1
    assert (observed_a[1], observed_b[1]) == ([], [])  # 則2
    assert fakes.model_library.get_manifest.call_count == 0  # 則3


# ---- 004 US3-API-34


async def test_自動排入後刪除或取消自動下載不影響佇列_照常下載完成_結果也不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:兩項都設自動下載,判定完成、下載停在閘門前
    downloadable(fakes)
    hold = hold_pulls(fakes)
    item_a = await curate(ui_client, "qwen2.5:7b", auto=True)
    item_b = await curate(ui_client, "qwen2.5:0.5b", auto=True)
    await open_ready(ui_client)
    await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Act
    deleted = await ui_client.delete(f"/api/curated/{item_a['id']}")
    edited = await ui_client.put(f"/api/curated/{item_b['id']}", json={"name": "qwen2.5:0.5b", "autoDownload": False})
    hold.release()
    final = await wait_queue(ui_client, lambda q: [state for _, state in states(q)] == ["completed", "completed"])
    result = (await ui_client.get("/api/downloads/auto-result")).json()["result"]

    # Assert
    assert deleted.status_code == 204  # 則1
    assert edited.status_code == 200  # 則2
    assert [state for _, state in states(final)] == ["completed", "completed"]  # 則3
    pulled = [call.kwargs.get("model") for call in fakes.remote_ollama.pull_model.calls]
    assert (pulled.count("qwen2.5:7b"), pulled.count("qwen2.5:0.5b")) == (1, 1)  # 則4
    assert result is not None and result["enqueued"] == ["qwen2.5:7b", "qwen2.5:0.5b"]  # 則5


# ---- 004 US3-API-35


async def test_重新啟動後精選清單的類型與自動下載設定都還在_就緒時照設定排入(make_app: Callable[..., Any], fakes: Any) -> None:
    # Arrange:第一個 app 新增兩項後離開
    downloadable(fakes)
    hold_pulls(fakes)
    runtime_type = {"gpu": "H100", "highMem": False}
    async with running(make_app()) as client:
        first = await client.post(
            "/api/curated",
            json={"name": "qwen2.5:0.5b", "description": "日常用", "recommendedRuntimeType": runtime_type, "autoDownload": True},
        )
        second = await client.post("/api/curated", json={"name": HF_SMOL})
        assert (first.status_code, second.status_code) == (201, 201)

    # Act:以同一個 SQLite 檔建第二個 app
    async with running(make_app()) as client:
        listed = (await client.get("/api/curated")).json()["items"]
        await open_ready(client)
        await wait_auto(client, lambda r: r is not None and r["state"] == "done")
        jobs = (await queue(client))["jobs"]

    # Assert
    assert [item["name"] for item in listed] == ["qwen2.5:0.5b", HF_SMOL]  # 則1
    assert (listed[0]["autoDownload"], listed[0]["recommendedRuntimeType"], listed[0]["description"]) == (True, runtime_type, "日常用")  # 則2
    assert listed[1]["autoDownload"] is False  # 則3
    assert [(job["model"], job["origin"]) for job in jobs] == [("qwen2.5:0.5b", "auto")]  # 則4


# ---- 004 US3-API-36


async def test_就緒後_0_6_秒內給出結果_8_項都排入或標示跳過_已在執行環境上的不算(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:8 個官方名稱(1 個 LIBRARY_NOT_FOUND、1 個 MAY_NOT_FIT),取大小每次 0.1 秒;`gemma2:2b` 已在執行環境上
    sizes = {**SIX_SIZES, "qwen2.5:32b": 19_851_336_256}

    async def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        full = f"{kwargs['name']}:{kwargs['tag']}"
        if full not in sizes:
            raise AdapterError("LIBRARY_NOT_FOUND", "manifest unknown")
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": sizes[full]}

    downloadable(fakes)
    fakes.model_library.get_manifest.side_effect(manifest)
    set_tags(fakes, tag("gemma2:2b", 1_629_518_495))
    hold_pulls(fakes)
    for name in [*sizes, "qwen2.5:999b", "gemma2:2b"]:
        await curate(ui_client, name, auto=True)

    # Act
    await open_ready(ui_client)
    ready_at = time.monotonic()
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done", timeout=2.0)
    elapsed = time.monotonic() - ready_at

    # Assert
    assert result is not None and result["state"] == "done"
    assert elapsed < 0.6, elapsed  # 則1
    assert len(result["enqueued"]) + len(result["skipped"]) == 8  # 則2
    reasons = {item["model"]: (item["reason"], item["reasonCode"]) for item in result["skipped"]}
    assert reasons == {"qwen2.5:999b": ("SIZE_UNAVAILABLE", "LIBRARY_NOT_FOUND"), "qwen2.5:32b": ("MAY_NOT_FIT", None)}  # 則3
    assert "gemma2:2b" not in result["enqueued"] and "gemma2:2b" not in reasons  # 則4


# ---- 004 US3-API-37


async def test_所有來源都連不到時自動下載照常完成_不回_500_工作階段仍就緒(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:執行環境的模型清單、兩個模型來源、剩餘空間全部讀不到
    downloadable(fakes)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)
    await curate(ui_client, HF_SMOL, auto=True)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_TIMEOUT", "逾時")
    fakes.model_library.get_manifest.raises("LIBRARY_UNREACHABLE", "連不到")
    fakes.huggingface.get_manifest.raises("HF_UNREACHABLE", "連不到")
    fakes.colab.probe_resources.raises("COLAB_UNREACHABLE", "連不到")

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    responses = [
        await ui_client.get("/api/downloads/auto-result"),
        await ui_client.get("/api/curated"),
        await ui_client.get("/api/downloads"),
        await ui_client.get("/api/session"),
    ]

    # Assert
    assert [response.status_code for response in responses] == [200, 200, 200, 200]  # 則1
    assert result is not None and result["state"] == "done"
    assert [item["reasonCode"] for item in result["skipped"]] == ["LIBRARY_UNREACHABLE", "HF_UNREACHABLE"]  # 則2
    assert responses[3].json()["state"] == "ready"  # 則3


# ---- 004 US3-API-39


async def test_跳過的項目帶大小_剩餘空間_顯示記憶體_依原因有值或為_null_重新啟動後不變(
    make_app: Callable[..., Any], fakes: Any, tmp_path: Path
) -> None:
    # Arrange:情況 A 剩餘磁碟 5,200,000,000、顯示記憶體 16,106,127,360;情況 B 讀不到剩餘空間(另一個暫存庫)
    downloadable(fakes, disk_free=5_200_000_000)
    set_library(fakes, {**LATEST_SIZES, "qwen2.5:32b": 19_851_336_256})
    hold_pulls(fakes)
    async with running(make_app()) as client:
        for name in ("qwen2.5:999b", "qwen2.5:32b", "qwen2.5:7b", "llama3.2"):
            await curate(client, name, auto=True)
        name_a = (await open_ready(client))["name"]
        before = await wait_auto(client, lambda r: r is not None and r["state"] == "done")

    # Act:情況 A 重新啟動後再讀;情況 B
    async with running(make_app()) as client:
        await wait_until(client, lambda s: s.get("state") == "ready" and s.get("name") == name_a)
        after = (await client.get("/api/downloads/auto-result")).json()["result"]
    async with running(make_app(db_path=tmp_path / "b.sqlite3")) as client:
        await curate(client, "qwen2.5:999b", auto=True)
        await curate(client, "qwen2.5:7b", auto=True)
        fakes.colab.probe_resources.raises("COLAB_UNREACHABLE", "連不到執行環境")
        await open_ready(client)
        result_b = await wait_auto(client, lambda r: r is not None and r["state"] == "done")

    # Assert
    assert before is not None and after is not None and result_b is not None
    assert [item["model"] for item in before["skipped"]] == ["qwen2.5:999b", "qwen2.5:32b", "llama3.2:latest"]  # 則1
    assert before["enqueued"] == ["qwen2.5:7b"]  # 則1
    figures = {item["model"]: (item["sizeBytes"], item["freeDiskBytes"], item["vramBytes"]) for item in before["skipped"]}
    assert figures["qwen2.5:999b"] == (None, None, None)  # 則2
    assert figures["qwen2.5:32b"] == (19_851_336_256, None, 16_106_127_360)  # 則3
    assert figures["llama3.2:latest"] == (2_019_393_189, 516_912_668, None)  # 則4
    assert after["skipped"] == before["skipped"]  # 則5
    unknown = next(item for item in result_b["skipped"] if item["reason"] == "DISK_SPACE_UNKNOWN")
    assert (unknown["model"], unknown["sizeBytes"], unknown["freeDiskBytes"], unknown["vramBytes"]) == ("qwen2.5:7b", 4_683_087_332, None, None)  # 則6


# ---- 004 US3-API-競爭:自動下載取大小期間手動加入其中一項


async def test_自動下載取大小期間手動加入其中一項_其餘照常排入_結果只列實際排入的(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:自動下載目標 7b 與 0.5b;0.5b 的 manifest 停在閘門前,7b 的照常回
    downloadable(fakes)
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:7b", auto=True)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)
    held = Gate()

    async def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["tag"] == "0.5b":
            await held.pass_async()
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": MANIFEST_SIZES[f"{kwargs['name']}:{kwargs['tag']}"]}

    fakes.model_library.get_manifest.side_effect(manifest)
    await open_ready(ui_client)
    await held.wait_entered_async(timeout=3.0)

    # Act:判定還沒結束,使用者手動加入 7b;再放行 0.5b
    manual = await ui_client.post("/api/downloads", json={"models": ["qwen2.5:7b"]})
    held.release()
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert manual.status_code == 201  # 則1
    assert result is not None and result["enqueued"] == ["qwen2.5:0.5b"]  # 則2
    assert result["skipped"] == []  # 則3
    assert sorted((job["model"], job["origin"]) for job in jobs) == [("qwen2.5:0.5b", "auto"), ("qwen2.5:7b", "user")]  # 則4


async def test_手動加入的重複項目先排除再試算空間_剩餘空間只夠手動與其他項目各一份時其他項目仍排入(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange:剩餘空間剛好放得下 7b 加 0.5b 各一份,放不下 7b 算兩次再加 0.5b;自動下載目標依序為 7b、0.5b
    sizes = MANIFEST_SIZES
    downloadable(fakes, disk_free=sizes["qwen2.5:7b"] + sizes["qwen2.5:0.5b"])
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:7b", auto=True)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)
    held = Gate()

    async def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["tag"] == "0.5b":
            await held.pass_async()
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": sizes[f"{kwargs['name']}:{kwargs['tag']}"]}

    fakes.model_library.get_manifest.side_effect(manifest)
    await open_ready(ui_client)
    await held.wait_entered_async(timeout=3.0)

    # Act:取大小期間手動加入 7b,再放行
    manual = await ui_client.post("/api/downloads", json={"models": ["qwen2.5:7b"]})
    held.release()
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")

    # Assert:0.5b 沒有被誤判成空間不足
    assert manual.status_code == 201  # 則1
    assert result is not None and result["enqueued"] == ["qwen2.5:0.5b"]  # 則2
    assert result["skipped"] == []  # 則3
