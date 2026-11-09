"""工作階段的狀態與對外的形狀(contracts/ui.openapi.yaml § Session)。純函式,不碰 I/O。"""

from datetime import datetime, timedelta
from typing import Any

from cgb.domain.errors import RELEASE_WARNING_MESSAGE, ApiError

# contracts/ui.openapi.yaml § GpuType(大小寫須完全相同;CLI 會把認不得的名稱當成 A100)
GPU_TYPES = ("T4", "L4", "G4", "A100", "H100")

# FR-006:這些狀態占用唯一的位子(store.dbml sessions.active_slot)
ACTIVE_STATES = frozenset({"opening", "ready", "reconnecting"})

# 一定有 endReason 的結束狀態
TERMINAL_STATES = frozenset({"ended", "open_failed", "lost"})

# 閒置時限的預設值(contracts/ui.openapi.yaml § Settings.idleTimeoutMinutes)
DEFAULT_IDLE_TIMEOUT_MINUTES = 30

# 失聯時給使用者的說明(FR-003、FR-004)
RECLAIMED_MESSAGE = "執行環境已被 Colab 收回,請重新開啟一個工作階段。"
RECONNECT_TIMEOUT_MESSAGE = "重連逾時,接不回原本的執行環境,已將它結束;請重新開啟一個工作階段。"


def release_warning_fields(reason_code: str | None, detected_at: str | None) -> dict[str, Any]:
    """寫進 sessions 表的釋放警告欄位(FR-007);`reason_code` 與 `detected_at` 都是 None 表示清掉警告。"""
    return {
        "release_warning_reason_code": reason_code,
        "release_warning_message": RELEASE_WARNING_MESSAGE if detected_at is not None else None,
        "release_warning_detected_at": detected_at,
    }


def reclaimed_fields(ended_at: str) -> dict[str, Any]:
    """被 Colab 收回而失聯(FR-003、FR-004、FR-005)時寫進 sessions 表的欄位。"""
    return {
        "state": "lost",
        "active_slot": None,
        "step": None,
        "end_reason": "RECLAIMED_BY_COLAB",
        "message": RECLAIMED_MESSAGE,
        "ended_at": ended_at,
    }


def listed_names(listed: dict[str, Any]) -> set[str]:
    """`colab sessions` 的結果裡本機認得名稱的那些(contracts/colab-cli.openapi.yaml § SessionList.named)。"""
    return {entry["name"] for entry in listed["named"]}


def reconnect_offsets(backoff: tuple[float, ...], interval: float, limit: float) -> list[float]:
    """重連每一輪開始的時間(相對於第 1 輪):前幾輪照 `backoff` 等,之後每 `interval`;超過 `limit` 的那一輪不開始(Q67)。"""
    offsets: list[float] = []
    offset = 0.0
    waits = iter(backoff)
    while True:
        offset += next(waits, interval)
        if offset > limit:
            return offsets
        offsets.append(offset)


def iso(when: datetime) -> str:
    """ISO 8601 UTC 字串(store.dbml:例 2026-11-09T08:30:00Z)。"""
    return when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_iso(value: str) -> datetime:
    """`iso()` 的反向:資料庫存的 ISO 8601 UTC 字串換回 datetime。"""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def runtime_type_of(row: dict[str, Any]) -> dict[str, Any]:
    """sessions 表攤平的欄位換回 `RuntimeType`。"""
    return {"gpu": row["runtime_type_gpu"], "highMem": bool(row["runtime_type_high_mem"])}


def parse_runtime_type(body: Any) -> dict[str, Any]:
    """驗證 `OpenSessionInput`,回傳 `RuntimeType`。"""
    if not isinstance(body, dict) or not isinstance(body.get("runtimeType"), dict):
        raise ApiError(400, "INVALID_REQUEST_BODY")
    runtime_type = body["runtimeType"]
    if runtime_type.get("gpu") not in GPU_TYPES or not isinstance(runtime_type.get("highMem"), bool):
        raise ApiError(400, "INVALID_RUNTIME_TYPE")
    return {"gpu": runtime_type["gpu"], "highMem": runtime_type["highMem"]}


def session_payload(row: dict[str, Any] | None, unmanaged_runtimes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """資料庫的一列換成 `Session`;沒有任何一列時是 `none`。不是本系統開的執行環境不論有沒有工作階段都附上。"""
    unmanaged = {"unmanagedRuntimes": list(unmanaged_runtimes or [])}
    if row is None:
        return {"state": "none", **unmanaged}
    return {
        **unmanaged,
        "state": row["state"],
        "name": row["name"],
        "runtimeType": runtime_type_of(row),
        "step": row["step"],
        "endReason": row["end_reason"],
        "reasonCode": row["reason_code"],
        "message": row["message"],
        "openedAt": row["opened_at"],
        "readyAt": row["ready_at"],
        "endedAt": row["ended_at"],
        "releaseWarning": _release_warning(row),
        "idle": _idle(row),
    }


def _idle(row: dict[str, Any]) -> dict[str, Any] | None:
    """FR-026、Q24:只有 Ollama 相容端點的請求會重設;沒有任何請求時是就緒的時間(健康檢查不算,Q89)。"""
    if row["state"] != "ready":
        return None
    last = row["last_request_at"] or row["ready_at"]
    deadline = parse_iso(last) + timedelta(minutes=DEFAULT_IDLE_TIMEOUT_MINUTES)
    return {
        "timeoutMinutes": DEFAULT_IDLE_TIMEOUT_MINUTES,
        "activeRequests": 0,
        "lastRequestAt": last,
        "deadline": iso(deadline),
    }


def _release_warning(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["release_warning_message"] is None:
        return None
    return {
        "reasonCode": row["release_warning_reason_code"],
        "message": row["release_warning_message"],
        "detectedAt": row["release_warning_detected_at"],
    }
