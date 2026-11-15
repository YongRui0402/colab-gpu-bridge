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

# AutoDownloadSkipped.message:給使用者看的繁體中文原因,「原因名稱:說明」(prototype/mock.js 的 SKIP_MESSAGE、SIZE_MESSAGE;
# 原因名稱是 spec.md FR-012 的四種,plan.md Q81)
SKIPPED_MESSAGES = {
    "DISK_SPACE_INSUFFICIENT": "空間不足:剩餘磁碟放不下這一個",
    "MAY_NOT_FIT": "這台可能無法載入:大小超過顯示記憶體",
    "DISK_SPACE_UNKNOWN": "讀不到剩餘空間:讀不到執行環境的剩餘磁碟空間,還沒判定的項目都先跳過",
}
# 取不到大小依取大小失敗的代碼說明;沒列的代碼用通用的一句
SIZE_UNAVAILABLE_MESSAGES = {
    "HF_AUTH_REQUIRED": "取不到大小:Hugging Face 上這個模型需要登入、同意條款、私有或不存在",
    "HF_QUANT_UNAVAILABLE": "取不到大小:這個量化版本無法下載(不存在、分割檔或不是 GGUF)",
    "HF_TIMEOUT": "取不到大小:Hugging Face 在 10 秒內沒有回應",
    "LIBRARY_NOT_FOUND": "取不到大小:官方模型庫沒有這個模型或版本",
}
SIZE_UNAVAILABLE_FALLBACK = "取不到大小:模型來源沒有回應或不能下載"


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

    def dismiss(self) -> dict[str, Any] | None:
        """關閉提示(`dismissAutoDownloadResult`):記成已關閉並推送;回傳關閉後的結果,沒有結果時是 None。"""
        if self.result() is None:
            return None
        self._repo.dismiss(self._lifecycle.current()["name"])
        self._publish()
        return self.result()

    def on_ready(self, base_url: str) -> None:
        """工作階段就緒:這個工作階段第一次就緒才判定;精選清單沒有設自動下載的項目時只記下做過一次,不推送。"""
        name = self._lifecycle.current()["name"]
        targets = [with_version(row["name"]) for row in self._curated.all() if row["auto_download"]]
        if not self._repo.start(name, len(targets)) or not targets:
            return
        self._publish()
        self._task = self._lifecycle.spawn(self._decide(name, targets, base_url))

    async def _decide(self, name: str, targets: list[str], base_url: str) -> None:
        """依精選清單的順序判定每一項:已在執行環境上或佇列中的不排,取不到大小的跳過,其餘一次排入佇列。"""
        wanted = await self._not_there_yet(targets, base_url)
        candidates = await self._with_sizes(name, wanted)
        fitting = await self._fit_in_resources(name, candidates)
        # 排入、記下完成與推送之間沒有 `await`:工作階段結束的清除不會夾在中間;
        # 判定期間被手動加入的同名模型由 `enqueue_auto` 略過,結果只列實際排入的
        enqueued = set(self._downloads.enqueue_auto([(model, size) for _, model, size in fitting], name, base_url))
        for position, model, _ in fitting:
            if model in enqueued:
                self._repo.add_item(name, position, model)
        self._repo.finish(name, iso(self._state.clock.now()))
        self._publish()

    async def _not_there_yet(self, targets: list[str], base_url: str) -> list[tuple[int, str]]:
        """(清單位置, 名稱):濾掉執行環境上已有的與佇列裡已有的(不分大小寫);這些不取大小,也不列為跳過。"""
        try:
            local = {match_key(m["name"]) for m in (await self._state.remote_ollama.list_local_models(base_url=base_url))["models"]}
        except AdapterError:
            # 讀不到就當成執行環境上沒有任何模型(新的執行環境本來就是空的)
            local = set()
        queued = {match_key(job["model"]) for job in self._downloads.pending()}
        return [(position, model) for position, model in enumerate(targets) if match_key(model) not in local | queued]

    async def _with_sizes(self, name: str, wanted: list[tuple[int, str]]) -> list[tuple[int, str, int]]:
        """取大小同時最多 4 個,結果仍依清單順序處理;取不到的記成 `SIZE_UNAVAILABLE` 跳過,其餘回傳 (位置, 名稱, 大小)。"""
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
                    message=SIZE_UNAVAILABLE_MESSAGES.get(size.code, SIZE_UNAVAILABLE_FALLBACK),
                )
                continue
            candidates.append((position, model, size))
        return candidates

    async def _fit_in_resources(self, name: str, candidates: list[tuple[int, str, int]]) -> list[tuple[int, str, int]]:
        """剩餘磁碟空間讀一次,依清單順序累加:已決定排入的大小 + 佇列裡還沒下載完的大小 + 這一項 > 剩餘 → 跳過,
        後面較小的照常判斷;回傳要排入的 (位置, 名稱, 大小),排入後才記進結果。"""
        try:
            resources = await self._state.colab.probe_resources(name=name)
        except AdapterError as error:
            # 讀不到就無法確認放不放得下,其餘還沒判定的項目都跳過(001 不把讀不到當成夠用)
            for position, model, size in candidates:
                self._repo.add_item(
                    name,
                    position,
                    model,
                    reason="DISK_SPACE_UNKNOWN",
                    reason_code=error.code,
                    message=SKIPPED_MESSAGES["DISK_SPACE_UNKNOWN"],
                    size_bytes=size,
                )
            return []
        used = sum(row["size_bytes"] for row in self._downloads.pending())
        fitting: list[tuple[int, str, int]] = []
        vram = resources["vramTotalBytes"]
        for position, model, size in candidates:
            if vram is not None and size > vram:
                self._repo.add_item(
                    name,
                    position,
                    model,
                    reason="MAY_NOT_FIT",
                    message=SKIPPED_MESSAGES["MAY_NOT_FIT"],
                    size_bytes=size,
                    vram_bytes=vram,
                )
                continue
            if used + size > resources["diskFreeBytes"]:
                # 剩餘空間扣掉已決定排入與佇列裡還沒下載完的大小,才是這一項實際比較的數字
                self._repo.add_item(
                    name,
                    position,
                    model,
                    reason="DISK_SPACE_INSUFFICIENT",
                    message=SKIPPED_MESSAGES["DISK_SPACE_INSUFFICIENT"],
                    size_bytes=size,
                    free_disk_bytes=resources["diskFreeBytes"] - used,
                )
                continue
            used += size
            fitting.append((position, model, size))
        return fitting

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
