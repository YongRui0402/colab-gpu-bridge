"""`curated_models` 表的存取(contracts/store.dbml § Table curated_models)。"""

import sqlite3
from typing import Any


class CuratedDuplicate(Exception):
    """精選清單已有同一個名稱(含版本)。"""


class CuratedRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, *, name: str, description: str | None, auto_download: bool = False) -> int:
        try:
            cursor = self._conn.execute(
                "INSERT INTO curated_models (name, description, auto_download) VALUES (?, ?, ?)",
                (name, description, int(auto_download)),
            )
        except sqlite3.IntegrityError as error:
            # 寫入本身就是檢查:name 的 unique 擋下重複
            raise CuratedDuplicate from error
        return int(cursor.lastrowid)

    def update(self, curated_id: int, *, name: str, description: str | None, auto_download: bool = False) -> None:
        self._conn.execute(
            "UPDATE curated_models SET name = ?, description = ?, auto_download = ? WHERE id = ?",
            (name, description, int(auto_download), curated_id),
        )

    def delete(self, curated_id: int) -> None:
        self._conn.execute("DELETE FROM curated_models WHERE id = ?", (curated_id,))

    def get(self, curated_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM curated_models WHERE id = ?", (curated_id,)).fetchone()
        return dict(row) if row is not None else None

    def all(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._conn.execute("SELECT * FROM curated_models ORDER BY id")]
