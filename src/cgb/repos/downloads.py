"""`download_jobs` 表的存取(contracts/store.dbml § Table download_jobs)。"""

import sqlite3
from typing import Any


class DownloadsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def enqueue(self, *, model: str, size_bytes: int, origin: str, preload_on_complete: bool, added_at: str) -> None:
        self._conn.execute(
            "INSERT INTO download_jobs (model, pending_model, queue_position, size_bytes, state, origin,"
            " preload_on_complete, added_at)"
            " VALUES (?, ?, (SELECT COALESCE(MAX(queue_position), 0) + 1 FROM download_jobs), ?, 'queued', ?, ?, ?)",
            (model, model, size_bytes, origin, int(preload_on_complete), added_at),
        )

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
