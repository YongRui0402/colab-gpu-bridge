"""後端重新啟動後接回工作階段(FR-005;research.md R10)。

讀資料庫最後一筆未結束的工作階段 → `colab sessions` 確認那個名稱還在 → 清掉上一個行程留下的 ssh → 重建轉發 → 回到就緒。
"""

import asyncio
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.session_state import TERMINAL_STATES, iso, listed_names, reclaimed_fields
from cgb.repos.sessions import SessionsRepo
from cgb.services.session_lifecycle import TUNNEL_LOCAL_PORT


class Recovery:
    def __init__(self, state: Any, repo: SessionsRepo, key_path: str) -> None:
        self._state = state
        self._repo = repo
        self._key_path = key_path
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        listed = await self._state.colab.list_sessions()
        detected_at = iso(self._state.clock.now())
        # Q100:是不是本系統的執行環境以資料庫的名稱為準,不看前綴。
        # 資料庫不認得的(名稱是 `?`,或別的實例開的)不接手、不關閉,只提示(Q122);
        # 資料庫認得、但本系統認為已結束的是遺留,要釋放(FR-007)
        unmanaged = list(listed["unnamed"])
        leftovers: list[str] = []
        for entry in listed["named"]:
            known = self._repo.get(entry["name"])
            if known is None:
                unmanaged.append(entry)
            elif known["state"] in TERMINAL_STATES:
                leftovers.append(entry["name"])
        self._repo.unmanaged_runtimes = [{"hardware": entry["hardware"], "detectedAt": detected_at} for entry in unmanaged]
        for leftover in leftovers:
            try:
                await self._state.colab.stop_session(name=leftover)
            except AdapterError:
                pass
        unfinished = self._repo.latest_unfinished()
        if unfinished is None:
            return
        name = unfinished["name"]
        if name not in listed_names(listed):
            # 資料庫說還在、Colab 帳號下已經沒有:被收回(不照資料庫標成就緒)
            self._repo.update(name, **reclaimed_fields(iso(self._state.clock.now())))
            return
        await self._state.tunnel.cleanup_residual(key_path=self._key_path)
        await self._state.tunnel.open_tunnel(session_name=name, key_path=self._key_path, local_port=TUNNEL_LOCAL_PORT)
        self._repo.update(name, state="ready", active_slot=1)
