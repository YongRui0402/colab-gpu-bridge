"""健康檢查與斷線處理(FR-003、FR-004;contracts/tunnel.openapi.yaml § checkTunnelHealth、reconnectTunnel)。

健康檢查只經通道的 `check_health`(打遠端 `/api/version`),不經 Ollama 相容端點,不會重設閒置計時(Q89)。
"""

import asyncio
from typing import Any

from cgb.adapters.errors import AdapterError
from datetime import timedelta

from cgb.domain.session_state import RECONNECT_TIMEOUT_MESSAGE, iso, listed_names, reclaimed_fields, reconnect_offsets, release_warning_fields
from cgb.repos.sessions import SessionsRepo


class HealthMonitor:
    def __init__(self, state: Any, repo: SessionsRepo) -> None:
        self._state = state
        self._repo = repo
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            await self._state.clock.sleep(self._state.timeouts.health_interval)
            latest = self._repo.latest()
            if latest is not None and latest["state"] == "ready":
                await self._check(latest["name"])

    async def _check(self, name: str) -> None:
        try:
            await self._state.tunnel.check_health(session_name=name)
            return
        except AdapterError:
            pass
        await self._reconnect(name)

    async def _reconnect(self, name: str) -> None:
        """Q67:每一輪先關通道、查 `colab sessions`、再建立;輪與輪之間照節奏等,下一輪開始超過時限就不再開始。"""
        clock, timeouts = self._state.clock, self._state.timeouts
        started_at = clock.now()
        self._repo.update(
            name,
            state="reconnecting",
            reconnect_started_at=iso(started_at),
            reconnect_deadline=iso(started_at + timedelta(seconds=timeouts.reconnect_limit)),
        )
        origin = clock.monotonic()
        last_code = "TUNNEL_TIMEOUT"
        for offset in reconnect_offsets(timeouts.reconnect_backoff, timeouts.reconnect_interval, timeouts.reconnect_limit):
            await clock.sleep(origin + offset - clock.monotonic())
            await self._state.tunnel.close_tunnel(session_name=name)
            try:
                listed = await self._state.colab.list_sessions()
            except AdapterError:
                # 例如家裡網路斷了:確認不了,當成還在,繼續這一輪
                listed = None
            if listed is not None and name not in listed_names(listed):
                self._mark_reclaimed(name)
                return
            try:
                await self._state.tunnel.open_tunnel(session_name=name)
            except AdapterError as error:
                last_code = error.code
                continue
            self._repo.update(name, state="ready", reconnect_started_at=None, reconnect_deadline=None)
            return
        await clock.sleep(origin + timeouts.reconnect_limit - clock.monotonic())
        # 期限到這件事由 endReason 表達,reasonCode 給出接不回的原因(contracts/tunnel.openapi.yaml § reconnectTunnel)
        self._repo.update(
            name,
            state="lost",
            active_slot=None,
            end_reason="RECONNECT_TIMEOUT",
            reason_code=last_code,
            message=RECONNECT_TIMEOUT_MESSAGE,
            ended_at=iso(clock.now()),
            reconnect_started_at=None,
            reconnect_deadline=None,
        )
        # FR-004:確保該執行環境被釋放;釋放不了就在 UI 警告(FR-007)
        try:
            await self._state.colab.stop_session(name=name)
        except AdapterError as error:
            self._repo.update(
                name,
                **release_warning_fields(error.code, iso(clock.now())),
            )

    def _mark_reclaimed(self, name: str) -> None:
        self._repo.update(name, **reclaimed_fields(iso(self._state.clock.now())))
