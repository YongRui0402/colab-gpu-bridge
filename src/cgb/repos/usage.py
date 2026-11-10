"""`usage_snapshots` 表的存取(contracts/store.dbml § Table usage_snapshots;Q76 只留最後一筆)。"""

import sqlite3
from typing import Any


class UsageRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def latest(self) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT balance, rate_per_hour, read_at FROM usage_snapshots WHERE id = 1").fetchone()
        return dict(row) if row is not None else None

    def save(self, *, balance: float, rate_per_hour: float, read_at: str) -> None:
        """每次讀成功就覆寫唯一的那一列。"""
        self._conn.execute(
            "INSERT OR REPLACE INTO usage_snapshots (id, balance, rate_per_hour, read_at) VALUES (1, ?, ?, ?)",
            (balance, rate_per_hour, read_at),
        )
