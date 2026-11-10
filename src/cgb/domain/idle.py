"""閒置倒數(FR-026、Q24;contracts/ui.openapi.yaml § IdleCountdown)。純函式,不碰 I/O。"""

from datetime import timedelta
from typing import Any

from cgb.domain.session_state import iso, parse_iso


def idle_countdown(row: dict[str, Any], *, timeout_minutes: int, active_requests: int) -> dict[str, Any]:
    """就緒中的工作階段(sessions 表的一列)的閒置倒數。

    沒有任何請求時以就緒的時間起算;有請求進行中時不計閒置,`deadline` 為 null。
    """
    last = row["last_request_at"] or row["ready_at"]
    deadline = None if active_requests > 0 else iso(parse_iso(last) + timedelta(minutes=timeout_minutes))
    return {
        "timeoutMinutes": timeout_minutes,
        "activeRequests": active_requests,
        "lastRequestAt": last,
        "deadline": deadline,
    }
