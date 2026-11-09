"""E4 資料庫(SQLite)(testplan.md § 2.5;contracts/store.dbml)。

接縫:`db` 模組建立的 schema,以 sqlite3 直接下 SQL(plan.md Q98)。
"""

import sqlite3
from pathlib import Path

import pytest

from cgb.db.connection import connect
from cgb.db.schema import create_schema


def _insert_session(conn: sqlite3.Connection, name: str, state: str, active_slot: int | None) -> None:
    conn.execute(
        "INSERT INTO sessions (name, runtime_type_gpu, runtime_type_high_mem, state, active_slot, opened_at)"
        " VALUES (?, 'T4', 0, ?, ?, '2026-11-09T08:30:00Z')",
        (name, state, active_slot),
    )


# ---------------------------------------------------------------- US1-DB-01


def test_同一時間只寫得進一個開啟中的工作階段_結束中的不占位(tmp_path: Path) -> None:
    # Arrange:已有一筆 active_slot=1 的 ready
    conn = connect(tmp_path / "cgb.sqlite3")
    create_schema(conn)
    _insert_session(conn, "cgb-ready", "ready", 1)

    # Act & Assert:則1 第二筆 active_slot=1 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_session(conn, "cgb-second", "opening", 1)

    # Act & Assert:則2 active_slot 為 null 的 ending 寫得進去
    try:
        _insert_session(conn, "cgb-ending", "ending", None)
    except sqlite3.IntegrityError as exc:
        pytest.fail(f"active_slot 為 null 的 ending 應寫得進去:{exc}")
    names = [row[0] for row in conn.execute("SELECT name FROM sessions ORDER BY name")]
    assert names == ["cgb-ending", "cgb-ready"]
    conn.close()


# ---------------------------------------------------------------- US1-DB-02


def test_重新開啟資料庫後仍是_WAL_且狀態變化紀錄都還在(tmp_path: Path) -> None:
    # Arrange:寫入一筆 sessions 與三筆 session_transitions
    db_path = tmp_path / "cgb.sqlite3"
    conn = connect(db_path)
    create_schema(conn)
    _insert_session(conn, "cgb-ready", "ready", 1)
    transitions = [
        ("2026-11-09T08:30:00Z", "opening", "allocating", None, None),
        ("2026-11-09T08:31:00Z", "opening", "connecting", None, None),
        ("2026-11-09T08:32:00Z", "ready", None, None, None),
    ]
    for at, state, step, end_reason, reason_code in reversed(transitions):
        conn.execute(
            "INSERT INTO session_transitions (session_name, at, state, step, end_reason, reason_code)"
            " VALUES ('cgb-ready', ?, ?, ?, ?, ?)",
            (at, state, step, end_reason, reason_code),
        )

    # Act:關閉連線,以新的連線開同一個檔
    conn.close()
    reopened = sqlite3.connect(db_path)

    # Assert
    journal_mode = reopened.execute("PRAGMA journal_mode").fetchone()[0]
    rows = reopened.execute(
        "SELECT at, state, step, end_reason, reason_code FROM session_transitions"
        " WHERE session_name = 'cgb-ready' ORDER BY at"
    ).fetchall()
    reopened.close()
    assert journal_mode == "wal"
    assert rows == transitions
