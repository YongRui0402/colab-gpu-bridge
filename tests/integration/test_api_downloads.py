"""E2 後端 UI API:下載佇列(testplan.md § 4.1,`/api/downloads` › 加入、移除、試算、重新排隊)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身(testplan.md § 接縫的取捨)。
「假伺服器的 pull」是 `FakeRemoteOllama.pull_model` 產出的進度行;每一行前面放一個閘門,
由測試端的 `Pacer` 照節奏放行,模擬「每 0.1 秒送一行」。
"""

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.db.connection import connect
from cgb.domain.errors import MESSAGES
from fakes import Gate, JsonReply
from integration.test_api_events import sse_events
from integration.test_api_models import (
    DISK_FREE,
    QWEN_7B,
    QWEN_7B_BYTES,
    QWEN_SMALL,
    QWEN_SMALL_BYTES,
    resources,
    set_loaded,
    set_tags,
    tag,
)
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    T4,
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
    wait_for_state,
)

QWEN_MID = "qwen2.5:1.5b"
QWEN_MID_BYTES = 986_061_892
MANIFEST_SIZES = {QWEN_SMALL: QWEN_SMALL_BYTES, QWEN_7B: QWEN_7B_BYTES, QWEN_MID: QWEN_MID_BYTES}
LATEST_SIZES = {**MANIFEST_SIZES, "qwen2.5:latest": 4_683_087_332, "llama3.2:latest": 2_019_393_189}

# 故事 4 的測試資料(testplan.md § 5.3);不從 test_api_huggingface、test_api_curated 匯入,它們反過來匯入本檔(會循環)
HF_Q4 = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
HF_Q4_BYTES = 105_455_145
HF_GEMMA = "hf.co/google/gemma-3-1b-it-qat-q4_0-gguf:Q4_0"  # 需要登入的 repo
HF_Q4_L = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_L"  # 不存在的量化版本
HF_NOT_GGUF = "hf.co/Qwen/Qwen2.5-0.5B-Instruct"  # 不是 GGUF 的 repo(沒寫量化版本,補成 `:latest`)


def set_library(fakes: Any, sizes: dict[str, int] = MANIFEST_SIZES) -> None:
    """`get_manifest` 依 `<名稱>:<版本>` 回精確大小,其他回 `LIBRARY_NOT_FOUND`。"""

    def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        full = f"{kwargs['name']}:{kwargs['tag']}"
        if full not in sizes:
            raise AdapterError("LIBRARY_NOT_FOUND", "manifest unknown")
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": sizes[full]}

    fakes.model_library.get_manifest.side_effect(manifest)


def set_hf(fakes: Any, sizes: dict[str, int], raises: dict[str, str] | None = None) -> None:
    """`FakeHuggingFaceHub.get_manifest` 依 `hf.co/<作者>/<模型>:<tag>` 回 `sizes` 裡的大小,其他回 `HF_AUTH_REQUIRED`(plan.md Q36、Q65)。

    `raises` 對某個完整名稱指定要丟的代碼,優先於 `sizes`(與 test_api_curated 的 `set_hf` 同一個行為)。
    """
    failing = raises or {}

    def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        full = f"hf.co/{kwargs['author']}/{kwargs['model']}:{kwargs['tag']}"
        if full in failing:
            raise AdapterError(failing[full], "manifest failure")
        if full not in sizes:
            raise AdapterError("HF_AUTH_REQUIRED", "manifest unknown")
        return {"sizeBytes": sizes[full]}

    fakes.huggingface.get_manifest.side_effect(manifest)


def set_hf_refusals(fakes: Any) -> None:
    """Hugging Face 拒絕的三種名稱(testplan.md § US4-API-16 的鋪陳):需要登入、量化版本不存在、不是 GGUF 的 repo(Q20)。"""
    set_hf(
        fakes,
        {},
        raises={HF_GEMMA: "HF_AUTH_REQUIRED", HF_Q4_L: "HF_QUANT_UNAVAILABLE", f"{HF_NOT_GGUF}:latest": "HF_QUANT_UNAVAILABLE"},
    )


def downloadable(fakes: Any, *, disk_free: int = DISK_FREE) -> ColabWorld:
    """工作階段可開到就緒、模型庫有三個 qwen2.5 版本、剩餘磁碟 `disk_free`。"""
    world = ColabWorld(fakes)
    set_tags(fakes)
    set_loaded(fakes)
    set_library(fakes)
    fakes.colab.probe_resources.returns(resources(disk_free))
    return world


class Pacer:
    """照節奏放行閘門:每個閘門被走到之後等 `interval` 秒才放行。"""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.gates: list[Gate] = []

    def gate(self) -> Gate:
        gate = Gate()
        self.gates.append(gate)
        return gate

    async def run(self) -> None:
        index = 0
        while True:
            while index >= len(self.gates):
                await asyncio.sleep(0.005)
            gate = self.gates[index]
            await gate.wait_entered_async(timeout=30.0)
            await asyncio.sleep(self.interval)
            gate.release()
            index += 1


def paced_pull(pacer: Pacer, lines: int, log: list[tuple[str, str, float]], total: int = 3000) -> Callable[..., Iterator[Any]]:
    """`pull_model` 的 side effect:送 `lines` 行進度(每行前一個 `pacer` 的閘門),最後 `success`。

    開始(被呼叫)與送完 `success` 的時間記進 `log`:(`"start"` 或 `"end"`, 模型, time.monotonic())。
    """

    def pull(*args: Any, **kwargs: Any) -> Iterator[Any]:
        model = kwargs["model"]
        log.append(("start", model, time.monotonic()))

        def lines_of() -> Iterator[Any]:
            yield {"status": "pulling manifest"}
            for i in range(lines):
                yield pacer.gate()
                yield {"status": "pulling sha256:a", "digest": "sha256:a", "total": total, "completed": (i + 1) * total // lines}
            yield {"status": "success"}
            log.append(("end", model, time.monotonic()))

        return lines_of()

    return pull


async def queue(client: httpx.AsyncClient) -> dict[str, Any]:
    return (await client.get("/api/downloads")).json()


async def wait_queue(client: httpx.AsyncClient, predicate: Callable[[dict[str, Any]], bool], timeout: float = 5.0) -> dict[str, Any]:
    """一直查 `GET /api/downloads`,直到 `predicate(佇列)` 成立或逾時;回傳最後一次看到的。"""
    deadline = time.monotonic() + timeout
    current = await queue(client)
    while not predicate(current) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
        current = await queue(client)
    return current


def states(current: dict[str, Any]) -> list[tuple[str, str]]:
    return [(job["model"], job["state"]) for job in current.get("jobs", [])]


async def catalog_names(client: httpx.AsyncClient) -> list[str]:
    return [item["name"] for item in (await client.get("/api/models")).json().get("items", [])]


# ---------------------------------------------------------------- US3-API-07


async def test_背景下載每秒最多推一則進度_完成後才出現在目錄(live_servers: Any, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    pacer, log = Pacer(0.1), []
    fakes.remote_ollama.pull_model.side_effect(paced_pull(pacer, 30, log))
    fakes.remote_ollama.list_local_models.side_effect(
        lambda *a, **k: {"models": [tag(QWEN_7B, QWEN_7B_BYTES)] if any(e[0] == "end" for e in log) else []}
    )
    received: list[tuple[float, dict[str, Any]]] = []
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        async with client.stream("GET", "/api/events") as stream:

            async def collect() -> None:
                async for name, payload in sse_events(stream):
                    if name == "download.updated":
                        received.append((time.monotonic(), payload["job"]))

            collector = asyncio.create_task(collect())
            pacing = asyncio.create_task(pacer.run())
            await asyncio.sleep(0.1)

            # Act
            response = await client.post("/api/downloads", json={"models": [QWEN_7B]})
            await asyncio.sleep(1.5)
            names_while_downloading = await catalog_names(client)
            final = await wait_queue(client, lambda q: states(q) == [(QWEN_7B, "completed")], timeout=8.0)
            names_after = await catalog_names(client)
            await asyncio.sleep(0.1)
            pacing.cancel()
            collector.cancel()

    # Assert
    accepted = response.json().get("jobs", [{}]) if response.status_code == 201 else [{}]
    assert (response.status_code, accepted[0].get("state") in ("queued", "downloading")) == (201, True)
    downloading = [(at, job) for at, job in received if job.get("state") == "downloading"]
    gaps = [later - earlier for (earlier, _), (later, _) in zip(downloading, downloading[1:], strict=False)]
    assert len(downloading) >= 2 and all(gap >= 0.9 for gap in gaps), gaps
    progress = [job["progress"]["completedBytes"] for _, job in downloading if job.get("progress")]
    assert progress == sorted(progress) and len(set(progress)) >= 2, progress
    assert QWEN_7B not in names_while_downloading
    assert states(final) == [(QWEN_7B, "completed")]
    assert QWEN_7B in names_after


# ---------------------------------------------------------------- US3-API-08


async def test_模型庫沒有的模型不排進佇列(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.remote_ollama.pull_model.returns([{"status": "success"}])
    await open_ready(ui_client)
    missing = "qwen2.5:cgb-test-nonexistent"

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [missing]})
    await asyncio.sleep(0.1)
    after = await queue(ui_client)

    # Assert
    body = response.json() if response.status_code == 404 else {}
    assert (response.status_code, body.get("code"), body.get("model")) == (404, "LIBRARY_NOT_FOUND", missing)
    assert states(after) == []
    assert fakes.remote_ollama.pull_model.call_count == 0


# ---------------------------------------------------------------- US3-API-09


async def test_pull_串流中出現錯誤時那一筆失敗_並分出原因(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:情況 A(qwen2.5:7b)找不到 manifest,情況 B(qwen2.5:0.5b)磁碟滿
    downloadable(fakes)
    set_tags(fakes, tag(QWEN_MID, QWEN_MID_BYTES))
    errors = {
        QWEN_7B: AdapterError("OLLAMA_NOT_FOUND", "pull model manifest: file does not exist"),
        QWEN_SMALL: AdapterError("OLLAMA_PULL_FAILED", "no space left on device"),
    }
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "pulling manifest"}, errors[k["model"]]])
    await open_ready(ui_client)
    before = await catalog_names(ui_client)

    # Act
    await ui_client.post("/api/downloads", json={"models": [QWEN_7B]})
    await wait_queue(ui_client, lambda q: states(q) == [(QWEN_7B, "failed")])
    await ui_client.post("/api/downloads", json={"models": [QWEN_SMALL]})
    final = await wait_queue(ui_client, lambda q: states(q) == [(QWEN_7B, "failed"), (QWEN_SMALL, "failed")])
    after = await catalog_names(ui_client)

    # Assert
    reasons = {job["model"]: (job["state"], job["reasonCode"]) for job in final.get("jobs", [])}
    assert reasons == {QWEN_7B: ("failed", "OLLAMA_NOT_FOUND"), QWEN_SMALL: ("failed", "OLLAMA_PULL_FAILED")}
    assert after == before


# ---------------------------------------------------------------- US3-API-10


async def test_一次加入三個時依加入順序一個接一個下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:每個 pull 送 3 行進度,每行間隔 0.05 秒
    downloadable(fakes)
    pacer, log = Pacer(0.05), []
    fakes.remote_ollama.pull_model.side_effect(paced_pull(pacer, 3, log))
    await open_ready(ui_client)
    pacing = asyncio.create_task(pacer.run())
    order = [QWEN_SMALL, QWEN_7B, QWEN_MID]

    # Act
    await ui_client.post("/api/downloads", json={"models": order})
    final = await wait_queue(ui_client, lambda q: all(state == "completed" for _, state in states(q)) and len(states(q)) == 3)
    pacing.cancel()

    # Assert
    times = {(kind, model): at for kind, model, at in log}
    assert [model for kind, model, _ in log if kind == "start"] == order
    assert times[("start", QWEN_7B)] >= times[("end", QWEN_SMALL)]
    assert times[("start", QWEN_MID)] >= times[("end", QWEN_7B)]
    assert states(final) == [(model, "completed") for model in order]


# ---------------------------------------------------------------- US3-API-11


async def test_排隊中的可以取消_正在下載的不能取消(live_servers: Any, fakes: Any) -> None:
    # Arrange:第 1 筆的 pull 停在閘門前(下載中),第 2、3 筆排隊中
    downloadable(fakes)
    hold = Gate()
    pulled: list[str] = []

    def pull(*args: Any, **kwargs: Any) -> list[Any]:
        pulled.append(kwargs["model"])
        return [{"status": "pulling manifest"}, hold, {"status": "success"}]

    fakes.remote_ollama.pull_model.side_effect(pull)
    removed: list[int] = []
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        async with client.stream("GET", "/api/events") as stream:

            async def collect() -> None:
                async for name, payload in sse_events(stream):
                    if name == "download.removed":
                        removed.append(payload["id"])

            collector = asyncio.create_task(collect())
            await asyncio.sleep(0.1)
            jobs = (await client.post("/api/downloads", json={"models": [QWEN_SMALL, QWEN_7B, QWEN_MID]})).json()["jobs"]
            first, third = jobs[0]["id"], jobs[2]["id"]
            await wait_queue(client, lambda q: states(q)[:1] == [(QWEN_SMALL, "downloading")])

            # Act
            cancel_third = await client.delete(f"/api/downloads/{third}")
            cancel_first = await client.delete(f"/api/downloads/{first}")
            await asyncio.sleep(0.2)
            during = await queue(client)
            hold.release()
            await wait_queue(client, lambda q: [s for _, s in states(q)] == ["completed", "completed"])
            collector.cancel()

    # Assert
    assert (cancel_third.status_code, removed) == (204, [third])
    assert QWEN_MID not in pulled
    assert (cancel_first.status_code, error_code(cancel_first)) == (409, "DOWNLOAD_IN_PROGRESS")
    assert states(during) == [(QWEN_SMALL, "downloading"), (QWEN_7B, "queued")]


# ---------------------------------------------------------------- US3-API-12


async def test_試算用_manifest_各層加總_剩餘磁碟與預估時間_不改變佇列(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_7B, QWEN_SMALL]})
    estimate = response.json() if response.status_code == 200 else {}
    after = await queue(ui_client)

    # Assert
    assert response.status_code == 200
    assert estimate.get("totalBytes") == 5_080_908_651
    assert estimate.get("freeDiskBytes") == DISK_FREE
    assert 101 <= estimate.get("estimatedSeconds", -1) <= 102
    assert estimate.get("fits") is True
    assert states(after) == []


async def enqueue_waiting(client: httpx.AsyncClient, fakes: Any, *models: str) -> Gate:
    """加入 `models`;第 1 筆的 pull 停在閘門前(下載中),之後的排隊中。回傳那個閘門。"""
    hold = Gate()
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "pulling manifest"}, hold, {"status": "success"}])
    await client.post("/api/downloads", json={"models": list(models)})
    await wait_queue(client, lambda q: states(q)[:1] == [(models[0], "downloading")])
    return hold


# ---------------------------------------------------------------- US3-API-13


async def test_佇列裡還沒下載的大小也算進剩餘空間(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:剩餘磁碟 5,000,000,000;佇列已有排隊中的 qwen2.5:7b(第 1 筆的 0.5b-instruct 先下載中)
    downloadable(fakes, disk_free=5_000_000_000)
    set_library(fakes, {**MANIFEST_SIZES, "qwen2.5:0.5b-instruct": 0})
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:0.5b-instruct", QWEN_7B)

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_SMALL]})
    added = await ui_client.post("/api/downloads", json={"models": [QWEN_SMALL]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    estimate = estimated.json()
    assert (estimate.get("fits"), estimate.get("pendingQueueBytes")) == (False, QWEN_7B_BYTES)
    assert (added.status_code, error_code(added)) == (409, "DISK_SPACE_INSUFFICIENT")
    assert [model for model, _ in states(after)] == ["qwen2.5:0.5b-instruct", QWEN_7B]


# ---------------------------------------------------------------- US3-API-14


async def test_讀不到剩餘空間時不加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.remote_ollama.pull_model.returns([{"status": "success"}])
    await open_ready(ui_client)
    fakes.colab.probe_resources.raises("COLAB_UNREACHABLE", "連不到執行環境")

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [QWEN_SMALL]})
    after = await queue(ui_client)

    # Assert
    body = response.json() if response.status_code == 503 else {}
    assert (response.status_code, body.get("code"), body.get("reasonCode")) == (503, "DISK_SPACE_UNKNOWN", "COLAB_UNREACHABLE")
    assert states(after) == []


# ---------------------------------------------------------------- US3-API-15


async def test_沒有工作階段時不加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [QWEN_SMALL]})
    after = await queue(ui_client)

    # Assert
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")
    assert states(after) == []


# ---------------------------------------------------------------- US3-API-16


async def test_一批裡有已下載或已排隊的模型時整批不加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:tags 已有 qwen2.5:0.5b;佇列有排隊中的 qwen2.5:7b(第 1 筆的 0.5b-instruct 先下載中)
    downloadable(fakes)
    set_library(fakes, {**MANIFEST_SIZES, "qwen2.5:0.5b-instruct": 0})
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:0.5b-instruct", QWEN_7B)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))

    # Act
    first = await ui_client.post("/api/downloads", json={"models": [QWEN_SMALL, QWEN_MID]})
    after_first = await queue(ui_client)
    second = await ui_client.post("/api/downloads", json={"models": [QWEN_7B]})
    after_second = await queue(ui_client)
    hold.release()

    # Assert
    assert (first.status_code, error_code(first)) == (409, "MODEL_ALREADY_DOWNLOADED")
    assert QWEN_MID not in [model for model, _ in states(after_first)]
    assert (second.status_code, error_code(second)) == (409, "DOWNLOAD_ALREADY_QUEUED")
    assert [model for model, _ in states(after_second)] == ["qwen2.5:0.5b-instruct", QWEN_7B]


# ---------------------------------------------------------------- US3-API-17


async def test_只能在雲端執行的版本不排進佇列(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen3-coder", tag="480b-cloud").raises("LIBRARY_CLOUD_ONLY", "layers 是空的")
    fakes.remote_ollama.pull_model.returns([{"status": "success"}])
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen3-coder:480b-cloud"]})
    after = await queue(ui_client)

    # Assert
    assert (response.status_code, error_code(response)) == (422, "LIBRARY_CLOUD_ONLY")
    assert states(after) == []


def insert_jobs(db_path: Any, *jobs: tuple[str, str, str | None], sizes: dict[str, int] = MANIFEST_SIZES) -> None:
    """直接寫入 `download_jobs`(模型, 狀態, reason_code),依序排在佇列裡;大小取自 `sizes`。"""
    conn = connect(db_path)
    for position, (model, state, reason) in enumerate(jobs, start=1):
        pending = model if state in ("queued", "downloading") else None
        conn.execute(
            "INSERT INTO download_jobs (model, pending_model, queue_position, size_bytes, state, reason_code, added_at)"
            " VALUES (?, ?, ?, ?, ?, ?, '2026-11-09T09:00:00Z')",
            (model, pending, position, sizes[model], state, reason),
        )
    conn.close()


# ---------------------------------------------------------------- US3-API-20


async def test_重新排隊排到最後_清除已完成只清完成的(ui_client: httpx.AsyncClient, fakes: Any, db_path: Any) -> None:
    # Arrange:依序有 completed 的 A、failed 的 B(SESSION_ENDED)、queued 的 C;工作階段就緒(重新排隊前要讀執行環境上的模型清單)
    downloadable(fakes)
    await open_ready(ui_client)
    insert_jobs(db_path, (QWEN_SMALL, "completed", None), (QWEN_7B, "failed", "SESSION_ENDED"), (QWEN_MID, "queued", None))
    ids = {job["model"]: job["id"] for job in (await queue(ui_client))["jobs"]}

    # Act
    retried = await ui_client.post(f"/api/downloads/{ids[QWEN_7B]}/retry")
    after_retry = await queue(ui_client)
    cleared = await ui_client.post("/api/downloads/clear-completed")
    after_clear = await queue(ui_client)

    # Assert
    assert (retried.status_code, retried.json().get("state")) == (200, "queued")
    assert [model for model, _ in states(after_retry)] == [QWEN_SMALL, QWEN_MID, QWEN_7B]
    assert (cleared.status_code, cleared.json().get("removedIds")) == (200, [ids[QWEN_SMALL]])
    assert states(after_clear) == [(QWEN_MID, "queued"), (QWEN_7B, "queued")]


# ---------------------------------------------------------------- US3-API-27


async def test_背景下載時經_Ollama_相容端點的推論照常立即回應(live_servers: Any, fakes: Any) -> None:
    # Arrange:pull 每 0.1 秒一行、持續 3 秒;generate 立即回應
    downloadable(fakes)
    pacer, log = Pacer(0.1), []
    fakes.remote_ollama.pull_model.side_effect(paced_pull(pacer, 30, log))
    fakes.server.add("POST", "/api/generate", JsonReply({"model": QWEN_SMALL, "response": "你好", "done": True}))
    pacing = asyncio.create_task(pacer.run())
    async with (
        httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as ui,
        httpx.AsyncClient(base_url=live_servers.ollama_url, timeout=5.0) as ollama,
    ):
        await open_ready(ui)
        await ui.post("/api/downloads", json={"models": [QWEN_7B]})
        await asyncio.sleep(0.5)

        # Act
        results = []
        for _ in range(5):
            started = time.monotonic()
            response = await ollama.post("/api/generate", json={"model": QWEN_SMALL, "prompt": "你好", "stream": False})
            results.append((response.status_code, time.monotonic() - started))
        pull_still_running = not any(kind == "end" for kind, _, _ in log)
    pacing.cancel()

    # Assert
    assert all(status == 200 and elapsed <= 0.2 for status, elapsed in results), results
    assert pull_still_running


# ---------------------------------------------------------------- US2-API-01


async def test_試算時模型庫連不到_回_502_指出是哪一個模型_不回部分試算(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").raises(
        "LIBRARY_UNREACHABLE", "ConnectError: [Errno -2] Name or service not known"
    )
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_SMALL, QWEN_7B]})

    # Assert
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    assert (response.status_code, body.get("code"), body.get("model"), "totalBytes" in body) == (
        502,
        "LIBRARY_UNREACHABLE",
        QWEN_7B,
        False,
    )


# ---------------------------------------------------------------- US2-API-02


async def test_試算時模型庫逾時_回_504_訊息是固定的繁中說明(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_7B]})

    # Assert
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    assert (response.status_code, body.get("code"), body.get("model"), body.get("message")) == (
        504,
        "LIBRARY_TIMEOUT",
        QWEN_7B,
        MESSAGES["LIBRARY_TIMEOUT"],
    )


def body_of(response: httpx.Response) -> dict[str, Any]:
    """回應本文;不是 JSON 時(例如未處理的例外變成的 500)是空 dict。"""
    return response.json() if response.headers.get("content-type", "").startswith("application/json") else {}


def manifest_tags(fakes: Any) -> list[str]:
    """`get_manifest` 依序被呼叫的版本。"""
    return [call.kwargs["tag"] for call in fakes.model_library.get_manifest.calls]


# ---------------------------------------------------------------- US2-API-03


async def test_試算遇到第一個失敗就停_不再取後面的_manifest(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="0.5b").raises("LIBRARY_SERVER_ERROR", "HTTP 503")
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_SMALL, QWEN_MID, QWEN_7B]})

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model"), fakes.model_library.get_manifest.call_count) == (
        502,
        "LIBRARY_SERVER_ERROR",
        QWEN_SMALL,
        1,
    )


# ---------------------------------------------------------------- US2-API-04


async def test_試算時沒寫版本的名稱以_latest_回報是哪一個模型(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="latest").raises("LIBRARY_BAD_RESPONSE", "manifest is not JSON")
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_SMALL, "qwen2.5"]})

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (502, "LIBRARY_BAD_RESPONSE", "qwen2.5:latest")


# ---------------------------------------------------------------- US2-API-05


async def test_試算時找不到的版本_指出是它_且之後的模型不再取(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_SMALL, "qwen2.5:999b", QWEN_7B]})

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model"), manifest_tags(fakes)) == (
        404,
        "LIBRARY_NOT_FOUND",
        "qwen2.5:999b",
        ["0.5b", "999b"],
    )


# ---------------------------------------------------------------- US2-API-06


async def test_試算時只能在雲端執行的版本_回_422_帶固定訊息(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="gpt-oss", tag="120b-cloud").raises("LIBRARY_CLOUD_ONLY", "gpt-oss:120b-cloud is cloud only")
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_SMALL, "gpt-oss:120b-cloud"]})

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model"), body.get("message")) == (
        422,
        "LIBRARY_CLOUD_ONLY",
        "gpt-oss:120b-cloud",
        MESSAGES["LIBRARY_CLOUD_ONLY"],
    )


def hold_pulls(fakes: Any) -> Gate:
    """每一筆 `pull_model` 都停在同一個閘門前(加入了就看得到下載中或排隊中)。"""
    hold = Gate()
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: [{"status": "pulling manifest"}, hold, {"status": "success"}])
    return hold


# ---------------------------------------------------------------- US2-API-07


async def test_加入時找不到的版本整批不加入_指出是它_也不下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [QWEN_SMALL, "qwen2.5:999b", QWEN_7B]})
    await asyncio.sleep(0.1)
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (404, "LIBRARY_NOT_FOUND", "qwen2.5:999b")
    assert (after["jobs"], manifest_tags(fakes), fakes.remote_ollama.pull_model.call_count) == ([], ["0.5b", "999b"], 0)


# ---------------------------------------------------------------- US2-API-08


async def test_加入時有只能在雲端執行的版本整批不加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="gpt-oss", tag="120b-cloud").raises("LIBRARY_CLOUD_ONLY", "cloud only")
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [QWEN_7B, "gpt-oss:120b-cloud"]})
    await asyncio.sleep(0.1)
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (422, "LIBRARY_CLOUD_ONLY", "gpt-oss:120b-cloud")
    assert after["jobs"] == []


# ---------------------------------------------------------------- US2-API-09


async def test_加入時第三個取不到大小_前兩個也不留在佇列(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_UNREACHABLE", "ConnectError: connection refused")
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [QWEN_SMALL, QWEN_MID, QWEN_7B]})
    await asyncio.sleep(0.1)
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (502, "LIBRARY_UNREACHABLE", QWEN_7B)
    assert after["jobs"] == []


# ---------------------------------------------------------------- US2-API-10


async def test_加入時模型庫逾時_回_504_固定訊息_佇列不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [QWEN_7B]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model"), body.get("message")) == (
        504,
        "LIBRARY_TIMEOUT",
        QWEN_7B,
        MESSAGES["LIBRARY_TIMEOUT"],
    )
    assert after["jobs"] == []


# ---------------------------------------------------------------- US2-API-11


async def test_加入失敗時_UI_沒有收到任何_download_updated(live_servers: Any, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="1.5b").raises("LIBRARY_SERVER_ERROR", "HTTP 503")
    hold = hold_pulls(fakes)
    updates: list[tuple[float, str]] = []
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        async with client.stream("GET", "/api/events") as stream:

            async def collect() -> None:
                async for name, payload in sse_events(stream):
                    if name == "download.updated":
                        updates.append((time.monotonic(), payload["job"]["model"]))

            collector = asyncio.create_task(collect())
            await asyncio.sleep(0.1)

            # Act
            first_start = time.monotonic()
            first = await client.post("/api/downloads", json={"models": [QWEN_SMALL, QWEN_MID]})
            await asyncio.sleep(0.5)
            second_start = time.monotonic()
            await client.post("/api/downloads", json={"models": [QWEN_7B]})
            await asyncio.sleep(1.0)
            collector.cancel()
            hold.release()

    # Assert
    body = body_of(first)
    assert (first.status_code, body.get("code"), body.get("model")) == (502, "LIBRARY_SERVER_ERROR", QWEN_MID)
    assert [model for at, model in updates if first_start <= at < second_start] == []
    assert QWEN_7B in [model for at, model in updates if at >= second_start]


# ---------------------------------------------------------------- US2-API-12


async def test_加入時沒寫版本的名稱以_latest_回報_佇列不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="latest").raises("LIBRARY_BAD_RESPONSE", "manifest layers is not a list")
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (502, "LIBRARY_BAD_RESPONSE", "qwen2.5:latest")
    assert after["jobs"] == []


# ---------------------------------------------------------------- US2-API-13


async def test_模型庫失敗時佇列與精選清單不受影響_下載中的照常完成(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:下載中 qwen2.5:0.5b-instruct、排隊中 qwen2.5:7b、精選清單有 qwen2.5:7b
    downloadable(fakes)
    set_library(fakes, {**MANIFEST_SIZES, "qwen2.5:0.5b-instruct": 0})
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:0.5b-instruct", QWEN_7B)
    await ui_client.post("/api/curated", json={"name": QWEN_7B})
    curated_before = (await ui_client.get("/api/curated")).json()["items"]
    assert [item["name"] for item in curated_before] == [QWEN_7B]
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="1.5b").raises("LIBRARY_UNREACHABLE", "ConnectError")

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [QWEN_MID]})
    during = await queue(ui_client)
    curated_after = (await ui_client.get("/api/curated")).json()["items"]
    pulls_before_release = [call.kwargs["model"] for call in fakes.remote_ollama.pull_model.calls]
    hold.release()
    done = await wait_queue(ui_client, lambda q: states(q)[:1] == [("qwen2.5:0.5b-instruct", "completed")], timeout=2.0)

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code")) == (502, "LIBRARY_UNREACHABLE")
    assert states(during) == [("qwen2.5:0.5b-instruct", "downloading"), (QWEN_7B, "queued")]
    assert curated_after == curated_before
    assert pulls_before_release == ["qwen2.5:0.5b-instruct"]
    assert states(done)[:1] == [("qwen2.5:0.5b-instruct", "completed")]


# ---------------------------------------------------------------- US2-API-14


async def test_試算失敗的回應本文不含底層的網址與堆疊(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").raises(
        "LIBRARY_SERVER_ERROR",
        "Server error '503 Service Unavailable' for url 'https://registry.ollama.ai/v2/library/qwen2.5/manifests/7b' "
        "Traceback (most recent call last)",
    )
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_7B]})

    # Assert
    body = body_of(response)
    assert response.status_code == 502 and body.get("code") == "LIBRARY_SERVER_ERROR"
    assert "registry.ollama.ai" not in response.text
    assert "Traceback" not in response.text
    assert set(body) == {"code", "message", "model"}
    assert body["message"] == MESSAGES["LIBRARY_SERVER_ERROR"]


# ---------------------------------------------------------------- US2-API-15

LIBRARY_CODES = [
    "LIBRARY_NOT_FOUND",
    "LIBRARY_CLOUD_ONLY",
    "LIBRARY_UNREACHABLE",
    "LIBRARY_SERVER_ERROR",
    "LIBRARY_BAD_RESPONSE",
    "LIBRARY_TIMEOUT",
]


async def test_同一個代碼對不同模型回同一句繁中訊息_並帶退路(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:替身依「目前要測的代碼」丟錯,7b 與 1.5b 各帶不同的英文說明
    downloadable(fakes)
    current = {"code": ""}
    notes = {"7b": "failed A https://registry.ollama.ai/a", "1.5b": "failed B https://registry.ollama.ai/b"}

    def fail(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AdapterError(current["code"], notes[kwargs["tag"]])

    fakes.model_library.get_manifest.side_effect(fail)
    hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    messages: dict[str, list[str]] = {}
    for code in LIBRARY_CODES:
        current["code"] = code
        responses = [await ui_client.post("/api/downloads", json={"models": [model]}) for model in (QWEN_7B, QWEN_MID)]
        messages[code] = [body_of(response).get("message", "") for response in responses]

    # Assert
    assert {code: len(set(texts)) for code, texts in messages.items()} == {code: 1 for code in LIBRARY_CODES}
    assert all(any("一" <= char <= "鿿" for char in texts[0]) for texts in messages.values())
    with_fallback = ["LIBRARY_UNREACHABLE", "LIBRARY_TIMEOUT", "LIBRARY_SERVER_ERROR", "LIBRARY_BAD_RESPONSE"]
    assert all("從精選清單挑選或直接輸入名稱" in messages[code][0] for code in with_fallback)


# ---- 003 US1-API-01


async def test_執行環境上已有_latest_時試算沒寫版本的名稱回已下載_不取_manifest(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes, tag("qwen2.5:latest", 4_683_087_332))
    await open_ready(ui_client)
    fakes.model_library.get_manifest.reset_calls()

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (409, "MODEL_ALREADY_DOWNLOADED", "qwen2.5:latest")
    assert fakes.model_library.get_manifest.call_count == 0


# ---- 003 US1-API-02


async def test_執行環境上已有_latest_時加入沒寫版本的名稱回已下載_佇列不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes, tag("qwen2.5:latest", 4_683_087_332))
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5"]})
    await asyncio.sleep(0.1)
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (409, "MODEL_ALREADY_DOWNLOADED", "qwen2.5:latest")
    assert after["jobs"] == []
    assert fakes.remote_ollama.pull_model.call_count == 0


# ---- 003 US1-API-03


async def test_佇列裡已有_latest_時試算沒寫版本的名稱回已在佇列(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:0.5b", "qwen2.5:latest")

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (409, "DOWNLOAD_ALREADY_QUEUED", "qwen2.5:latest")
    assert states(after) == [("qwen2.5:0.5b", "downloading"), ("qwen2.5:latest", "queued")]


# ---- 003 US1-API-04


async def test_佇列裡下載中的_latest_讓加入沒寫版本的名稱回已在佇列_不回_500(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:latest", "qwen2.5:7b")

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (409, "DOWNLOAD_ALREADY_QUEUED", "qwen2.5:latest")
    assert states(after) == [("qwen2.5:latest", "downloading"), ("qwen2.5:7b", "queued")]


# ---- 003 US1-API-05


async def test_執行環境上有_latest_時加入寫了版本的_7b_照常加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes, tag("qwen2.5:latest", 4_683_087_332))
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5:7b"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    jobs = response.json().get("jobs", []) if response.status_code == 201 else []
    assert response.status_code == 201
    assert [job["model"] for job in jobs] == ["qwen2.5:7b"]
    assert [model for model, _ in states(after)] == ["qwen2.5:7b"]


# ---- 003 US1-API-06


async def test_試算同一批補過版本後相同的只算一次(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes)
    await open_ready(ui_client)
    fakes.remote_ollama.list_local_models.reset_calls()
    fakes.model_library.get_manifest.reset_calls()

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5", "qwen2.5:latest"]})

    # Assert
    estimate = response.json() if response.status_code == 200 else {}
    assert response.status_code == 200
    assert [item["name"] for item in estimate.get("items", [])] == ["qwen2.5:latest"]
    assert estimate.get("totalBytes") == 4_683_087_332
    assert fakes.model_library.get_manifest.call_count == 1
    assert fakes.remote_ollama.list_local_models.call_count == 1


# ---- 003 US1-API-07


async def test_加入一批時補過版本後相同的只加入一筆_保留第一次出現的順序(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes)
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post(
        "/api/downloads", json={"models": ["qwen2.5:0.5b", "qwen2.5", "qwen2.5:7b", "qwen2.5:latest"]}
    )
    after = await queue(ui_client)
    hold.release()

    # Assert
    jobs = response.json().get("jobs", []) if response.status_code == 201 else []
    assert response.status_code == 201
    assert [job["model"] for job in jobs] == ["qwen2.5:0.5b", "qwen2.5:latest", "qwen2.5:7b"]
    assert [model for model, _ in states(after)] == ["qwen2.5:0.5b", "qwen2.5:latest", "qwen2.5:7b"]


# ---- 003 US1-API-08


async def test_加入一批時寫了版本的相同名稱也只加入一筆(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_tags(fakes)
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5:7b", "qwen2.5:7b"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    jobs = response.json().get("jobs", []) if response.status_code == 201 else []
    assert response.status_code == 201
    assert [job["model"] for job in jobs] == ["qwen2.5:7b"]
    assert [model for model, _ in states(after)] == ["qwen2.5:7b"]


# ---- 003 US1-API-09


async def test_一批裡有一個已在佇列時整批不加入_回第一個重複的(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:1.5b", "qwen2.5:latest")

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5:0.5b", "qwen2.5", "qwen2.5:7b"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = body_of(response)
    assert (response.status_code, body.get("code"), body.get("model")) == (409, "DOWNLOAD_ALREADY_QUEUED", "qwen2.5:latest")
    assert states(after) == [("qwen2.5:1.5b", "downloading"), ("qwen2.5:latest", "queued")]


# ---- 003 US1-API-10


async def test_佇列裡同名的那筆下載失敗時加入沒寫版本的名稱照常加入(ui_client: httpx.AsyncClient, fakes: Any, db_path: Any) -> None:
    # Arrange
    insert_jobs(db_path, ("qwen2.5:latest", "failed", "OLLAMA_PULL_FAILED"), sizes=LATEST_SIZES)
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes)
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    jobs = response.json().get("jobs", []) if response.status_code == 201 else []
    assert response.status_code == 201
    assert [(job["model"], job["state"] in ("queued", "downloading")) for job in jobs] == [("qwen2.5:latest", True)]
    assert [(job["model"], job["state"]) for job in after["jobs"]][0] == ("qwen2.5:latest", "failed")
    assert [(job["model"], job["state"] in ("queued", "downloading")) for job in after["jobs"]][1:] == [("qwen2.5:latest", True)]


# ---- 003 US1-API-11


async def test_佇列裡同名的那筆已完成時加入沒寫版本的名稱照常加入(ui_client: httpx.AsyncClient, fakes: Any, db_path: Any) -> None:
    # Arrange
    insert_jobs(db_path, ("qwen2.5:latest", "completed", None), sizes=LATEST_SIZES)
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes)
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    jobs = response.json().get("jobs", []) if response.status_code == 201 else []
    assert response.status_code == 201
    assert [job["model"] for job in jobs] == ["qwen2.5:latest"]
    assert [job["state"] for job in after["jobs"] if job["model"] == "qwen2.5:latest"][0] == "completed"
    assert [job["state"] in ("queued", "downloading") for job in after["jobs"] if job["model"] == "qwen2.5:latest"][1:] == [True]


# ---- 003 US1-API-13


async def test_一批裡先比已下載再比佇列_回合併後順序的第一個重複(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:0.5b", "qwen2.5:7b")
    set_tags(fakes, tag("qwen2.5:latest", 4_683_087_332))

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5:7b", "qwen2.5"]})
    added = await ui_client.post("/api/downloads", json={"models": ["qwen2.5", "qwen2.5:7b"]})
    hold.release()

    # Assert
    assert (estimated.status_code, body_of(estimated).get("code"), body_of(estimated).get("model")) == (
        409,
        "DOWNLOAD_ALREADY_QUEUED",
        "qwen2.5:7b",
    )
    assert (added.status_code, body_of(added).get("code"), body_of(added).get("model")) == (
        409,
        "MODEL_ALREADY_DOWNLOADED",
        "qwen2.5:latest",
    )


# ---- 003 US1-API-14


async def test_沒有工作階段時試算回沒有就緒的工作階段_不讀模型清單也不取_manifest(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})

    # Assert
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")
    assert fakes.remote_ollama.list_local_models.call_count == 0
    assert fakes.model_library.get_manifest.call_count == 0


# ---- 003 US1-API-15


async def test_開啟中試算與加入都回沒有就緒的工作階段_不讀模型清單(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    create_gate = fakes.colab.create_session.gate()
    opened = await ui_client.post("/api/session", json={"runtimeType": T4})
    await asyncio.sleep(0.1)
    opening = (await ui_client.get("/api/session")).json().get("state")
    fakes.remote_ollama.list_local_models.reset_calls()

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})
    added = await ui_client.post("/api/downloads", json={"models": ["qwen2.5"]})
    list_calls = fakes.remote_ollama.list_local_models.call_count
    create_gate.release()
    await wait_for_state(ui_client, "ready")

    # Assert
    assert (opened.status_code, opening) == (202, "opening")
    assert (estimated.status_code, error_code(estimated)) == (503, "NO_READY_SESSION")
    assert (added.status_code, error_code(added)) == (503, "NO_READY_SESSION")
    assert list_calls == 0


# ---- 003 US1-API-16


async def test_本文不是合法_JSON_時試算與加入先回_400_不看工作階段(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    broken = {"content": '{"models": [', "headers": {"Content-Type": "application/json"}}

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", **broken)
    added = await ui_client.post("/api/downloads", **broken)
    control = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})

    # Assert
    assert (estimated.status_code, error_code(estimated)) == (400, "INVALID_REQUEST_BODY")
    assert (added.status_code, error_code(added)) == (400, "INVALID_REQUEST_BODY")
    assert (control.status_code, error_code(control)) == (503, "NO_READY_SESSION")


# ---- 003 US1-API-17


async def test_讀執行環境的模型清單失敗時試算依代碼回_502_或_504_不帶模型名稱(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    fakes.model_library.get_manifest.reset_calls()
    fakes.colab.probe_resources.reset_calls()

    # Act
    outcomes = []
    for code in ("OLLAMA_UNREACHABLE", "OLLAMA_BAD_RESPONSE", "OLLAMA_TIMEOUT"):
        fakes.remote_ollama.list_local_models.raises(code)
        response = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})
        outcomes.append((response.status_code, body_of(response).get("code"), "model" in body_of(response)))

    # Assert
    assert outcomes == [
        (502, "OLLAMA_UNREACHABLE", False),
        (502, "OLLAMA_BAD_RESPONSE", False),
        (504, "OLLAMA_TIMEOUT", False),
    ]
    assert fakes.model_library.get_manifest.call_count == 0
    assert fakes.colab.probe_resources.call_count == 0


# ---- 003 US1-API-18


async def test_讀執行環境的模型清單失敗時加入依代碼回_502_或_504_佇列不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:0.5b")
    fakes.model_library.get_manifest.reset_calls()

    # Act
    outcomes = []
    for code in ("OLLAMA_UNREACHABLE", "OLLAMA_BAD_RESPONSE", "OLLAMA_TIMEOUT"):
        fakes.remote_ollama.list_local_models.raises(code)
        response = await ui_client.post("/api/downloads", json={"models": ["qwen2.5", "qwen2.5:7b"]})
        outcomes.append((response.status_code, body_of(response).get("code"), "model" in body_of(response)))
    after = await queue(ui_client)
    hold.release()

    # Assert
    assert outcomes == [
        (502, "OLLAMA_UNREACHABLE", False),
        (502, "OLLAMA_BAD_RESPONSE", False),
        (504, "OLLAMA_TIMEOUT", False),
    ]
    assert states(after) == [("qwen2.5:0.5b", "downloading")]
    assert fakes.model_library.get_manifest.call_count == 0


# ---- 003 US1-API-19


async def test_一批裡有取不到_manifest_的版本時合併後的名稱只取一次_整批不加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes)
    hold = hold_pulls(fakes)
    await open_ready(ui_client)
    batch = {"models": ["qwen2.5", "qwen2.5:latest", "qwen2.5:999b"]}

    # Act
    fakes.model_library.get_manifest.reset_calls()
    estimated = await ui_client.post("/api/downloads/estimate", json=batch)
    estimate_tags = manifest_tags(fakes)
    fakes.model_library.get_manifest.reset_calls()
    added = await ui_client.post("/api/downloads", json=batch)
    add_tags = manifest_tags(fakes)
    after = await queue(ui_client)
    hold.release()

    # Assert
    assert (estimated.status_code, body_of(estimated).get("code"), body_of(estimated).get("model")) == (
        404,
        "LIBRARY_NOT_FOUND",
        "qwen2.5:999b",
    )
    assert estimate_tags == ["latest", "999b"]
    assert (added.status_code, body_of(added).get("code")) == (404, "LIBRARY_NOT_FOUND")
    assert add_tags == ["latest", "999b"]
    assert after["jobs"] == []


# ---- 003 US1-API-20


async def test_同一批補過版本後相同的名稱只算一次大小_試算與加入的空間檢查一致(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes, disk_free=5_000_000_000)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes)
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5", "qwen2.5:latest"]})
    control = await ui_client.post("/api/downloads", json={"models": ["qwen2.5:latest", "qwen2.5:7b"]})
    added = await ui_client.post("/api/downloads", json={"models": ["qwen2.5", "qwen2.5:latest"]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    assert estimated.json().get("fits") is True
    assert (control.status_code, body_of(control).get("code"), "model" in body_of(control)) == (409, "DISK_SPACE_INSUFFICIENT", False)
    assert added.status_code == 201
    assert [model for model, _ in states(after)] == ["qwen2.5:latest"]


# ---- 003 US1-API-21


async def test_試算先檢查重複再讀剩餘磁碟_重複的模型不因讀不到磁碟而回_503(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes, tag("qwen2.5:latest", 4_683_087_332))
    await open_ready(ui_client)
    fakes.colab.probe_resources.raises("COLAB_UNREACHABLE", "連不到執行環境")

    # Act
    duplicated = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})
    control = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5:7b"]})

    # Assert
    assert (duplicated.status_code, body_of(duplicated).get("code")) == (409, "MODEL_ALREADY_DOWNLOADED")
    assert (control.status_code, body_of(control).get("code"), body_of(control).get("reasonCode")) == (
        503,
        "DISK_SPACE_UNKNOWN",
        "COLAB_UNREACHABLE",
    )


# ---- 003 US1-API-22


async def test_兩個加入請求交錯時後到的整批不加入_回已在佇列_先到的照常下載(live_servers: Any, fakes: Any) -> None:
    # Arrange:請求 2 停在 `llama3.2` 的 manifest(已過重複檢查),請求 1 趁這時加入 `qwen2.5`
    downloadable(fakes)
    set_tags(fakes)
    hold = hold_pulls(fakes)
    first_done = threading.Event()

    async def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["name"] == "llama3.2":
            while not first_done.is_set():
                await asyncio.sleep(0.005)
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": LATEST_SIZES[f"{kwargs['name']}:{kwargs['tag']}"]}

    fakes.model_library.get_manifest.side_effect(manifest)
    updates: list[tuple[float, str]] = []
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        async with client.stream("GET", "/api/events") as stream:

            async def collect() -> None:
                async for name, payload in sse_events(stream):
                    if name == "download.updated":
                        updates.append((time.monotonic(), payload["job"]["model"]))

            collector = asyncio.create_task(collect())
            await asyncio.sleep(0.1)

            # Act
            second = asyncio.create_task(client.post("/api/downloads", json={"models": ["llama3.2", "qwen2.5:latest"]}))
            deadline = time.monotonic() + 5.0
            while not any(call.kwargs["name"] == "llama3.2" for call in fakes.model_library.get_manifest.calls):
                assert time.monotonic() < deadline, "請求 2 沒有走到 llama3.2 的 manifest"
                await asyncio.sleep(0.005)
            first = await client.post("/api/downloads", json={"models": ["qwen2.5"]})
            released_at = time.monotonic()
            first_done.set()
            second_response = await second
            await asyncio.sleep(0.5)
            after = await queue(client)
            collector.cancel()
            hold.release()

    # Assert
    first_jobs = first.json().get("jobs", [{}]) if first.status_code == 201 else [{}]
    assert (first.status_code, first_jobs[0].get("model")) == (201, "qwen2.5:latest")
    body = body_of(second_response)
    assert (second_response.status_code, body.get("code"), body.get("model")) == (409, "DOWNLOAD_ALREADY_QUEUED", "qwen2.5:latest")
    assert states(after) == [("qwen2.5:latest", "downloading")]
    assert [model for at, model in updates if at >= released_at and model == "llama3.2:latest"] == []


# ---- 003 US1-API-23


async def test_判定重複時不為任何模型取_manifest(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, "qwen2.5:1.5b", "qwen2.5:latest")
    fakes.model_library.get_manifest.reset_calls()
    batch = {"models": ["qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5"]}

    # Act
    queued_estimate = await ui_client.post("/api/downloads/estimate", json=batch)
    queued_add = await ui_client.post("/api/downloads", json=batch)
    set_tags(fakes, tag("qwen2.5:latest", 4_683_087_332))
    downloaded_estimate = await ui_client.post("/api/downloads/estimate", json=batch)
    downloaded_add = await ui_client.post("/api/downloads", json=batch)
    manifest_calls = fakes.model_library.get_manifest.call_count
    hold.release()

    # Assert
    assert [(r.status_code, body_of(r).get("code")) for r in (queued_estimate, queued_add)] == [(409, "DOWNLOAD_ALREADY_QUEUED")] * 2
    assert [(r.status_code, body_of(r).get("code")) for r in (downloaded_estimate, downloaded_add)] == [
        (409, "MODEL_ALREADY_DOWNLOADED")
    ] * 2
    assert manifest_calls == 0


# ---- 003 US1-API-24

ALREADY_DOWNLOADED, ALREADY_QUEUED, ALREADY_DOWNLOADING, SAME_BATCH = "已下載", "排隊中", "下載中", "同一批"


async def arrange_duplicate(client: httpx.AsyncClient, fakes: Any, situation: str) -> Gate:
    """依情況讓 `qwen2.5:latest` 已下載、排隊中、下載中,或什麼都不做(同一批);回傳要在最後放行的閘門。"""
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(client)
    if situation == ALREADY_QUEUED:
        return await enqueue_waiting(client, fakes, "qwen2.5:0.5b", "qwen2.5:latest")
    if situation == ALREADY_DOWNLOADING:
        return await enqueue_waiting(client, fakes, "qwen2.5:latest")
    if situation == ALREADY_DOWNLOADED:
        set_tags(fakes, tag("qwen2.5:latest", 4_683_087_332))
    return hold_pulls(fakes)


@pytest.mark.parametrize("operation", ["試算", "加入"])
@pytest.mark.parametrize("situation", [ALREADY_DOWNLOADED, ALREADY_QUEUED, ALREADY_DOWNLOADING, SAME_BATCH])
@pytest.mark.parametrize("name", ["qwen2.5", "qwen2.5:latest"])
async def test_每一種重複的組合都照合約回應_不回_500(
    ui_client: httpx.AsyncClient, fakes: Any, name: str, situation: str, operation: str
) -> None:
    # Arrange
    hold = await arrange_duplicate(ui_client, fakes, situation)
    other = "qwen2.5:latest" if name == "qwen2.5" else "qwen2.5"
    models = [name, other] if situation == SAME_BATCH else [name]
    path = "/api/downloads/estimate" if operation == "試算" else "/api/downloads"

    # Act
    response = await ui_client.post(path, json={"models": models})
    after = await queue(ui_client)
    hold.release()

    # Assert
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    expected = {
        ALREADY_DOWNLOADED: (409, "MODEL_ALREADY_DOWNLOADED"),
        ALREADY_QUEUED: (409, "DOWNLOAD_ALREADY_QUEUED"),
        ALREADY_DOWNLOADING: (409, "DOWNLOAD_ALREADY_QUEUED"),
    }
    if situation != SAME_BATCH:
        assert (response.status_code, body.get("code")) == expected[situation]
    elif operation == "試算":
        assert (response.status_code, [item["name"] for item in body.get("items", [])]) == (200, ["qwen2.5:latest"])
    else:
        assert (response.status_code, [job["model"] for job in body.get("jobs", [])]) == (201, ["qwen2.5:latest"])
    active = [job for job in after["jobs"] if job["model"] == "qwen2.5:latest" and job["state"] in ("queued", "downloading")]
    assert len(active) <= 1


# ---- 003 US1-API-25


async def test_讀模型清單失敗的回應只有代碼與固定訊息_不含底層文字_試算與加入同一句(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_library(fakes, LATEST_SIZES)
    await open_ready(ui_client)
    leaked = "ConnectError: [Errno 111] Connection refused http://127.0.0.1:41234/api/tags Traceback (most recent call last)"

    # Act
    responses: list[tuple[str, str, httpx.Response]] = []
    for code in ("OLLAMA_UNREACHABLE", "OLLAMA_BAD_RESPONSE", "OLLAMA_TIMEOUT"):
        fakes.remote_ollama.list_local_models.raises(code, leaked)
        estimated = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})
        added = await ui_client.post("/api/downloads", json={"models": ["qwen2.5"]})
        responses += [(code, "試算", estimated), (code, "加入", added)]

    # Assert
    assert all("127.0.0.1:41234" not in r.text and "Traceback" not in r.text for _, _, r in responses)
    assert all(set(body_of(r)) == {"code", "message"} for _, _, r in responses)
    assert [(operation, body_of(r).get("message") == MESSAGES[code]) for code, operation, r in responses] == [
        (operation, True) for _, operation, _ in responses
    ]


# ---- 004 US4-API-12


async def test_試算同一批的_hf_co_與官方模型_各依來源取大小_一起加總(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES})
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [HF_Q4, QWEN_7B]})

    # Assert
    estimate = body_of(response)
    assert response.status_code == 200
    assert [(item["name"], item["sizeBytes"]) for item in estimate.get("items", [])] == [
        (HF_Q4, 105_455_145),
        (QWEN_7B, 4_683_087_332),
    ]
    assert estimate.get("totalBytes") == 4_788_542_477
    assert (estimate.get("freeDiskBytes"), estimate.get("fits")) == (DISK_FREE, True)
    assert estimate.get("estimatedSeconds") == 95
    assert [call.kwargs for call in fakes.huggingface.get_manifest.calls] == [
        {"author": "bartowski", "model": "SmolLM2-135M-Instruct-GGUF", "tag": "Q4_K_M"}
    ]
    assert [call.kwargs for call in fakes.model_library.get_manifest.calls] == [{"name": "qwen2.5", "tag": "7b"}]


# ---- 004 US4-API-13


async def test_加入同一批的_hf_co_與官方模型_依加入順序一個接一個下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES})
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads", json={"models": [HF_Q4, QWEN_7B]})
    during = await wait_queue(ui_client, lambda q: states(q)[:1] == [(HF_Q4, "downloading")])
    hold.release()
    final = await wait_queue(ui_client, lambda q: [state for _, state in states(q)] == ["completed", "completed"])

    # Assert
    accepted = body_of(response).get("jobs", [])
    assert response.status_code == 201
    assert [(job["model"], job["source"]) for job in accepted] == [(HF_Q4, "huggingface"), (QWEN_7B, "library")]
    assert states(during) == [(HF_Q4, "downloading"), (QWEN_7B, "queued")]
    assert [call.kwargs["model"] for call in fakes.remote_ollama.pull_model.calls] == [HF_Q4, QWEN_7B]
    assert [(job["model"], job["sizeBytes"]) for job in final["jobs"]] == [(HF_Q4, 105_455_145), (QWEN_7B, 4_683_087_332)]


# ---- 004 US4-API-14


async def test_加入_hf_co_模型後推出的_download_updated_帶來源_huggingface(live_servers: Any, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES})
    hold = hold_pulls(fakes)
    updates: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        async with client.stream("GET", "/api/events") as stream:

            async def collect() -> None:
                async for name, payload in sse_events(stream):
                    if name == "download.updated":
                        updates.append(payload["job"])

            collector = asyncio.create_task(collect())
            await asyncio.sleep(0.1)

            # Act
            await client.post("/api/downloads", json={"models": [HF_Q4]})
            deadline = time.monotonic() + 1.0
            while not updates and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            collector.cancel()
            hold.release()

    # Assert
    assert [(job["model"], job["source"]) for job in updates[:1]] == [(HF_Q4, "huggingface")]


# ---- 004 US4-API-15


async def test_hf_co_的大小也算進空間檢查_放不下時整批不加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes, disk_free=4_700_000_000)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES})
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": [HF_Q4, QWEN_7B]})
    refused = await ui_client.post("/api/downloads", json={"models": [HF_Q4, QWEN_7B]})
    after = await queue(ui_client)
    control = await ui_client.post("/api/downloads", json={"models": [QWEN_7B]})
    hold.release()

    # Assert
    assert estimated.status_code == 200
    assert body_of(estimated).get("fits") is False
    assert (refused.status_code, error_code(refused)) == (409, "DISK_SPACE_INSUFFICIENT")
    assert "model" not in body_of(refused)
    assert after["jobs"] == []
    assert control.status_code == 201


# ---- 004 US4-API-16


async def test_試算時_hf_co_模型需要登入或量化版本無法下載_回_422_指出是哪一個(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_hf_refusals(fakes)
    await open_ready(ui_client)

    # Act
    needs_login = await ui_client.post("/api/downloads/estimate", json={"models": [QWEN_7B, HF_GEMMA]})
    missing_quant = await ui_client.post("/api/downloads/estimate", json={"models": [HF_Q4_L]})
    fakes.huggingface.get_manifest.reset_calls()
    not_gguf = await ui_client.post("/api/downloads/estimate", json={"models": [HF_NOT_GGUF]})

    # Assert
    assert (needs_login.status_code, error_code(needs_login), body_of(needs_login).get("model")) == (422, "HF_AUTH_REQUIRED", HF_GEMMA)
    assert (missing_quant.status_code, error_code(missing_quant)) == (422, "HF_QUANT_UNAVAILABLE")
    assert (not_gguf.status_code, error_code(not_gguf), body_of(not_gguf).get("model")) == (
        422,
        "HF_QUANT_UNAVAILABLE",
        f"{HF_NOT_GGUF}:latest",
    )
    assert [call.kwargs["tag"] for call in fakes.huggingface.get_manifest.calls] == ["latest"]


# ---- 004 US4-API-17


async def test_加入時_hf_co_模型被拒絕_整批不加入_也不影響下載中的(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_hf_refusals(fakes)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, QWEN_SMALL)

    # Act
    needs_login = await ui_client.post("/api/downloads", json={"models": [QWEN_7B, HF_GEMMA]})
    missing_quant = await ui_client.post("/api/downloads", json={"models": [HF_Q4_L]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    assert (needs_login.status_code, error_code(needs_login)) == (422, "HF_AUTH_REQUIRED")
    assert (missing_quant.status_code, error_code(missing_quant)) == (422, "HF_QUANT_UNAVAILABLE")
    assert states(after) == [(QWEN_SMALL, "downloading")]
    assert [call.kwargs["model"] for call in fakes.remote_ollama.pull_model.calls] == [QWEN_SMALL]


# ---- 004 US4-API-18


async def test_hf_co_取大小失敗時試算與加入依自己的代碼回_指出是哪一個_佇列不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    await open_ready(ui_client)
    outcomes: list[tuple[int, str | None, str | None]] = []
    library_manifest_calls: list[int] = []

    # Act
    for code in ("HF_UNREACHABLE", "HF_SERVER_ERROR", "HF_BAD_RESPONSE", "HF_TIMEOUT"):
        fakes.huggingface.get_manifest.raises(code)
        fakes.model_library.get_manifest.reset_calls()
        for path in ("/api/downloads/estimate", "/api/downloads"):
            response = await ui_client.post(path, json={"models": [HF_Q4, QWEN_7B]})
            outcomes.append((response.status_code, error_code(response), body_of(response).get("model")))
        library_manifest_calls.append(fakes.model_library.get_manifest.call_count)
    after = await queue(ui_client)

    # Assert
    assert outcomes == [
        (502, "HF_UNREACHABLE", HF_Q4),
        (502, "HF_UNREACHABLE", HF_Q4),
        (502, "HF_SERVER_ERROR", HF_Q4),
        (502, "HF_SERVER_ERROR", HF_Q4),
        (502, "HF_BAD_RESPONSE", HF_Q4),
        (502, "HF_BAD_RESPONSE", HF_Q4),
        (504, "HF_TIMEOUT", HF_Q4),
        (504, "HF_TIMEOUT", HF_Q4),
    ]
    assert library_manifest_calls == [0, 0, 0, 0]
    assert after["jobs"] == []


# ---- 004 US4-API-19


async def test_已下載的比對不分大小寫_hf_co_與官方名稱一樣_回應是使用者的寫法_不取_manifest(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange
    mixed_case = "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
    downloadable(fakes)
    set_hf(fakes, {mixed_case: HF_Q4_BYTES})
    set_library(fakes, LATEST_SIZES)
    set_tags(fakes, tag("hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m", HF_Q4_BYTES), tag("qwen2.5:latest", 4_683_087_332))
    await open_ready(ui_client)
    fakes.huggingface.get_manifest.reset_calls()
    fakes.model_library.get_manifest.reset_calls()

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": [mixed_case]})
    enqueued = await ui_client.post("/api/downloads", json={"models": [mixed_case]})
    official = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5:Latest"]})

    # Assert
    assert (estimated.status_code, error_code(estimated), body_of(estimated).get("model")) == (409, "MODEL_ALREADY_DOWNLOADED", mixed_case)
    assert (enqueued.status_code, error_code(enqueued)) == (409, "MODEL_ALREADY_DOWNLOADED")
    assert (official.status_code, error_code(official)) == (409, "MODEL_ALREADY_DOWNLOADED")
    assert (fakes.huggingface.get_manifest.call_count, fakes.model_library.get_manifest.call_count) == (0, 0)


# ---- 004 US4-API-20


async def test_已在佇列的比對不分大小寫_試算與加入都回已在佇列_整批不加入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    lowered = "hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m"
    typed = "hf.co/BARTOWSKI/SmolLM2-135M-Instruct-GGUF:Q4_k_m"
    downloadable(fakes)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES, lowered: HF_Q4_BYTES, typed: HF_Q4_BYTES})
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, QWEN_SMALL, HF_Q4)

    # Act
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": [lowered]})
    enqueued = await ui_client.post("/api/downloads", json={"models": [QWEN_7B, typed]})
    after = await queue(ui_client)
    hold.release()

    # Assert
    assert (estimated.status_code, error_code(estimated)) == (409, "DOWNLOAD_ALREADY_QUEUED")
    assert (enqueued.status_code, error_code(enqueued), body_of(enqueued).get("model")) == (409, "DOWNLOAD_ALREADY_QUEUED", typed)
    assert states(after) == [(QWEN_SMALL, "downloading"), (HF_Q4, "queued")]


# ---- 004 US4-API-21


async def test_同一批的合併不分大小寫_沒寫版本與_latest_是同一筆_與量化版本不是同一筆(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    base = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF"
    batch = [base, "hf.co/Bartowski/smollm2-135m-instruct-gguf:LATEST", HF_Q4]
    downloadable(fakes)
    set_hf(fakes, {f"{base}:latest": HF_Q4_BYTES, HF_Q4: HF_Q4_BYTES})
    hold = hold_pulls(fakes)
    await open_ready(ui_client)

    # Act
    fakes.huggingface.get_manifest.reset_calls()
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": batch})
    estimate_tags = [call.kwargs["tag"] for call in fakes.huggingface.get_manifest.calls]
    fakes.huggingface.get_manifest.reset_calls()
    enqueued = await ui_client.post("/api/downloads", json={"models": batch})
    after = await queue(ui_client)
    hold.release()

    # Assert
    estimate = body_of(estimated)
    assert estimated.status_code == 200
    assert [item["name"] for item in estimate.get("items", [])] == [f"{base}:latest", HF_Q4]
    assert estimate.get("totalBytes") == 210_910_290
    assert estimate_tags == ["latest", "Q4_K_M"]
    assert enqueued.status_code == 201
    assert [job["model"] for job in body_of(enqueued).get("jobs", [])] == [f"{base}:latest", HF_Q4]
    assert len(after["jobs"]) == 2


# ---- 004 US4-API-22


async def test_沒寫量化版本的_hf_co_名稱和已下載的量化版本是不同的名稱_照常試算(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    base = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF"
    downloadable(fakes)
    set_hf(fakes, {f"{base}:latest": HF_Q4_BYTES})
    set_tags(fakes, tag(HF_Q4, HF_Q4_BYTES))
    await open_ready(ui_client)

    # Act
    response = await ui_client.post("/api/downloads/estimate", json={"models": [base]})

    # Assert
    assert response.status_code == 200
    assert [item["name"] for item in body_of(response).get("items", [])] == [f"{base}:latest"]


# ---- 004 US4-API-23


async def test_模型名稱格式與空清單最先檢查_不需要工作階段_也不取_manifest(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    wrong_names = {
        "A": [QWEN_7B, "huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"],
        "B": ["HF.CO/bartowski/SmolLM2-135M-Instruct-GGUF"],
        "C": ["Qwen2.5:7b"],
        "D": ["hf.co/bartowski"],
        "E": ["hf.co/-bartowski/x"],
    }
    downloadable(fakes)
    fakes.huggingface.get_manifest.reset_calls()
    fakes.model_library.get_manifest.reset_calls()

    # Act
    wrong: dict[str, list[httpx.Response]] = {}
    for case, models in wrong_names.items():
        wrong[case] = [await ui_client.post(path, json={"models": models}) for path in ("/api/downloads/estimate", "/api/downloads")]
    empty = [await ui_client.post(path, json={"models": []}) for path in ("/api/downloads/estimate", "/api/downloads")]
    control = [
        await ui_client.post(path, json={"models": ["hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:q4_k_m"]})
        for path in ("/api/downloads/estimate", "/api/downloads")
    ]

    # Assert
    assert [(r.status_code, error_code(r)) for rs in wrong.values() for r in rs] == [(400, "INVALID_MODEL_NAME")] * 10
    assert [body_of(r).get("model") for r in wrong["A"]] == ["huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"] * 2
    assert [(r.status_code, error_code(r)) for r in empty] == [(400, "EMPTY_MODEL_LIST")] * 2
    assert [(r.status_code, error_code(r)) for r in control] == [(503, "NO_READY_SESSION")] * 2
    assert (fakes.huggingface.get_manifest.call_count, fakes.model_library.get_manifest.call_count) == (0, 0)


# ---- 004 US4-API-24


async def test_重新排隊前先看執行環境_已下載的回已下載_其他的照常排到佇列最後(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES})
    fakes.remote_ollama.pull_model.raises("OLLAMA_PULL_FAILED")
    await open_ready(ui_client)
    await ui_client.post("/api/downloads", json={"models": [HF_Q4, QWEN_7B]})
    failed = await wait_queue(ui_client, lambda q: [state for _, state in states(q)] == ["failed", "failed"])
    ids = {job["model"]: job["id"] for job in failed["jobs"]}
    set_tags(fakes, tag("hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m", HF_Q4_BYTES))
    hold = hold_pulls(fakes)

    # Act
    already = await ui_client.post(f"/api/downloads/{ids[HF_Q4]}/retry")
    control = await ui_client.post(f"/api/downloads/{ids[QWEN_7B]}/retry")
    after = await queue(ui_client)
    hold.release()

    # Assert
    assert (already.status_code, error_code(already)) == (409, "MODEL_ALREADY_DOWNLOADED")
    assert (control.status_code, body_of(control).get("state")) == (200, "queued")
    assert states(after) == [(HF_Q4, "failed"), (QWEN_7B, "queued")]


# ---- 004 US4-API-25


async def test_重新排隊找不到或不是失敗或讀不到執行環境時各回該有的錯誤_失敗的那一筆不動(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:失敗的 HF_Q4(執行環境上沒有它)與停在閘門前、下載中的 qwen2.5:7b
    downloadable(fakes)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES})
    fakes.remote_ollama.pull_model.raises("OLLAMA_PULL_FAILED")
    await open_ready(ui_client)
    await ui_client.post("/api/downloads", json={"models": [HF_Q4]})
    await wait_queue(ui_client, lambda q: states(q) == [(HF_Q4, "failed")])
    hold = hold_pulls(fakes)
    await ui_client.post("/api/downloads", json={"models": [QWEN_7B]})
    both = await wait_queue(ui_client, lambda q: states(q) == [(HF_Q4, "failed"), (QWEN_7B, "downloading")])
    ids = {job["model"]: job["id"] for job in both["jobs"]}
    outcomes: dict[str, httpx.Response] = {}

    # Act
    outcomes["A"] = await ui_client.post("/api/downloads/9999/retry")
    outcomes["B"] = await ui_client.post(f"/api/downloads/{ids[QWEN_7B]}/retry")
    for case, code in (("C", "OLLAMA_UNREACHABLE"), ("D", "OLLAMA_BAD_RESPONSE"), ("E", "OLLAMA_TIMEOUT")):
        fakes.remote_ollama.list_local_models.raises(code)
        outcomes[case] = await ui_client.post(f"/api/downloads/{ids[HF_Q4]}/retry")
    reconnect = fakes.tunnel.open_tunnel.gate()
    fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE")
    await wait_for_state(ui_client, "reconnecting")
    outcomes["F"] = await ui_client.post(f"/api/downloads/{ids[HF_Q4]}/retry")
    after = await queue(ui_client)
    reconnect.release()
    hold.release()

    # Assert
    assert {case: (r.status_code, error_code(r)) for case, r in outcomes.items()} == {
        "A": (404, "DOWNLOAD_NOT_FOUND"),
        "B": (409, "DOWNLOAD_NOT_RETRYABLE"),
        "C": (502, "OLLAMA_UNREACHABLE"),
        "D": (502, "OLLAMA_BAD_RESPONSE"),
        "E": (504, "OLLAMA_TIMEOUT"),
        "F": (503, "NO_READY_SESSION"),
    }
    assert (HF_Q4, "failed") in states(after)


# ---- 004 US4-API-26


async def test_下載完成的_hf_co_模型出現在模型目錄(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    set_hf(fakes, {HF_Q4: HF_Q4_BYTES})
    fakes.remote_ollama.pull_model.returns([{"status": "pulling manifest"}, {"status": "success"}])
    await open_ready(ui_client)

    # Act
    await ui_client.post("/api/downloads", json={"models": [HF_Q4]})
    done = await wait_queue(ui_client, lambda q: states(q) == [(HF_Q4, "completed")])
    set_tags(fakes, tag(HF_Q4, 105_455_694))
    names = await catalog_names(ui_client)

    # Assert
    assert [(job["model"], job["state"], job["source"]) for job in done["jobs"]] == [(HF_Q4, "completed", "huggingface")]
    assert HF_Q4 in names
