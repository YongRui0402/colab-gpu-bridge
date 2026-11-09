"""變更執行階段類型並重開(FR-010;contracts/ui.openapi.yaml § restartSession)。

先結束原本的執行環境,再以新類型開新的(同一時間不會有兩台);原本已載入的模型加進下載佇列,新的就緒後重新下載並預先載入。
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

    async def restart(self, runtime_type: dict[str, Any]) -> dict[str, Any]:
        remote = self._state.remote_ollama
        latest = self._repo.latest()
        if latest is None or latest["state"] not in ACTIVE_STATES:
            # 沒有工作階段時不把 restart 當成開啟(這時直接用 openSession)
            raise ApiError(409, "NO_ACTIVE_SESSION")
        old = latest["name"]
        base_url = self._lifecycle.base_url
        loaded = (await remote.list_loaded_models(base_url=base_url))["models"]
        sizes = {m["name"]: m["size"] for m in (await remote.list_local_models(base_url=base_url))["models"]}
        for model in loaded:
            self._downloads.enqueue_restore(model["name"], sizes.get(model["name"], 0))
        # ending 不占位:舊的先改成 ending,才寫得進新的(store.dbml active_slot)
        self._repo.update(old, state="ending", active_slot=None, step=None, end_reason="RUNTIME_TYPE_CHANGED")
        new = self._lifecycle.reserve(runtime_type, step="ending_previous")
        self._lifecycle.spawn(self._run(old, new, runtime_type))
        return self._lifecycle.current()

    async def _run(self, old: str, new: str, runtime_type: dict[str, Any]) -> None:
        await self._state.tunnel.close_tunnel(session_name=old)
        await self._state.colab.stop_session(name=old)
        self._repo.update(old, state="ended", ended_at=iso(self._state.clock.now()))
        self._repo.update(new, step="allocating")
        await self._lifecycle.start_open(new, runtime_type)
        if self._repo.get(new)["state"] == "ready" and self._lifecycle.base_url is not None:
            await self._downloads.run_queue(self._lifecycle.base_url)
