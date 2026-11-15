"""下載佇列(FR-017、FR-021、FR-010;contracts/ui.openapi.yaml § DownloadQueue)。一次一個,依佇列順序(research.md R5)。"""

import asyncio
from collections.abc import Iterable
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError, hf_error, library_error, ollama_error
from cgb.domain.estimate import estimate
from cgb.domain.model_name import HF_PREFIX, match_key, source_of, with_version
from cgb.domain.session_state import iso
from cgb.repos.downloads import DownloadsRepo, QueueConflict
from cgb.services.event_bus import EventBus
from cgb.services.session_lifecycle import SessionLifecycle

# 下載中的 `download.updated` 最多每秒推一次(asyncapi § sendDownloadUpdated)
PROGRESS_INTERVAL = 1.0

# 下載失敗給使用者看的說明(DownloadJob.message);不把遠端的英文原文交給 UI(NFR-010)
FAILED_MESSAGES = {
    "OLLAMA_NOT_FOUND": "找不到這個模型或版本,請確認名稱。",
}
FAILED_FALLBACK_MESSAGE = "下載失敗,請稍後重新排隊再試。"

# 工作階段變成這些狀態時清空下載佇列(`info.x-queue-clearing` (1));重連中(還可能接回同一台)不清
QUEUE_CLEARING_STATES = frozenset({"ending", "ended", "open_failed", "lost"})


def _key_set(names: Iterable[str]) -> set[str]:
    """名稱集合轉成比對鍵集合(不分大小寫、補過版本)。"""
    return {match_key(name) for name in names}


class DownloadsService:
    def __init__(self, state: Any, repo: DownloadsRepo, lifecycle: SessionLifecycle, events: EventBus) -> None:
        self._state = state
        self._repo = repo
        self._lifecycle = lifecycle
        self._events = events
        # 下載中那一筆的進度(DownloadProgress);只活在這次執行之中,不存表
        self._progress: dict[int, dict[str, int]] = {}
        self._worker: asyncio.Task[None] | None = None
        lifecycle.ready_listeners.append(self.resume)

    def job_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "model": row["model"],
            "source": source_of(row["model"]),
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

    def _session_name(self) -> str:
        """目前工作階段的名稱;佇列的項目都記在它底下(`info.x-queue-clearing`)。"""
        return str(self._lifecycle.current()["name"])

    def pending(self) -> list[dict[str, Any]]:
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
        """每個模型(已由 `_checked` 補過版本)以 S2 `get_manifest` 取精確大小(Q11);任何一個不符就整批不加入。"""
        sized = []
        for model in models:
            try:
                sized.append((model, await self.manifest_size(model)))
            except AdapterError as error:
                # Hugging Face 與官方模型庫的失敗各依自己的代碼表歸類(`info.x-hf-error-status`)
                raise (hf_error if source_of(model) == "huggingface" else library_error)(error.code, model=model) from None
        return sized

    async def manifest_size(self, model: str) -> int:
        """補過版本的名稱取精確大小(位元組),依前綴分流:`hf.co/` 向 Hugging Face,其他向官方模型庫;失敗時丟 `AdapterError`。"""
        name, tag = model.split(":", 1)
        if source_of(model) == "huggingface":
            author, repo = name.removeprefix(HF_PREFIX).split("/", 1)
            return int((await self._state.huggingface.get_manifest(author=author, model=repo, tag=tag))["sizeBytes"])
        return int((await self._state.model_library.get_manifest(name=name, tag=tag))["sizeBytes"])

    async def local_keys(self) -> set[str] | None:
        """執行環境上已下載的模型(`match_key`,不分大小寫);沒有就緒的工作階段或讀不到時是 None。"""
        base_url = self._lifecycle.ready_base_url()
        if base_url is None:
            return None
        try:
            models = (await self._state.remote_ollama.list_local_models(base_url=base_url))["models"]
        except AdapterError:
            return None
        return _key_set(m["name"] for m in models)

    async def _runtime_keys(self, base_url: str) -> set[str]:
        """執行環境上已下載的模型的比對鍵;讀不到時依代碼轉成 502 或 504(和 `local_keys` 不同,它不吞錯誤)。"""
        try:
            models = (await self._state.remote_ollama.list_local_models(base_url=base_url))["models"]
        except AdapterError as error:
            raise ollama_error(error.code) from None
        return _key_set(m["name"] for m in models)

    async def _checked(self, models: list[str]) -> list[str]:
        """試算與加入共用的重複檢查(contracts/ui.openapi.yaml § info.x-download-check-order):回傳補過版本的名稱。"""
        base_url = self._lifecycle.require_ready_base_url()
        # 同一批不分大小寫相同的合併成一個,留第一次出現的寫法與順序(`info.x-model-name-rule` (2)(4))
        merged: dict[str, str] = {}
        for model in models:
            merged.setdefault(match_key(model), with_version(model))
        versioned = list(merged.values())
        local = await self._runtime_keys(base_url)
        pending = _key_set(row["model"] for row in self.pending())
        for model in versioned:
            if match_key(model) in local:
                raise ApiError(409, "MODEL_ALREADY_DOWNLOADED", model=model)
            if match_key(model) in pending:
                raise ApiError(409, "DOWNLOAD_ALREADY_QUEUED", model=model)
        return versioned

    async def estimate(self, models: list[str]) -> dict[str, Any]:
        """試算(estimateDownloads):不改變佇列。"""
        return await self._estimate(await self._sized(await self._checked(models)))

    async def _estimate(self, sized: list[tuple[str, int]]) -> dict[str, Any]:
        try:
            resources = await self._state.colab.probe_resources(name=self._lifecycle.current()["name"])
        except AdapterError as error:
            # 讀不到剩餘空間就無法檢查 FR-022,不當成夠用
            raise ApiError(503, "DISK_SPACE_UNKNOWN", reason_code=error.code) from None
        pending = sum(row["size_bytes"] for row in self.pending())
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
        # 請求開始時固定工作階段身分:取大小期間若結束或換成另一個,寫入前要能發現
        session_name = self._session_name()
        models = await self._checked(models)
        sized = await self._sized(models)
        # 檢查條件與試算相同,只差空間不足時回錯誤(使用者故事 3 驗收情境 12)
        if not (await self._estimate(sized))["fits"]:
            raise ApiError(409, "DISK_SPACE_INSUFFICIENT")
        # 最後一次 `await` 之後、寫入之前沒有 `await`:仍須是原本那個就緒的工作階段,否則不寫入也不下載
        if self._lifecycle.ready_base_url() != base_url or self._session_name() != session_name:
            raise ApiError(503, "NO_READY_SESSION")
        try:
            ids = self._repo.enqueue_many(
                sized, origin="user",
                preload_on_complete=False,
                added_at=iso(self._state.clock.now()),
                session_name=session_name,
            )
        except QueueConflict as conflict:
            # 另一個請求在這個請求取 manifest 時先把同一個模型加進佇列:整批已撤回(research.md R2)
            raise ApiError(409, "DOWNLOAD_ALREADY_QUEUED", model=conflict.model) from None
        for job_id in ids:
            self._publish(job_id)
        self.kick(base_url)
        return {"jobs": [self.job_payload(row) for row in self._repo.all() if row["id"] in ids]}

    def enqueue_auto(self, sized: list[tuple[str, int]], session_name: str, base_url: str) -> list[str]:
        """自動下載排入(`origin` 為 `auto`),每一筆推 `download.updated`,接著開始下載。

        判定期間使用者可能已手動加入同一個模型:最後寫入時再濾一次佇列裡的(不分大小寫),其餘照常排入。
        回傳實際排入的模型名稱。"""
        queued = _key_set(row["model"] for row in self.pending())
        sized = [(model, size) for model, size in sized if match_key(model) not in queued]
        if not sized:
            return []
        ids = self._repo.enqueue_many(
            sized, origin="auto", preload_on_complete=False, added_at=iso(self._state.clock.now()), session_name=session_name
        )
        for job_id in ids:
            self._publish(job_id)
        self.kick(base_url)
        return [model for model, _ in sized]

    def remove(self, job_id: int) -> None:
        """移除一筆(removeDownload):排隊中的取消,正在下載的不能取消。"""
        row = self._repo.get(job_id)
        if row is not None and row["state"] == "downloading":
            raise ApiError(409, "DOWNLOAD_IN_PROGRESS")
        self._repo.delete(job_id)
        self._events.download_removed(job_id)

    async def retry(self, job_id: int) -> dict[str, Any]:
        """重新排隊(retryDownload):排到佇列最後,不插回原位;佇列已清空而找不到這一筆時回 404;不是失敗的回 409;
        執行環境上已經有這個模型(不分大小寫,FR-018)時回 409,那一筆不動。"""
        row = self._repo.get(job_id)
        if row is None:
            raise ApiError(404, "DOWNLOAD_NOT_FOUND")
        if row["state"] != "failed":
            raise ApiError(409, "DOWNLOAD_NOT_RETRYABLE")
        base_url = self._lifecycle.require_ready_base_url()
        if match_key(row["model"]) in await self._runtime_keys(base_url):
            raise ApiError(409, "MODEL_ALREADY_DOWNLOADED", model=row["model"])
        self._repo.requeue(job_id)
        self._publish(job_id)
        return self.job_payload(self._repo.get(job_id))

    def clear_completed(self) -> dict[str, Any]:
        """清除已完成(clearCompletedDownloads,Q49);排隊中、下載中、失敗的不動。"""
        removed = self._repo.delete_completed()
        for job_id in removed:
            self._events.download_removed(job_id)
        return {"removedIds": removed}

    def enqueue_restore(self, model: str, size_bytes: int, session_name: str) -> None:
        """變更類型時為了重新載入原本已載入的模型而加入新的工作階段(FR-010、Q36)。"""
        job_id = self._repo.enqueue(
            model=model,
            size_bytes=size_bytes,
            origin="restore",
            preload_on_complete=True,
            added_at=iso(self._state.clock.now()),
            session_name=session_name,
        )
        # 清除時已先送空的快照,這一筆接著以 `download.updated` 推出(Q47、D61)
        self._publish(job_id)

    def clear_unowned(self) -> None:
        """後端啟動時呼叫:升級前留下、沒有所屬工作階段的項目一併移除(`info.x-queue-clearing` (3))。"""
        self._repo.delete_unowned()

    def requeue_interrupted(self) -> None:
        """後端重新啟動時呼叫:上一個行程中斷的下載回到排隊中,工作階段接回(就緒)後自動重新下載。"""
        self._repo.requeue_interrupted()

    def clear_if_session_over(self) -> None:
        """`SessionsRepo.listeners` 的清除(`info.x-queue-clearing` (1)):工作階段變成結束中、已結束、開啟失敗或失聯時,
        佇列的每一筆都移除(下載中的那筆不先標成失敗),每移除一筆推 `download.removed`,全部移除後推一則 `downloads.snapshot`。"""
        if self._lifecycle.current()["state"] not in QUEUE_CLEARING_STATES:
            return
        # 下載中那一筆的 worker 一起取消:閘門放行後不會再寫成 `completed`,也不會接著下載後面排入的項目
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        removed = self._repo.delete_all()
        for job_id in removed:
            self._progress.pop(job_id, None)
            self._events.download_removed(job_id)
        if removed:
            self._events.downloads_snapshot(self.queue(paused=True))

    def resume(self, base_url: str) -> None:
        """工作階段就緒:佇列有排隊中的項目就自動繼續,開始前重新讀剩餘空間(邊界情況、FR-021)。"""
        if self._repo.next_queued(self._session_name()) is not None:
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
        session_name = self._session_name()
        while (job := self._repo.next_queued(session_name)) is not None:
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
