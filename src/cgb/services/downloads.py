"""下載佇列(FR-017、FR-021、FR-010;contracts/ui.openapi.yaml § DownloadQueue)。一次一個,依佇列順序(research.md R5)。"""

import asyncio
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError
from cgb.domain.estimate import estimate
from cgb.domain.session_state import iso
from cgb.repos.downloads import DownloadsRepo
from cgb.services.event_bus import EventBus
from cgb.services.session_lifecycle import SessionLifecycle

# 下載中的 `download.updated` 最多每秒推一次(asyncapi § sendDownloadUpdated)
PROGRESS_INTERVAL = 1.0

# 模型庫(S2)的失敗 → HTTP 狀態(contracts § enqueueDownloads、estimateDownloads)
_LIBRARY_STATUS = {"LIBRARY_NOT_FOUND": 404, "LIBRARY_CLOUD_ONLY": 422}

# 下載失敗給使用者看的說明(DownloadJob.message);不把遠端的英文原文交給 UI(NFR-010)
FAILED_MESSAGES = {
    "OLLAMA_NOT_FOUND": "找不到這個模型或版本,請確認名稱。",
    "SESSION_ENDED": "工作階段結束,下載中斷;可以在新的工作階段重新排隊。",
}
FAILED_FALLBACK_MESSAGE = "下載失敗,請稍後重新排隊再試。"


class DownloadsService:
    def __init__(self, state: Any, repo: DownloadsRepo, lifecycle: SessionLifecycle, events: EventBus) -> None:
        self._state = state
        self._repo = repo
        self._lifecycle = lifecycle
        self._events = events
        # 下載中那一筆的進度(DownloadProgress);只活在這次執行之中,不存表
        self._progress: dict[int, dict[str, int]] = {}
        self._worker: asyncio.Task[None] | None = None
        lifecycle.end_listeners.append(self.interrupt)
        lifecycle.ready_listeners.append(self.resume)

    def job_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "model": row["model"],
            "sizeBytes": row["size_bytes"],
            "state": row["state"],
            "progress": self._progress.get(row["id"]) if row["state"] == "downloading" else None,
            "reasonCode": row["reason_code"],
            "message": row["message"],
            "origin": row["origin"],
            "preloadOnComplete": bool(row["preload_on_complete"]),
            "addedAt": row["added_at"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
        }

    def queue(self, *, paused: bool) -> dict[str, Any]:
        return {"paused": paused, "jobs": [self.job_payload(row) for row in self._repo.all()]}

    def _pending(self) -> list[dict[str, Any]]:
        """排隊中與下載中(還沒下載完)的項目。"""
        return [row for row in self._repo.all() if row["state"] in ("queued", "downloading")]

    def _fail(self, job_id: int, reason_code: str) -> None:
        self._progress.pop(job_id, None)
        self._repo.update(
            job_id,
            state="failed",
            pending_model=None,
            reason_code=reason_code,
            message=FAILED_MESSAGES.get(reason_code, FAILED_FALLBACK_MESSAGE),
            finished_at=iso(self._state.clock.now()),
        )
        self._publish(job_id)

    def _publish(self, job_id: int) -> None:
        row = self._repo.get(job_id)
        if row is not None:
            self._events.download_updated(self.job_payload(row))

    async def _sized(self, models: list[str]) -> list[tuple[str, int]]:
        """每個模型以 S2 `get_manifest` 取精確大小(Q11);任何一個不符就整批不加入。"""
        library = self._state.model_library
        sized = []
        for model in models:
            name, tag = model.split(":", 1)
            try:
                manifest = await library.get_manifest(name=name, tag=tag)
            except AdapterError as error:
                raise ApiError(_LIBRARY_STATUS[error.code], error.code, model=model) from None
            sized.append((model, manifest["sizeBytes"]))
        return sized

    async def estimate(self, models: list[str]) -> dict[str, Any]:
        """試算(estimateDownloads):不改變佇列。"""
        return await self._estimate(await self._sized(models))

    async def _estimate(self, sized: list[tuple[str, int]]) -> dict[str, Any]:
        try:
            resources = await self._state.colab.probe_resources(name=self._lifecycle.current()["name"])
        except AdapterError as error:
            # 讀不到剩餘空間就無法檢查 FR-022,不當成夠用
            raise ApiError(503, "DISK_SPACE_UNKNOWN", reason_code=error.code) from None
        pending = sum(row["size_bytes"] for row in self._pending())
        return estimate(
            sized,
            pending_queue_bytes=pending,
            free_disk_bytes=resources["diskFreeBytes"],
            disk_checked_at=resources["checkedAt"],
        )

    async def enqueue(self, models: list[str]) -> dict[str, Any]:
        """加入佇列(enqueueDownloads):以 manifest 的精確大小記下每一筆,再在背景依序下載。"""
        # 沒有就緒的工作階段時不加入,免得使用者以為在下載
        base_url = self._lifecycle.require_ready_base_url()
        local = {m["name"] for m in (await self._state.remote_ollama.list_local_models(base_url=base_url))["models"]}
        pending = {row["model"] for row in self._pending()}
        for model in models:
            if model in local:
                raise ApiError(409, "MODEL_ALREADY_DOWNLOADED", model=model)
            if model in pending:
                raise ApiError(409, "DOWNLOAD_ALREADY_QUEUED", model=model)
        sized = await self._sized(models)
        # 檢查條件與試算相同,只差空間不足時回錯誤(使用者故事 3 驗收情境 12)
        if not (await self._estimate(sized))["fits"]:
            raise ApiError(409, "DISK_SPACE_INSUFFICIENT")
        ids = [
            self._repo.enqueue(
                model=model, size_bytes=size, origin="user", preload_on_complete=False, added_at=iso(self._state.clock.now())
            )
            for model, size in sized
        ]
        for job_id in ids:
            self._publish(job_id)
        self.kick(base_url)
        return {"jobs": [self.job_payload(row) for row in self._repo.all() if row["id"] in ids]}

    def remove(self, job_id: int) -> None:
        """移除一筆(removeDownload):排隊中的取消,正在下載的不能取消。"""
        row = self._repo.get(job_id)
        if row is not None and row["state"] == "downloading":
            raise ApiError(409, "DOWNLOAD_IN_PROGRESS")
        self._repo.delete(job_id)
        self._events.download_removed(job_id)

    def retry(self, job_id: int) -> dict[str, Any]:
        """重新排隊(retryDownload):排到佇列最後,不插回原位。"""
        self._repo.requeue(job_id)
        self._publish(job_id)
        return self.job_payload(self._repo.get(job_id))

    def clear_completed(self) -> dict[str, Any]:
        """清除已完成(clearCompletedDownloads,Q49);排隊中、下載中、失敗的不動。"""
        removed = self._repo.delete_completed()
        for job_id in removed:
            self._events.download_removed(job_id)
        return {"removedIds": removed}

    def enqueue_restore(self, model: str, size_bytes: int) -> None:
        """變更類型時為了重新載入原本已載入的模型而加入(FR-010、Q36)。"""
        self._repo.enqueue(
            model=model,
            size_bytes=size_bytes,
            origin="restore",
            preload_on_complete=True,
            added_at=iso(self._state.clock.now()),
        )

    def requeue_interrupted(self) -> None:
        """後端重新啟動時呼叫:上一個行程中斷的下載回到排隊中,工作階段接回(就緒)後自動重新下載。"""
        self._repo.requeue_interrupted()

    def interrupt(self) -> None:
        """工作階段結束:停下背景下載,下載中的那筆標成失敗(SESSION_ENDED),排隊中的保留(邊界情況、FR-018)。"""
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        for row in self._repo.all():
            if row["state"] == "downloading":
                self._fail(row["id"], "SESSION_ENDED")

    def resume(self, base_url: str) -> None:
        """工作階段就緒:佇列有排隊中的項目就自動繼續,開始前重新讀剩餘空間(邊界情況、FR-021)。"""
        if self._repo.next_queued() is not None:
            self._start(self._resume(base_url))

    async def _resume(self, base_url: str) -> None:
        await self._state.colab.probe_resources(name=self._lifecycle.current()["name"])
        await self._run_queue(base_url)

    def kick(self, base_url: str) -> None:
        """在背景開始依序下載。"""
        self._start(self._run_queue(base_url))

    def _start(self, coro: Any) -> None:
        """一次只有一個背景下載;已經在跑就不另開(research.md R5)。"""
        if self._worker is None or self._worker.done():
            self._worker = self._lifecycle.spawn(coro)
        else:
            coro.close()

    async def _run_queue(self, base_url: str) -> None:
        """依序下載排隊中的項目;`preloadOnComplete` 的下載完成後預先載入(keep_alive: -1,Q4)。"""
        remote, clock = self._state.remote_ollama, self._state.clock
        while (job := self._repo.next_queued()) is not None:
            job_id = job["id"]
            self._repo.update(job_id, state="downloading", started_at=iso(clock.now()))
            self._publish(job_id)
            last_published = clock.monotonic()
            layers: dict[str, tuple[int, int]] = {}
            try:
                async for line in await remote.pull_model(base_url=base_url, model=job["model"]):
                    if "total" in line and "digest" in line:
                        layers[line["digest"]] = (line.get("completed", 0), line["total"])
                        self._progress[job_id] = {
                            "completedBytes": sum(done for done, _ in layers.values()),
                            "totalBytes": sum(total for _, total in layers.values()),
                        }
                        if clock.monotonic() - last_published >= PROGRESS_INTERVAL:
                            self._publish(job_id)
                            last_published = clock.monotonic()
            except AdapterError as error:
                # pull 回 200 之後串流裡出現的錯誤也是失敗(Q3);執行環境上已有的模型不變
                self._fail(job_id, error.code)
                continue
            self._progress.pop(job_id, None)
            self._repo.update(job_id, state="completed", pending_model=None, finished_at=iso(clock.now()))
            self._publish(job_id)
            if job["preload_on_complete"]:
                await remote.preload(base_url=base_url, model=job["model"])
