"""閒置時限與餘額警告門檻(FR-027;contracts/ui.openapi.yaml § Settings)。"""

from collections.abc import Callable
from typing import Any

from cgb.domain.errors import ApiError
from cgb.repos.settings import SettingsRepo
from cgb.services.event_bus import EventBus

# Q34:閒置時限 1–1440 分鐘的整數、警告門檻 0–10000
IDLE_TIMEOUT_RANGE = (1, 1440)
THRESHOLD_RANGE = (0, 10000)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def parse_settings(body: Any) -> tuple[int, float]:
    """驗證 `Settings` 本文,回傳(閒置時限, 警告門檻)。"""
    if not isinstance(body, dict) or "idleTimeoutMinutes" not in body or "lowBalanceThreshold" not in body:
        raise ApiError(400, "INVALID_REQUEST_BODY")
    idle, threshold = body["idleTimeoutMinutes"], body["lowBalanceThreshold"]
    low, high = IDLE_TIMEOUT_RANGE
    if not isinstance(idle, int) or isinstance(idle, bool) or not low <= idle <= high:
        raise ApiError(400, "INVALID_IDLE_TIMEOUT")
    low, high = THRESHOLD_RANGE
    if not _is_number(threshold) or not low <= threshold <= high:
        raise ApiError(400, "INVALID_BALANCE_THRESHOLD")
    return idle, threshold


class SettingsService:
    def __init__(self, repo: SettingsRepo, events: EventBus) -> None:
        self._repo = repo
        self._events = events
        # 儲存成功之後呼叫(閒置倒數依新的時限重算)
        self.listeners: list[Callable[[dict[str, Any]], None]] = []

    def current(self) -> dict[str, Any]:
        return self._repo.get()

    def update(self, body: Any) -> dict[str, Any]:
        """儲存後立即生效,並推送 `settings.updated`。"""
        idle, threshold = parse_settings(body)
        # 兩個欄位都驗證過才寫入,不會只寫進其中一個
        self._repo.save(idle_timeout_minutes=idle, low_balance_threshold=threshold)
        settings = self.current()
        self._events.settings_updated(settings)
        for listener in list(self.listeners):
            listener(settings)
        return settings
