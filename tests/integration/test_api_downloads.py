"""E2 後端 UI API:下載佇列(testplan.md § 4.1,`/api/downloads` › 加入、移除、試算、重新排隊)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身(testplan.md § 接縫的取捨)。
「假伺服器的 pull」是 `FakeRemoteOllama.pull_model` 產出的進度行;每一行前面放一個閘門,
由測試端的 `Pacer` 照節奏放行,模擬「每 0.1 秒送一行」。
"""

import asyncio
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError
from cgb.db.connection import connect
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
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
    wait_for_state,
)

QWEN_MID = "qwen2.5:1.5b"
QWEN_MID_BYTES = 986_061_892
MANIFEST_SIZES = {QWEN_SMALL: QWEN_SMALL_BYTES, QWEN_7B: QWEN_7B_BYTES, QWEN_MID: QWEN_MID_BYTES}


def set_library(fakes: Any, sizes: dict[str, int] = MANIFEST_SIZES) -> None:
    """`get_manifest` 依 `<名稱>:<版本>` 回精確大小,其他回 `LIBRARY_NOT_FOUND`。"""

    def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        full = f"{kwargs['name']}:{kwargs['tag']}"
        if full not in sizes:
            raise AdapterError("LIBRARY_NOT_FOUND", "manifest unknown")
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": sizes[full]}

    fakes.model_library.get_manifest.side_effect(manifest)


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


# ---------------------------------------------------------------- US3-API-18


async def test_結束工作階段時下載中的那筆失敗_排隊中的保留(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_MID, QWEN_MID_BYTES))
    hold = await enqueue_waiting(ui_client, fakes, QWEN_SMALL, QWEN_7B)

    # Act
    await ui_client.delete("/api/session")
    ended = await wait_queue(ui_client, lambda q: states(q)[:1] == [(QWEN_SMALL, "failed")])
    await wait_for_state(ui_client, "ended")
    before_next = await queue(ui_client)
    hold.release()
    set_tags(fakes)
    await open_ready(ui_client)
    catalog = (await ui_client.get("/api/models")).json()

    # Assert
    first = ended.get("jobs", [{}])[0]
    assert (first.get("state"), first.get("reasonCode")) == ("failed", "SESSION_ENDED")
    assert states(before_next) == [(QWEN_SMALL, "failed"), (QWEN_7B, "queued")]
    assert catalog.get("items") == []


# ---------------------------------------------------------------- US3-API-19


async def test_新的工作階段就緒後佇列自動繼續_開始前重新檢查空間(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:上一個工作階段結束時 qwen2.5:7b 中斷,qwen2.5:0.5b 留在佇列
    downloadable(fakes)
    await open_ready(ui_client)
    hold = await enqueue_waiting(ui_client, fakes, QWEN_7B, QWEN_SMALL)
    await ui_client.delete("/api/session")
    await wait_for_state(ui_client, "ended")
    hold.release()
    paused = await queue(ui_client)
    calls: list[tuple[str, float]] = []

    def probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(("probe_resources", time.monotonic()))
        return resources()

    def pull(*args: Any, **kwargs: Any) -> list[Any]:
        calls.append((f"pull {kwargs['model']}", time.monotonic()))
        return [{"status": "success"}]

    fakes.colab.probe_resources.side_effect(probe)
    fakes.remote_ollama.pull_model.side_effect(pull)

    # Act
    ready_at = (await open_ready(ui_client), time.monotonic())[1]
    await wait_queue(ui_client, lambda q: (QWEN_SMALL, "completed") in states(q), timeout=2.0)

    # Assert
    assert paused.get("paused") is True and (QWEN_SMALL, "queued") in states(paused)
    pulls = [at for name, at in calls if name == f"pull {QWEN_SMALL}"]
    assert pulls and pulls[0] - ready_at <= 1.0, calls
    assert [name for name, _ in calls][:2] == ["probe_resources", f"pull {QWEN_SMALL}"]


def insert_jobs(db_path: Any, *jobs: tuple[str, str, str | None]) -> None:
    """直接寫入 `download_jobs`(模型, 狀態, reason_code),依序排在佇列裡。"""
    conn = connect(db_path)
    for position, (model, state, reason) in enumerate(jobs, start=1):
        pending = model if state in ("queued", "downloading") else None
        conn.execute(
            "INSERT INTO download_jobs (model, pending_model, queue_position, size_bytes, state, reason_code, added_at)"
            " VALUES (?, ?, ?, ?, ?, ?, '2026-11-09T09:00:00Z')",
            (model, pending, position, MANIFEST_SIZES[model], state, reason),
        )
    conn.close()


# ---------------------------------------------------------------- US3-API-20


async def test_重新排隊排到最後_清除已完成只清完成的(ui_client: httpx.AsyncClient, fakes: Any, db_path: Any) -> None:
    # Arrange:依序有 completed 的 A、failed 的 B(SESSION_ENDED)、queued 的 C;沒有工作階段
    downloadable(fakes)
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
