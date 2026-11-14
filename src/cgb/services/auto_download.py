"""自動下載(contracts/ui.openapi.yaml § info.x-auto-download、info.x-queue-clearing (5);research.md R6)。

工作階段第一次就緒時,把精選清單裡設了 `autoDownload` 的項目排入下載佇列,並記下這一次的結果;
結果屬於一個工作階段,工作階段結束時照佇列的清除一併移除。
"""

import asyncio
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.model_name import match_key, with_version
from cgb.domain.session_state import iso
from cgb.repos.auto_download import AutoDownloadRepo
from cgb.repos.curated import CuratedRepo
from cgb.services.downloads import QUEUE_CLEARING_STATES, DownloadsService
from cgb.services.event_bus import EventBus
from cgb.services.session_lifecycle import SessionLifecycle

# AutoDownloadSkipped.message:給使用者看的繁體中文原因
SKIPPED_MESSAGES = {
    "SIZE_UNAVAILABLE": "取不到模型大小,沒有排入。",
    "DISK_SPACE_INSUFFICIENT": "執行環境的剩餘空間不足,沒有排入。",
    "DISK_SPACE_UNKNOWN": "讀不到執行環境的剩餘空間,沒有排入。",
    "MAY_NOT_FIT": "這台可能無法載入這個模型(大小超過顯示記憶體),沒有排入。",
}


class AutoDownload:
    def __init__(
        self,
        state: Any,
        repo: AutoDownloadRepo,
        curated: CuratedRepo,
        downloads: DownloadsService,
        lifecycle: SessionLifecycle,
        events: EventBus,
    ) -> None:
        self._state = state
        self._repo = repo
        self._curated = curated
        self._downloads = downloads
        self._lifecycle = lifecycle
        self._events = events
        self._task: asyncio.Task[None] | None = None
        lifecycle.ready_listeners.append(self.on_ready)

    def result(self) -> dict[str, Any] | None:
        """目前工作階段的自動下載結果(`getAutoDownloadResult`);沒有時是 None。"""
        name = self._lifecycle.current().get("name")
        return self._repo.get(name) if name is not None else None

    def on_ready(self, base_url: str) -> None:
        """工作階段就緒:這個工作階段第一次就緒才判定;精選清單沒有設自動下載的項目時只記下做過一次,不推送。"""
        name = self._lifecycle.current()["name"]
        targets = [row["name"] for row in self._curated.all() if row["auto_download"]]
        if not self._repo.start(name, len(targets)) or not targets:
            return
        self._publish()
        self._task = self._lifecycle.spawn(self._decide(name, targets, base_url))

    async def _decide(self, name: str, targets: list[str], base_url: str) -> None:
        """依精選清單的順序判定每一項:已在執行環境上或佇列中的不排,取不到大小的跳過,其餘一次排入佇列。"""
        try:
            local = {match_key(m["name"]) for m in (await self._state.remote_ollama.list_local_models(base_url=base_url))["models"]}
        except AdapterError:
            # 讀不到就當成執行環境上沒有任何模型(新的執行環境本來就是空的)
            local = set()
        queued = {match_key(job["model"]) for job in self._downloads.pending()}
        wanted = [
            (position, with_version(target))
            for position, target in enumerate(targets)
            if match_key(with_version(target)) not in local | queued
        ]
        # 取大小同時最多 4 個;結果仍依清單順序處理
        slots = asyncio.Semaphore(4)

        async def size_of(model: str) -> int | AdapterError:
            async with slots:
                try:
                    return await self._downloads.manifest_size(model)
                except AdapterError as error:
                    return error

        sizes = await asyncio.gather(*(size_of(model) for _, model in wanted))
        candidates: list[tuple[int, str, int]] = []
        for (position, model), size in zip(wanted, sizes, strict=True):
            if isinstance(size, AdapterError):
                self._repo.add_item(
                    name,
                    position,
                    model,
                    reason="SIZE_UNAVAILABLE",
                    reason_code=size.code,
                    message=SKIPPED_MESSAGES["SIZE_UNAVAILABLE"],
                )
                continue
            candidates.append((position, model, size))
        # 剩餘磁碟空間讀一次,依清單順序累加:已決定排入的大小 + 佇列裡還沒下載完的大小 + 這一項 > 剩餘 → 跳過,後面較小的照常判斷
        try:
            resources = await self._state.colab.probe_resources(name=name)
        except AdapterError as error:
            # 讀不到就無法確認放不放得下,其餘還沒判定的項目都跳過(001 不把讀不到當成夠用)
            for position, model, _ in candidates:
                self._repo.add_item(
                    name,
                    position,
                    model,
                    reason="DISK_SPACE_UNKNOWN",
                    reason_code=error.code,
                    message=SKIPPED_MESSAGES["DISK_SPACE_UNKNOWN"],
                )
            candidates = []
            resources = {"diskFreeBytes": 0, "vramTotalBytes": None}
        used = sum(row["size_bytes"] for row in self._downloads.pending())
        sized: list[tuple[str, int]] = []
        vram = resources["vramTotalBytes"]
        for position, model, size in candidates:
            if vram is not None and size > vram:
                self._repo.add_item(
                    name, position, model, reason="MAY_NOT_FIT", message=SKIPPED_MESSAGES["MAY_NOT_FIT"]
                )
                continue
            if used + size > resources["diskFreeBytes"]:
                self._repo.add_item(
                    name,
                    position,
                    model,
                    reason="DISK_SPACE_INSUFFICIENT",
                    message=SKIPPED_MESSAGES["DISK_SPACE_INSUFFICIENT"],
                )
                continue
            used += size
            self._repo.add_item(name, position, model)
            sized.append((model, size))
        # 排入、記下完成與推送之間沒有 `await`:工作階段結束的清除不會夾在中間
        self._downloads.enqueue_auto(sized, name, base_url)
        self._repo.finish(name, iso(self._state.clock.now()))
        self._publish()

    def clear_if_session_over(self) -> None:
        """`SessionsRepo.listeners` 的清除(`info.x-queue-clearing` (5)):工作階段變成結束類的狀態時,
        結果連同判定到一半的工作一起移除;有對外的結果才推 `autoDownload.updated`(`result` 為 null)。"""
        latest = self._lifecycle.current()
        if latest["state"] not in QUEUE_CLEARING_STATES:
            return
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._repo.delete(latest["name"]):
            self._events.auto_download_updated(None)

    def _publish(self) -> None:
        self._events.auto_download_updated(self.result())
