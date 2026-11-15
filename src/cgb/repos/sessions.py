"""`sessions` 表的存取(contracts/store.dbml § Table sessions)。"""

import sqlite3
from collections.abc import Callable
from typing import Any


class ActiveSessionExists(Exception):
    """`active_slot` 已被占用:已有開啟中、就緒或重連中的工作階段(FR-006)。"""


class SessionsRepo:
    def __init__(self, conn: sqlite3.Connection, now: Callable[[], str]) -> None:
        """`now` 回傳現在的 ISO 8601 UTC 字串(注入的時鐘),狀態變化的時間用它。"""
        self._conn = conn
        self._now = now
        # 每次寫入之後呼叫(推送 session.updated 用)
        self.listeners: list[Callable[[], None]] = []
        # 不是本系統開的執行環境(spec 邊界情況):只活在這次執行之中,不存表(store.dbml 的說明)
        self.unmanaged_runtimes: list[dict[str, Any]] = []

    def insert_opening(self, *, name: str, gpu: str, high_mem: bool, opened_at: str, step: str) -> None:
        try:
            self._conn.execute(
                "INSERT INTO sessions (name, runtime_type_gpu, runtime_type_high_mem, state, active_slot, step, opened_at)"
                " VALUES (?, ?, ?, 'opening', 1, ?, ?)",
                (name, gpu, int(high_mem), step, opened_at),
            )
        except sqlite3.IntegrityError as error:
            if "active_slot" in str(error):
                raise ActiveSessionExists from error
            raise
        self._record_transition(name)
        self._changed()

    def update(self, name: str, **fields: Any) -> None:
        before = self.get(name)
        columns = ", ".join(f"{column} = ?" for column in fields)
        self._conn.execute(f"UPDATE sessions SET {columns} WHERE name = ?", (*fields.values(), name))
        after = self.get(name)
        # FR-028:狀態或開啟的步驟有變化就記一筆
        if before is not None and after is not None and (before["state"], before["step"]) != (after["state"], after["step"]):
            self._record_transition(name)
        if before != after:
            self._changed()

    def notify(self) -> None:
        """`sessions` 沒有變、但從它推出的 `Session`(例如 `ollama.lastApply`)變了時,通知一次(推送 session.updated 用)。"""
        self._changed()

    def _changed(self) -> None:
        for listener in list(self.listeners):
            listener()

    def _record_transition(self, name: str) -> None:
        self._conn.execute(
            "INSERT INTO session_transitions (session_name, at, state, step, end_reason, reason_code)"
            " SELECT name, ?, state, step, end_reason, reason_code FROM sessions WHERE name = ?",
            (self._now(), name),
        )

    def transitions(self, name: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM session_transitions WHERE session_name = ? ORDER BY at, id", (name,)
        ).fetchall()
        return [dict(row) for row in rows]

    def latest(self) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM sessions ORDER BY opened_at DESC, rowid DESC LIMIT 1").fetchone()
        return dict(row) if row is not None else None

    def latest_unfinished(self) -> dict[str, Any] | None:
        """後端啟動時找最後一筆未結束的工作階段(research.md R10)。"""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE state IN ('opening', 'ready', 'applying_tuning', 'reconnecting')"
            " ORDER BY opened_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row is not None else None

    def get(self, name: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM sessions WHERE name = ?", (name,)).fetchone()
        return dict(row) if row is not None else None

    def history(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM sessions ORDER BY opened_at DESC, rowid DESC").fetchall()
        return [dict(row) for row in rows]
