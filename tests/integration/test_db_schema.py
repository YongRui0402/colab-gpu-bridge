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


def _insert_job(conn: sqlite3.Connection, model: str, pending_model: str | None, queue_position: int, state: str) -> None:
    conn.execute(
        "INSERT INTO download_jobs (model, pending_model, queue_position, size_bytes, state, added_at)"
        " VALUES (?, ?, ?, 0, ?, '2026-11-09T09:00:00Z')",
        (model, pending_model, queue_position, state),
    )


# ---------------------------------------------------------------- US3-DB-01


def test_同一個模型不會同時排兩次_完成過的可以再下載_精選清單名稱不重複(tmp_path: Path) -> None:
    # Arrange:已有一筆 pending_model='qwen2.5:7b'、queue_position=1
    conn = connect(tmp_path / "cgb.sqlite3")
    create_schema(conn)
    _insert_job(conn, "qwen2.5:7b", "qwen2.5:7b", 1, "queued")

    # Act & Assert:則1 重複的 pending_model 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "qwen2.5:7b", "qwen2.5:7b", 2, "queued")

    # Act & Assert:則2 重複的 queue_position 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "qwen2.5:0.5b", "qwen2.5:0.5b", 1, "queued")

    # Act & Assert:則3 兩筆 pending_model 為 null 的已完成項目都寫得進去
    try:
        _insert_job(conn, "qwen2.5:7b", None, 3, "completed")
        _insert_job(conn, "qwen2.5:7b", None, 4, "completed")
    except sqlite3.IntegrityError as exc:
        pytest.fail(f"pending_model 為 null 的已完成項目應寫得進去:{exc}")

    # Act & Assert:則4 curated_models 第二筆同名的寫不進去
    conn.execute("INSERT INTO curated_models (name) VALUES ('qwen2.5:latest')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO curated_models (name) VALUES ('qwen2.5:latest')")
    conn.close()


# ---------------------------------------------------------------- US4-DB-01


def _settings_rows(conn: sqlite3.Connection) -> list[tuple[int, int, float]]:
    return [tuple(row) for row in conn.execute("SELECT id, idle_timeout_minutes, low_balance_threshold FROM settings")]


def test_第一次啟動寫入預設設定_之後啟動不覆寫使用者改過的值(tmp_path: Path) -> None:
    # Arrange:第一次啟動
    conn = connect(tmp_path / "cgb.sqlite3")
    create_schema(conn)

    # Act
    first = _settings_rows(conn)
    conn.execute("UPDATE settings SET idle_timeout_minutes = 10 WHERE id = 1")
    create_schema(conn)  # 第二次啟動
    second = _settings_rows(conn)
    conn.close()

    # Assert:則1 第一次讀到 1 列預設值
    assert first == [(1, 30, 10)]
    # Assert:則2、則3 第二次啟動後仍只有 1 列,且保留使用者改過的值
    assert second == [(1, 10, 10)]


# ---------------------------------------------------------------- US4-DB-02


def test_用量快照只留最後一筆_重新開啟後讀得到(tmp_path: Path) -> None:
    # Arrange
    db_path = tmp_path / "cgb.sqlite3"
    conn = connect(db_path)
    create_schema(conn)

    # Act:寫入兩次用量(id 不指定,沿用 schema 的預設),關閉後重新開啟
    for balance, rate, read_at in ((381.66, 1.15, "2026-11-10T08:00:00Z"), (380.00, 1.15, "2026-11-10T08:05:00Z")):
        conn.execute(
            "INSERT OR REPLACE INTO usage_snapshots (balance, rate_per_hour, read_at) VALUES (?, ?, ?)",
            (balance, rate, read_at),
        )
    conn.close()
    reopened = connect(db_path)
    rows = [tuple(row) for row in reopened.execute("SELECT id, balance, read_at FROM usage_snapshots")]
    reopened.close()

    # Assert:則1 只有 1 列且 id 為 1;則2 是最後一次寫入的值
    assert rows == [(1, 380.00, "2026-11-10T08:05:00Z")]
