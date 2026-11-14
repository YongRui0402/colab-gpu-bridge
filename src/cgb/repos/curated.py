"""`curated_models` 表的存取(contracts/store.dbml § Table curated_models)。"""

import sqlite3
from typing import Any

from cgb.domain.model_name import match_key


class CuratedDuplicate(Exception):
    """精選清單已有同一個名稱(補過版本後不分大小寫相同);`existing` 是清單裡已有的那一個名稱。"""

    def __init__(self, existing: str) -> None:
        super().__init__(existing)
        self.existing = existing


def _runtime_type_columns(runtime_type: dict[str, Any] | None) -> tuple[str | None, int | None]:
    """`RuntimeType` 攤成兩個欄位;沒有建議類型時兩個都是 NULL。"""
    if runtime_type is None:
        return None, None
    return runtime_type["gpu"], int(runtime_type["highMem"])


class CuratedRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        *,
        name: str,
        description: str | None,
        runtime_type: dict[str, Any] | None = None,
        auto_download: bool = False,
    ) -> int:
        gpu, high_mem = _runtime_type_columns(runtime_type)
        for row in self.all():
            if match_key(row["name"]) == match_key(name):
                raise CuratedDuplicate(row["name"])
        try:
            cursor = self._conn.execute(
                "INSERT INTO curated_models"
                " (name, description, recommended_runtime_type_gpu, recommended_runtime_type_high_mem, auto_download)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, description, gpu, high_mem, int(auto_download)),
            )
        except sqlite3.IntegrityError as error:
            # 寫入本身就是檢查:name 的 unique 擋下重複
            raise CuratedDuplicate(name) from error
        return int(cursor.lastrowid)

    def update(
        self,
        curated_id: int,
        *,
        name: str,
        description: str | None,
        runtime_type: dict[str, Any] | None = None,
        auto_download: bool = False,
    ) -> bool:
        """整筆取代;回傳有沒有這一筆。改成的名稱和另一筆(不含自己)重複時丟 `CuratedDuplicate`。"""
        if self.get(curated_id) is None:
            return False
        gpu, high_mem = _runtime_type_columns(runtime_type)
        for row in self.all():
            if row["id"] != curated_id and match_key(row["name"]) == match_key(name):
                raise CuratedDuplicate(row["name"])
        cursor = self._conn.execute(
            "UPDATE curated_models SET name = ?, description = ?,"
            " recommended_runtime_type_gpu = ?, recommended_runtime_type_high_mem = ?, auto_download = ? WHERE id = ?",
            (name, description, gpu, high_mem, int(auto_download), curated_id),
        )
        return cursor.rowcount == 1

    def delete(self, curated_id: int) -> bool:
        """回傳有沒有刪到。"""
        return self._conn.execute("DELETE FROM curated_models WHERE id = ?", (curated_id,)).rowcount == 1

    def get(self, curated_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM curated_models WHERE id = ?", (curated_id,)).fetchone()
        return dict(row) if row is not None else None

    def all(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._conn.execute("SELECT * FROM curated_models ORDER BY id")]
