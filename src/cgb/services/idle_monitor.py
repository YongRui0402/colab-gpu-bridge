"""閒置計時(FR-026、Q24):只有 Ollama 相容端點的請求算數,UI API 與健康檢查都不算(Q89)。"""

import asyncio
import logging
from typing import Any

from cgb.domain.idle import idle_countdown
from cgb.domain.session_state import iso, parse_iso
from cgb.repos.sessions import SessionsRepo
from cgb.services.session_lifecycle import SessionLifecycle
from cgb.services.settings import SettingsService

# 背景檢查的間隔(注入的時鐘);SC-006 要求到期後 1 分鐘內結束
CHECK_SECONDS = 1.0

logger = logging.getLogger(__name__)


class IdleMonitor:
    def __init__(self, state: Any, repo: SessionsRepo, lifecycle: SessionLifecycle, settings: SettingsService) -> None:
        self._state = state
        self._repo = repo
        self._lifecycle = lifecycle
        self._settings = settings
        # Ollama 相容端點目前進行中的請求數(含串流中)
        self.active_requests = 0
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        """不等請求進來,在背景定時檢查是否閒置到期。"""
        while True:
            await self._state.clock.sleep(CHECK_SECONDS)
            try:
                await self._check()
            except Exception:
                # Q191:非預期的例外不能讓閒置檢查停掉(否則不會再自動結束),記下來,下一輪照常檢查
                logger.exception("閒置檢查時發生非預期的錯誤,下一輪再試")

    def countdown(self, row: dict[str, Any]) -> dict[str, Any]:
        return idle_countdown(
            row, timeout_minutes=self._settings.current()["idleTimeoutMinutes"], active_requests=self.active_requests
        )

    def check_now(self) -> None:
        """不等下一次檢查,立刻看一次是否已經閒置到期(例如閒置時限剛改短,FR-027)。"""
        self._lifecycle.spawn(self._check())

    async def _check(self) -> None:
        row = self._repo.latest()
        if row is None or row["state"] != "ready":
            return
        deadline = self.countdown(row)["deadline"]
        if deadline is not None and self._state.clock.now() >= parse_iso(deadline):
            await self._lifecycle.end(end_reason="IDLE_TIMEOUT")

    def request_started(self) -> None:
        """Ollama 相容端點收到請求:進行中的請求數加一,並重設閒置計時。"""
        self.active_requests += 1
        self._reset()

    def request_finished(self) -> None:
        """請求(含串流回應)結束:進行中的請求數減一;最後一個結束時再重設一次(Q24)。"""
        self.active_requests -= 1
        if self.active_requests == 0:
            self._reset()

    def _reset(self) -> None:
        # 只在就緒時有計時可重設;寫進 sessions 表,後端重啟後接著算(Q75)
        row = self._repo.latest()
        if row is None or row["state"] != "ready":
            return
        self._repo.update(row["name"], last_request_at=iso(self._state.clock.now()))
