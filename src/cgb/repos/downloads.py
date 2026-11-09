"""`download_jobs` 表的存取(contracts/store.dbml § Table download_jobs)。"""

import sqlite3
from typing import Any


class DownloadsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def enqueue(self, *, model: str, size_bytes: int, origin: str, preload_on_complete: bool, added_at: str) -> int:
        cursor = self._conn.execute(
            "INSERT INTO download_jobs (model, pending_model, queue_position, size_bytes, state, origin,"
            " preload_on_complete, added_at)"
            " VALUES (?, ?, (SELECT COALESCE(MAX(queue_position), 0) + 1 FROM download_jobs), ?, 'queued', ?, ?, ?)",
            (model, model, size_bytes, origin, int(preload_on_complete), added_at),
        )
        return int(cursor.lastrowid)

    def get(self, job_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM download_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def update(self, job_id: int, **fields: Any) -> None:
        columns = ", ".join(f"{column} = ?" for column in fields)
        self._conn.execute(f"UPDATE download_jobs SET {columns} WHERE id = ?", (*fields.values(), job_id))

    def all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM download_jobs ORDER BY queue_position").fetchall()
        return [dict(row) for row in rows]

    def next_queued(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM download_jobs WHERE state = 'queued' ORDER BY queue_position LIMIT 1"
        ).fetchone()
        return dict(row) if row is not None else None

    def delete(self, job_id: int) -> None:
        self._conn.execute("DELETE FROM download_jobs WHERE id = ?", (job_id,))

    def requeue(self, job_id: int) -> None:
        """重新排到佇列最後:queue_position 改成目前最大值 + 1,狀態回到排隊中(store.dbml)。"""
        self._conn.execute(
            "UPDATE download_jobs SET state = 'queued', pending_model = model,"
            " queue_position = (SELECT MAX(queue_position) + 1 FROM download_jobs),"
            " reason_code = NULL, message = NULL, started_at = NULL, finished_at = NULL WHERE id = ?",
            (job_id,),
        )

    def delete_completed(self) -> list[int]:
        ids = [row[0] for row in self._conn.execute("SELECT id FROM download_jobs WHERE state = 'completed' ORDER BY queue_position")]
        self._conn.execute("DELETE FROM download_jobs WHERE state = 'completed'")
        return ids

    def requeue_interrupted(self) -> None:
        """上一個行程留下的 `downloading` 回到排隊中,順序不變(後端重新啟動,FR-021)。"""
        self._conn.execute("UPDATE download_jobs SET state = 'queued', started_at = NULL WHERE state = 'downloading'")
