"""`settings` 表的存取(contracts/store.dbml § Table settings;整張表只有 id 為 1 的一列)。"""

import sqlite3
from typing import Any


class SettingsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self) -> dict[str, Any]:
        row = self._conn.execute("SELECT idle_timeout_minutes, low_balance_threshold FROM settings WHERE id = 1").fetchone()
        return {"idleTimeoutMinutes": row["idle_timeout_minutes"], "lowBalanceThreshold": row["low_balance_threshold"]}

    def save(self, *, idle_timeout_minutes: int, low_balance_threshold: float) -> None:
        self._conn.execute(
            "UPDATE settings SET idle_timeout_minutes = ?, low_balance_threshold = ? WHERE id = 1",
            (idle_timeout_minutes, low_balance_threshold),
        )
