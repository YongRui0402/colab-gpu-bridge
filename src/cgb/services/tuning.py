"""套用新的 Ollama 設定並重啟遠端 Ollama(FR-010–FR-016;contracts/ui.openapi.yaml § applyTuning、`info.x-apply-flow`)。"""

import asyncio
import logging
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError
from cgb.domain.session_state import RECLAIMED_MESSAGE, iso, reclaimed_fields
from cgb.repos.sessions import SessionsRepo
from cgb.repos.tunings import TuningsRepo
from cgb.services.auth import AuthService
from cgb.services.catalog import catalog_payload
from cgb.services.downloads import DownloadsService
from cgb.services.event_bus import EventBus
from cgb.services.idle_monitor import IdleMonitor
from cgb.services.session_lifecycle import AUTO_OVERRIDES, SessionLifecycle

logger = logging.getLogger(__name__)

FELL_BACK_MESSAGE = "手動設定沒有套用成功,已改回自動值"
DOWNLOAD_IN_PROGRESS_MESSAGE = "有模型正在下載,下載完才能套用"
RESTART_FAILED_MESSAGE = "遠端 Ollama 重啟失敗,執行環境已結束;請重新開啟一個工作階段。"


class TuningService:
    def __init__(
        self,
        state: Any,
        repo: SessionsRepo,
        lifecycle: SessionLifecycle,
        tunings: TuningsRepo,
        events: EventBus,
        auth: AuthService,
        downloads: DownloadsService,
        idle: IdleMonitor,
    ) -> None:
        self._state = state
        self._repo = repo
        self._lifecycle = lifecycle
        self._tunings = tunings
        self._events = events
        self._auth = auth
        self._downloads = downloads
        self._idle = idle
        # 進行中的套用工作與它正在等的 `colab exec`(名稱 → …);結束時先停工作、再等 `colab exec` 自己結束
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._restarting: dict[str, asyncio.Future[Any]] = {}

    async def apply(self, overrides: dict[str, int | None]) -> dict[str, Any]:
        """受理:記一筆進行中的紀錄、`state` 改為 `applying_tuning`,重啟在背景進行。"""
        self._require_ready()
        if (await self._auth.check())["state"] == "logged_out":
            # 照 `openSession`:受理前就擋下,免得重啟一半授權失效而失聯(Q15)
            raise ApiError(409, "AUTH_REQUIRED")
        # 等授權檢查的期間另一個分頁可能先受理了,所以檢查完再確認一次狀態
        latest = self._require_ready()
        downloading = next((row for row in self._downloads.pending() if row["state"] == "downloading"), None)
        if downloading is not None:
            # 排隊中的不擋(套用期間暫停);正在下載的不中斷,請使用者等它下載完(FR-011)
            raise ApiError(409, "DOWNLOAD_IN_PROGRESS", model=downloading["model"], message=DOWNLOAD_IN_PROGRESS_MESSAGE)
        if self._idle.active_requests > 0:
            # UI 對話與相容端點共用這個進行中的請求數;有請求沒回完時重啟會切斷它(FR-011)
            raise ApiError(409, "REQUESTS_IN_PROGRESS")
        name = latest["name"]
        record_id = self._tunings.insert_apply(session_name=name, at=iso(self._state.clock.now()), requested=overrides)
        self._repo.update(name, state="applying_tuning", step="restarting_ollama")
        task = self._lifecycle.spawn(self._run(name, record_id, overrides))
        self._tasks[name] = task
        task.add_done_callback(lambda _: self._tasks.pop(name, None))
        return self._lifecycle.current()

    async def stop(self, name: str) -> None:
        """結束工作階段時呼叫:停止套用的工作,等進行中的 `colab exec` 自己結束(不中途終止),這一次套用記為 `interrupted`。"""
        task = self._tasks.get(name)
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        restarting = self._restarting.pop(name, None)
        if restarting is not None:
            await asyncio.gather(restarting, return_exceptions=True)
        self.mark_interrupted(name)

    def mark_interrupted(self, name: str) -> None:
        """套用中的那一筆記為 `interrupted`(結束工作階段、恢復時發現執行環境已被收回都用它;工作階段的狀態由呼叫的人寫)。"""
        record = self._tunings.latest_apply(name)
        if record is not None and record["result"] == "in_progress":
            self._tunings.finish_apply(record["id"], result="interrupted", finished_at=iso(self._state.clock.now()))

    async def recover(self, name: str) -> bool:
        """後端在套用中停機、恢復時接回同一個工作階段(`info.x-applying-state` (4)):以這一次要求的設定呼叫一次 `startOllama`
        (遠端 Ollama 已在回應時只讀它的設定,否則以這組設定啟動),不重啟、不重新載入模型;這一次套用記為 `interrupted`,回到就緒。"""
        record = self._tunings.latest_apply(name)
        overrides = dict(AUTO_OVERRIDES)
        if record["attempt"] == "requested":
            overrides = {
                "numParallel": record["requested_num_parallel"],
                "contextLength": record["requested_context_length"],
                "maxLoadedModels": record["requested_max_loaded_models"],
            }
        try:
            started = await self._state.colab.start_ollama(name=name, overrides=overrides)
        except AdapterError as error:
            # 讀不回遠端 Ollama:照 (5) 結束工作階段,這一次套用仍記為 `interrupted`(不是 `failed`,Q33)
            await self._fail(name, record["id"], error, result="interrupted")
            return False
        self._tunings.record_restart(record["id"], machine=started["machine"], tuning=started["tuning"])
        now = iso(self._state.clock.now())
        self._tunings.finish_apply(record["id"], result="interrupted", finished_at=now)
        self._repo.update(name, state="ready", step=None, last_request_at=now)
        return True

    async def shutdown(self) -> None:
        """後端停機:直接取消停在重啟中的套用工作與它等的 `colab exec`;紀錄不改,恢復時才判定(`recover`)。"""
        for task in list(self._tasks.values()):
            task.cancel()
        for future in list(self._restarting.values()):
            future.cancel()
        await asyncio.gather(*self._tasks.values(), *self._restarting.values(), return_exceptions=True)

    async def _restart(self, name: str, overrides: dict[str, int | None]) -> dict[str, Any]:
        """呼叫 `restart_ollama`;被取消(結束工作階段)時 `colab exec` 照樣跑完,由 `stop` 等它。"""
        future = asyncio.ensure_future(self._state.colab.restart_ollama(name=name, overrides=overrides))
        self._restarting[name] = future
        try:
            return await asyncio.shield(future)
        finally:
            if future.done():
                self._restarting.pop(name, None)

    def _require_ready(self) -> dict[str, Any]:
        """目前的工作階段要是就緒:已經在套用回 409,其他狀態(含沒有工作階段)回 503。"""
        latest = self._repo.latest()
        if latest is not None and latest["state"] == "applying_tuning":
            # 另一個分頁先按了套用;受理與改成 `applying_tuning` 之間沒有 await,所以同時送來的只有一個通過
            raise ApiError(409, "TUNING_IN_PROGRESS")
        if latest is None or latest["state"] != "ready":
            # 沒有工作階段、開啟中、重連中、結束中、已結束、開啟失敗或失聯:都不是就緒
            raise ApiError(503, "NO_READY_SESSION")
        return latest

    async def _run(self, name: str, record_id: int, overrides: dict[str, int | None]) -> None:
        try:
            await self._apply(name, record_id, overrides)
        except AdapterError as error:
            await self._fail(name, record_id, error)

    async def _fail(self, name: str, record_id: int, error: AdapterError, *, result: str = "failed") -> None:
        """無法回到就緒(`info.x-apply-flow` (5)):這一筆記 `result`(恢復時是 `interrupted`),工作階段標成失聯並釋放執行環境。"""
        now = iso(self._state.clock.now())
        reclaimed = error.code == "COLAB_NOT_FOUND"
        message = RECLAIMED_MESSAGE if reclaimed else RESTART_FAILED_MESSAGE
        stage = error.remote_stage if error.code == "COLAB_REMOTE_ERROR" else None
        self._tunings.fail_apply(
            record_id, finished_at=now, reason_code=error.code, remote_stage=stage, message=message, result=result
        )
        if error.code == "AUTH_REQUIRED":
            # 授權過期不是失聯的原因,讓 UI 知道要重新登入(照 001)
            self._auth.mark_logged_out()
        if reclaimed:
            # 執行環境已被 Colab 收回:照 001 標成失聯,已經不在了,不必釋放
            self._repo.update(name, **reclaimed_fields(now))
            return
        self._repo.update(
            name,
            state="lost",
            active_slot=None,
            step=None,
            end_reason="OLLAMA_RESTART_FAILED",
            reason_code=error.code,
            message=message,
            ended_at=now,
        )
        await self._lifecycle.release(name)

    async def _apply(self, name: str, record_id: int, overrides: dict[str, int | None]) -> None:
        base_url = self._lifecycle.base_url
        loaded = await self._loaded_models(base_url)
        restarted, result, message = await self._restart_or_fall_back(name, record_id, overrides)
        self._tunings.record_restart(record_id, machine=restarted["machine"], tuning=restarted["tuning"])
        vram_bytes = restarted["machine"]["vramTotalBytes"]
        await self._publish_models(base_url, vram_bytes)
        self._repo.update(name, step="reloading_models")
        await self._reload_models(record_id, base_url, vram_bytes, loaded, restarted["tuning"]["maxLoadedModels"]["value"])
        self._finish(name, record_id, overrides, result, message)

    async def _loaded_models(self, base_url: str) -> list[str]:
        """重啟前 `/api/ps` 列出的模型,依它的順序;讀不到就當作沒有已載入的模型,照常往下(`info.x-apply-flow` (1))。"""
        try:
            return [m["name"] for m in (await self._state.remote_ollama.list_loaded_models(base_url=base_url))["models"]]
        except AdapterError:
            return []

    async def _restart_or_fall_back(
        self, name: str, record_id: int, overrides: dict[str, int | None]
    ) -> tuple[dict[str, Any], str, str | None]:
        """重啟遠端 Ollama;遠端腳本失敗就改用自動值再試一次(`requested` 保留這次要求的值,FR-013)。回傳 (重啟結果, 結果, 說明)。"""
        try:
            return await self._restart(name, overrides), "applied", None
        except AdapterError as error:
            if error.code not in ("COLAB_REMOTE_ERROR", "COLAB_INVALID_TUNING"):
                raise
            self._tunings.mark_fallback(record_id, reason_code=error.code, remote_stage=error.remote_stage)
            self._repo.notify()
            return await self._restart(name, dict(AUTO_OVERRIDES)), "fell_back_to_auto", FELL_BACK_MESSAGE

    async def _reload_models(
        self, record_id: int, base_url: str, vram_bytes: int | None, loaded: list[str], limit: int | None
    ) -> None:
        """依重啟前 `/api/ps` 的順序一次一個預先載入,載到新的同時載入模型數(`limit`,None 是不設上限)為止,其餘列為超出上限(FR-012)。"""
        reload_count = len(loaded) if limit is None else limit
        for position, model in enumerate(loaded[reload_count:], start=reload_count):
            self._tunings.add_model(record_id, position=position, model=model, reason="OVER_LIMIT")
        for position, model in enumerate(loaded[:reload_count]):
            try:
                await self._state.remote_ollama.preload(base_url=base_url, model=model)
            except AdapterError as error:
                # 單一模型預先載入失敗不讓套用失敗:列為沒有重新載入,接著載下一個
                self._tunings.add_model(record_id, position=position, model=model, reason="PRELOAD_FAILED", reason_code=error.code)
            else:
                self._tunings.add_model(record_id, position=position, model=model)
            await self._publish_models(base_url, vram_bytes)

    def _finish(self, name: str, record_id: int, overrides: dict[str, int | None], result: str, message: str | None) -> None:
        """回到就緒:寫結果,套用成功才記住這種類型的覆蓋值(FR-014),重設閒置倒數(研究 R10)。"""
        finished_at = iso(self._state.clock.now())
        self._tunings.finish_apply(record_id, result=result, finished_at=finished_at, message=message)
        if result == "applied":
            # `updatedAt` 和這一筆的完成時間相同;改回自動值不寫
            self._tunings.put_type_override(self._repo.get(name)["runtime_type_gpu"], overrides, at=finished_at)
        self._repo.update(name, state="ready", step=None, last_request_at=finished_at)

    async def _publish_models(self, base_url: str, vram_bytes: int | None) -> None:
        """推送 `models.updated`(目錄的完整現況)。目錄這時不是就緒、`Catalog` 讀不了,所以這裡直接讀遠端 Ollama;
        推送是附帶的,失敗不能讓套用失敗。"""
        remote = self._state.remote_ollama
        try:
            local = (await remote.list_local_models(base_url=base_url))["models"]
            loaded = {m["name"] for m in (await remote.list_loaded_models(base_url=base_url))["models"]}
            catalog = catalog_payload(local, loaded, vram_bytes, {})
        except Exception:
            logger.exception("套用設定時推送模型目錄失敗,略過這一次")
            return
        self._events.models_updated(catalog)
