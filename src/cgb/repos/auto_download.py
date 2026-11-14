"""`auto_download_results`、`auto_download_items` 表的存取(contracts/store.dbml)。"""

import sqlite3
from typing import Any


class AutoDownloadRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def start(self, session_name: str, target_count: int) -> bool:
        """記下這個工作階段做過第一次判定(state 為 running);已經有這一列時回 False(同一個工作階段只做一次)。"""
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO auto_download_results (session_name, target_count) VALUES (?, ?)",
            (session_name, target_count),
        )
        return cursor.rowcount == 1

    def finish(self, session_name: str, finished_at: str) -> None:
        self._conn.execute(
            "UPDATE auto_download_results SET state = 'done', finished_at = ? WHERE session_name = ?",
            (finished_at, session_name),
        )

    def add_item(
        self,
        session_name: str,
        position: int,
        model: str,
        *,
        reason: str | None = None,
        reason_code: str | None = None,
        message: str | None = None,
        size_bytes: int | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO auto_download_items (session_name, position, model, reason, reason_code, message, size_bytes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_name, position, model, reason, reason_code, message, size_bytes),
        )

    def get(self, session_name: str) -> dict[str, Any] | None:
        """對外的結果(`AutoDownloadResult`);沒有這一列,或沒有設自動下載的項目(`target_count` 為 0)時是 None。"""
        row = self._conn.execute(
            "SELECT * FROM auto_download_results WHERE session_name = ? AND target_count > 0", (session_name,)
        ).fetchone()
        if row is None:
            return None
        items = self._conn.execute(
            "SELECT * FROM auto_download_items WHERE session_name = ? ORDER BY position", (session_name,)
        ).fetchall()
        return {
            "sessionName": row["session_name"],
            "state": row["state"],
            "enqueued": [item["model"] for item in items if item["reason"] is None],
            "skipped": [
                {
                    "model": item["model"],
                    "reason": item["reason"],
                    "reasonCode": item["reason_code"],
                    "message": item["message"],
                    "sizeBytes": item["size_bytes"],
                    "freeDiskBytes": item["free_disk_bytes"],
                    "vramBytes": item["vram_bytes"],
                }
                for item in items
                if item["reason"] is not None
            ],
            "dismissed": bool(row["dismissed"]),
            "finishedAt": row["finished_at"],
        }

    def delete(self, session_name: str) -> bool:
        """移除這個工作階段的結果與它的每一項;回傳先前有沒有對外的結果(`get` 不是 None)。"""
        visible = self.get(session_name) is not None
        self._conn.execute("DELETE FROM auto_download_items WHERE session_name = ?", (session_name,))
        self._conn.execute("DELETE FROM auto_download_results WHERE session_name = ?", (session_name,))
        return visible
