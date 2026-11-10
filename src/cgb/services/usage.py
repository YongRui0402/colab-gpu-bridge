"""定時讀帳號用量(FR-024、NFR-008;contracts/colab-cli.openapi.yaml § getUsage)。

啟動時讀一次,之後每 `POLL_SECONDS` 讀一次(不論 UI 有沒有打開);讀成功就覆寫快照。
"""

import asyncio
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.session_state import iso, parse_iso
from cgb.domain.usage_calc import failure_of, usage_payload
from cgb.repos.usage import UsageRepo
from cgb.services.event_bus import EventBus
from cgb.services.settings import SettingsService

# NFR-008 要求至少每 5 分鐘讀一次;排程的等待會被讀取本身的時間拉長,所以取 4 分鐘留餘裕
POLL_SECONDS = 240.0


class UsageService:
    def __init__(self, state: Any, repo: UsageRepo, events: EventBus, settings: SettingsService) -> None:
        self._state = state
        self._repo = repo
        self._events = events
        # 警告門檻每次都照目前的設定判斷,改了門檻不必等下一次讀用量(FR-027)
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        # 最近一次讀取失敗的說明;只放記憶體,讀成功就清掉(Q123)
        self._failure: dict[str, Any] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            await self.read_once()
            await self._state.clock.sleep(POLL_SECONDS)

    async def read_once(self) -> None:
        """讀一次;成功或失敗都推送 `usage.updated`(contracts/ui-events.asyncapi.yaml § sendUsageUpdated)。"""
        await self._read()
        self.publish()

    async def _read(self) -> None:
        try:
            usage = await self._state.colab.get_usage()
        except AdapterError as error:
            self._failure = failure_of(error.code, iso(self._state.clock.now()))
            return
        self._failure = None
        self._repo.save(
            balance=usage["balance"], rate_per_hour=usage["ratePerHour"], read_at=iso(parse_iso(usage["readAt"]))
        )

    def current(self) -> dict[str, Any]:
        threshold = self._settings.current()["lowBalanceThreshold"]
        return usage_payload(self._repo.latest(), failure=self._failure, threshold=threshold, now=self._state.clock.now())

    def publish(self) -> None:
        """不重新讀,以最後的快照推送一次 `usage.updated`(例如警告門檻改變時)。"""
        self._events.usage_updated(self.current())

    def balance_may_be_depleted(self) -> bool:
        """最後讀到的餘額小於等於 0(從沒讀到過時不提示)。"""
        snapshot = self._repo.latest()
        return snapshot is not None and snapshot["balance"] <= 0
