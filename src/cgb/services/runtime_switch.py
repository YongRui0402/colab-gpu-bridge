"""變更執行階段類型並重開(FR-010;contracts/ui.openapi.yaml § restartSession)。

先結束原本的執行環境,再以新類型開新的(同一時間不會有兩台);原本已載入的模型加進下載佇列,
新的就緒後佇列自動繼續,重新下載並預先載入。
"""

from typing import Any

from cgb.domain.errors import ApiError
from cgb.domain.session_state import ACTIVE_STATES, iso
from cgb.repos.sessions import SessionsRepo
from cgb.services.downloads import DownloadsService
from cgb.services.session_lifecycle import SessionLifecycle


class RuntimeSwitch:
    def __init__(self, state: Any, repo: SessionsRepo, lifecycle: SessionLifecycle, downloads: DownloadsService) -> None:
        self._state = state
        self._repo = repo
        self._lifecycle = lifecycle
        self._downloads = downloads

    async def restart(self, runtime_type: dict[str, Any], tuning: dict[str, Any] | None) -> dict[str, Any]:
        """`tuning` 是本文帶的覆蓋值(已驗證);沒有帶時是 None。"""
        remote = self._state.remote_ollama
        latest = self._repo.latest()
        if latest is not None and latest["state"] == "ending":
            # 照 001 restartSession 的 409:目前的工作階段正在結束
            raise ApiError(409, "SESSION_ENDING")
        if latest is not None and latest["state"] == "applying_tuning":
            # 套用設定中結束舊的執行環境,套用的工作會對已不在的執行環境重新載入;等套用結束再變更(`info.x-applying-state` (3))
            raise ApiError(409, "TUNING_IN_PROGRESS")
        if latest is None or latest["state"] not in ACTIVE_STATES:
            # 沒有工作階段時不把 restart 當成開啟(這時直接用 openSession)
            raise ApiError(409, "NO_ACTIVE_SESSION")
        old = latest["name"]
        base_url = self._lifecycle.base_url
        loaded = (await remote.list_loaded_models(base_url=base_url))["models"]
        sizes = {m["name"]: m["size"] for m in (await remote.list_local_models(base_url=base_url))["models"]}
        # ending 不占位:舊的先改成 ending,才寫得進新的(store.dbml active_slot);
        # 變成 ending 時佇列照 `info.x-queue-clearing` (1) 清空,清除之後才排入重新載入的項目(FR-002)
        self._repo.update(old, state="ending", active_slot=None, step=None, end_reason="RUNTIME_TYPE_CHANGED")
        new = self._lifecycle.reserve(runtime_type, step="ending_previous")
        # 不沿用舊的工作階段的設定;沒有帶時用新類型記住的值(spec 邊界情況「變更執行階段類型」、FR-008)
        overrides = self._lifecycle.accept_overrides(runtime_type["gpu"], tuning)
        for model in loaded:
            self._downloads.enqueue_restore(model["name"], sizes.get(model["name"], 0), new)
        self._lifecycle.spawn(self._run(old, new, runtime_type, overrides))
        return self._lifecycle.current()

    async def _run(self, old: str, new: str, runtime_type: dict[str, Any], overrides: dict[str, Any]) -> None:
        await self._state.tunnel.close_tunnel(session_name=old)
        await self._state.colab.stop_session(name=old)
        self._repo.update(old, state="ended", ended_at=iso(self._state.clock.now()))
        self._repo.update(new, step="allocating")
        # 新的就緒後,佇列(含要重新下載的模型)由 DownloadsService.resume 自動繼續
        await self._lifecycle.start_open(new, runtime_type, overrides)
