"""用量的對外形狀(contracts/ui.openapi.yaml § Usage;FR-024、FR-025、NFR-008)。純函式,不碰 I/O。"""

from datetime import datetime, timedelta
from typing import Any

from cgb.domain.session_state import parse_iso

# NFR-008:讀取時間超過 15 分鐘標成過期
STALE_AFTER = timedelta(minutes=15)

# 讀取用量失敗的說明(Usage.message);只用這張表,不把轉接層的原始訊息交給 UI(NFR-010)
FAILURE_MESSAGES: dict[str, str] = {
    "AUTH_REQUIRED": "Colab 帳號尚未登入或授權已過期,讀不到 compute units 用量;請先登入 Colab。",
    "COLAB_UNREACHABLE": "連不到 Colab,讀不到 compute units 用量;會繼續定時重試。",
    "COLAB_TIMEOUT": "Colab 在時限內沒有回應,讀不到 compute units 用量;會繼續定時重試。",
}
FAILURE_FALLBACK_MESSAGE = "讀不到 compute units 用量;會繼續定時重試。"


def failure_of(reason_code: str, failed_at: str) -> dict[str, Any]:
    """最近一次讀取失敗的說明(Q123:`reasonCode`、`message`、`lastFailedAt`)。"""
    return {
        "reasonCode": reason_code,
        "message": FAILURE_MESSAGES.get(reason_code, FAILURE_FALLBACK_MESSAGE),
        "lastFailedAt": failed_at,
    }


NO_FAILURE: dict[str, Any] = {"reasonCode": None, "message": None, "lastFailedAt": None}


def hours_remaining(balance: float, rate_per_hour: float) -> float | None:
    """估計還能用的時數(餘額 ÷ 每小時耗用);耗用為 0 時是 null,餘額小於等於 0 時是 0(Q120)。"""
    if rate_per_hour <= 0:
        return None
    if balance <= 0:
        return 0
    return balance / rate_per_hour


def usage_payload(
    snapshot: dict[str, Any] | None, *, failure: dict[str, Any] | None, threshold: float, now: datetime
) -> dict[str, Any]:
    """最後一次讀到的用量快照(`usage_snapshots` 的一列)與最近一次讀取失敗的說明換成 `Usage`。

    從來沒讀到過時是 `unknown`,數值與 `readAt` 都是 null(Q119)。
    """
    reason = failure if failure is not None else NO_FAILURE
    if snapshot is None:
        return {
            "state": "unknown",
            "balance": None,
            "ratePerHour": None,
            "hoursRemaining": None,
            "readAt": None,
            "stale": False,
            "lowBalance": False,
            "warningThreshold": threshold,
            **reason,
        }
    balance = snapshot["balance"]
    rate = snapshot["rate_per_hour"]
    read_at = snapshot["read_at"]
    return {
        "state": "known",
        "balance": balance,
        "ratePerHour": rate,
        "hoursRemaining": hours_remaining(balance, rate),
        "readAt": read_at,
        "stale": now - parse_iso(read_at) > STALE_AFTER,
        "lowBalance": balance < threshold,
        "warningThreshold": threshold,
        **reason,
    }
