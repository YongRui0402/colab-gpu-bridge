"""後端重新啟動後接回工作階段(FR-005;research.md R10)。

讀資料庫最後一筆未結束的工作階段 → `colab sessions` 確認那個名稱還在 → 清掉上一個行程留下的 ssh → 重建轉發 → 回到就緒。
"""

import asyncio
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.session_state import TERMINAL_STATES, iso, listed_names, reclaimed_fields, release_warning_fields
from cgb.repos.sessions import SessionsRepo
from cgb.services.downloads import DownloadsService
from cgb.services.session_lifecycle import SessionLifecycle


class Recovery:
    def __init__(
        self, state: Any, repo: SessionsRepo, key_path: str, lifecycle: SessionLifecycle, downloads: DownloadsService
    ) -> None:
        self._state = state
        self._repo = repo
        self._key_path = key_path
        self._downloads = downloads
        # Q170:接回時經工作階段用例建立通道,轉發位址才會寫回
        self._lifecycle = lifecycle
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        # 升級前留下、沒有所屬工作階段的項目不論有沒有工作階段可接回都移除(FR-003)
        self._downloads.clear_unowned()
        # 先判定有沒有上一個行程留下的工作階段:有才把中斷的下載改回排隊中(FR-021),沒有的話佇列不會有要接續的項目;
        # 接著的 `_run` 若發現已被收回,清除會連這些項目一起移除(FR-003)。放在同步的這裡,UI 一連上就看到排隊中
        if self._repo.latest_unfinished() is not None:
            self._downloads.requeue_interrupted()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        # Q190:先記下上一個行程留下的那筆,再列 sessions;列的期間才開啟的工作階段不歸接回判定
        unfinished = self._repo.latest_unfinished()
        # 接回期間 UI 顯示「接回中」(Q167);回到就緒前先清掉,推送的就緒才不會帶著它
        self._lifecycle.resuming = unfinished["name"] if unfinished is not None else None
        try:
            name = await self._reattach(unfinished)
        finally:
            self._lifecycle.resuming = None
        if name is not None:
            self._repo.update(name, state="ready", active_slot=1)

    async def _reattach(self, unfinished: dict[str, Any] | None) -> str | None:
        """接回上一個行程留下的那筆;回傳接回的名稱,沒有要接回的(或已被收回)時回 None。"""
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
            except AdapterError as error:
                # FR-007:釋放不了就在 UI 警告;掛在目前那筆工作階段上(Q161)
                latest = self._repo.latest()
                if latest is not None:
                    self._repo.update(latest["name"], **release_warning_fields(error.code, iso(self._state.clock.now())))
        if unfinished is None:
            return None
        name = unfinished["name"]
        if name not in listed_names(listed):
            # 資料庫說還在、Colab 帳號下已經沒有:被收回(不照資料庫標成就緒)
            self._repo.update(name, **reclaimed_fields(iso(self._state.clock.now())))
            return None
        await self._state.tunnel.cleanup_residual(key_path=self._key_path)
        await self._lifecycle.open_tunnel(name)
        return name
