"""E4 資料庫(SQLite)(testplan.md § 2.5;contracts/store.dbml)。

接縫:`db` 模組建立的 schema,以 sqlite3 直接下 SQL(plan.md Q98)。
"""

import logging
import sqlite3
from pathlib import Path

import pytest

from cgb.db.connection import connect
from cgb.db.schema import create_schema


def _insert_session(
    conn: sqlite3.Connection,
    name: str,
    state: str,
    active_slot: int | None,
    *,
    runtime_type_gpu: str = "T4",
    runtime_type_high_mem: int = 0,
    step: str | None = None,
    end_reason: str | None = None,
    reason_code: str | None = None,
    message: str | None = None,
    opened_at: str = "2026-11-09T08:30:00Z",
    ready_at: str | None = None,
    ended_at: str | None = None,
    last_request_at: str | None = None,
    reconnect_started_at: str | None = None,
    reconnect_deadline: str | None = None,
    release_warning_reason_code: str | None = None,
    release_warning_message: str | None = None,
    release_warning_detected_at: str | None = None,
) -> None:
    """以 001 的 18 個欄位寫入一筆工作階段;舊庫(v0、v1)與新庫都寫得進去。"""
    columns = {
        "name": name,
        "runtime_type_gpu": runtime_type_gpu,
        "runtime_type_high_mem": runtime_type_high_mem,
        "state": state,
        "active_slot": active_slot,
        "step": step,
        "end_reason": end_reason,
        "reason_code": reason_code,
        "message": message,
        "opened_at": opened_at,
        "ready_at": ready_at,
        "ended_at": ended_at,
        "last_request_at": last_request_at,
        "reconnect_started_at": reconnect_started_at,
        "reconnect_deadline": reconnect_deadline,
        "release_warning_reason_code": release_warning_reason_code,
        "release_warning_message": release_warning_message,
        "release_warning_detected_at": release_warning_detected_at,
    }
    conn.execute(
        f"INSERT INTO sessions ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        tuple(columns.values()),
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


def _insert_job(
    conn: sqlite3.Connection,
    model: str,
    pending_model: str | None,
    queue_position: int,
    state: str,
    *,
    size_bytes: int = 0,
    session_name: str | None = None,
    origin: str = "user",
    preload_on_complete: int = 0,
    reason_code: str | None = None,
    message: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    columns = {
        "model": model,
        "pending_model": pending_model,
        "queue_position": queue_position,
        "size_bytes": size_bytes,
        "state": state,
        "reason_code": reason_code,
        "message": message,
        "origin": origin,
        "preload_on_complete": preload_on_complete,
        "added_at": "2026-11-09T09:00:00Z",
        "started_at": started_at,
        "finished_at": finished_at,
    }
    # 舊庫(001)沒有 session_name 欄位,沒指定時不寫這一欄,讓同一個 helper 寫舊庫和新庫
    if session_name is not None:
        columns["session_name"] = session_name
    conn.execute(
        f"INSERT INTO download_jobs ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        tuple(columns.values()),
    )


_SCHEMA_V0 = Path(__file__).parent.parent / "fixtures" / "db" / "schema_v0.sql"


def _build_v0(db_path: Path) -> sqlite3.Connection:
    """以凍結的 001 DDL 建出舊庫,`user_version` 保持 0(plan.md Q37)。"""
    conn = connect(db_path)
    conn.executescript(_SCHEMA_V0.read_text(encoding="utf-8"))
    return conn


# ---- 004 US1-DB-01


def test_全新資料庫建出_user_version_為_2_且_download_jobs_有所屬工作階段與不分大小寫的唯一索引(tmp_path: Path) -> None:
    # Arrange:tmp_path 裡還沒有資料庫檔
    conn = connect(tmp_path / "cgb.sqlite3")

    # Act
    create_schema(conn)

    # Assert:則1 user_version 為 2(005 起全新庫直接建到第 2 版,plan.md Q41)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則2 session_name 為可為 NULL 的 TEXT
    session_name = [row for row in conn.execute("PRAGMA table_info(download_jobs)") if row["name"] == "session_name"]
    assert [(row["type"], row["notnull"]) for row in session_name] == [("TEXT", 0)]
    # Assert:則3 兩個一般索引與不分大小寫的唯一索引
    indexes = {row["name"]: row["unique"] for row in conn.execute("PRAGMA index_list(download_jobs)")}
    assert indexes["idx_download_jobs_state"] == 0
    assert indexes["idx_download_jobs_session"] == 0
    assert indexes["uq_download_jobs_pending_model_ci"] == 1
    # Assert:則4 只有一個外鍵,指向 sessions(name),刪除時 cascade
    foreign_keys = [
        (row["table"], row["from"], row["to"], row["on_delete"]) for row in conn.execute("PRAGMA foreign_key_list(download_jobs)")
    ]
    assert foreign_keys == [("sessions", "session_name", "name", "CASCADE")]
    # Assert:則5 沒有開 foreign_keys(Q27)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    conn.close()


# ---- 004 US1-DB-02


def test_全新資料庫的下載項目可寫入自動下載來源_大小寫只差的排隊項目寫不進去(tmp_path: Path) -> None:
    # Arrange:全新庫有 cgb-a(ready),download_jobs 已有一筆屬於 cgb-a 的 qwen2.5:7b 排隊中
    conn = connect(tmp_path / "cgb.sqlite3")
    create_schema(conn)
    _insert_session(conn, "cgb-a", "ready", 1)
    _insert_job(conn, "qwen2.5:7b", "qwen2.5:7b", 1, "queued", session_name="cgb-a")

    # Act & Assert:則1 origin 為 auto 的項目寫得進去,讀回 origin 與 session_name
    _insert_job(conn, "llama3.2:3b", "llama3.2:3b", 2, "queued", session_name="cgb-a", origin="auto")
    row = conn.execute("SELECT origin, session_name FROM download_jobs WHERE queue_position = 2").fetchone()
    assert (row["origin"], row["session_name"]) == ("auto", "cgb-a")

    # Act & Assert:則2 不在 origin 清單裡的 manual 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "gemma3:1b", "gemma3:1b", 3, "queued", origin="manual")

    # Act & Assert:則3 pending_model 只差大小寫的排隊項目寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "Qwen2.5:7B", "Qwen2.5:7B", 4, "queued")

    # Act & Assert:則4 pending_model 為 NULL 的兩筆已完成項目都寫得進去
    try:
        _insert_job(conn, "qwen2.5:7b", None, 5, "completed")
        _insert_job(conn, "qwen2.5:7b", None, 6, "completed")
    except sqlite3.IntegrityError as exc:
        pytest.fail(f"pending_model 為 null 的已完成項目應寫得進去:{exc}")
    conn.close()


# 「13 個舊欄位」:001 的 download_jobs 欄位,依順序(testplan.md § 2.2)
_LEGACY_COLUMNS = (
    "id, model, pending_model, queue_position, size_bytes, state, reason_code, message,"
    " origin, preload_on_complete, added_at, started_at, finished_at"
)

# 「舊庫三筆」:A 排隊中、B 完成(restore)、C 失敗
_LEGACY_JOBS = [
    (1, "qwen2.5:7b", "qwen2.5:7b", 1, 4683087332, "queued", None, None, "user", 0, "2026-11-01T08:00:00Z", None, None),
    (
        2, "llama3.2:3b", None, 2, 2019393189, "completed", None, None, "restore", 1,
        "2026-11-01T08:01:00Z", "2026-11-01T08:02:00Z", "2026-11-01T08:05:00Z",
    ),
    (
        3, "gemma3:1b", None, 3, 815319791, "failed", "SESSION_ENDED", "工作階段已結束", "user", 0,
        "2026-11-01T08:03:00Z", "2026-11-01T08:04:00Z", "2026-11-01T08:06:00Z",
    ),
]  # fmt: skip


def _insert_legacy_jobs(conn: sqlite3.Connection, jobs: list[tuple] = _LEGACY_JOBS) -> None:
    """以舊版欄位寫入 `cgb-old`(ended)與下載項目,舊庫沒有 session_name,所以逐欄明寫。"""
    conn.execute(
        "INSERT INTO sessions (name, runtime_type_gpu, runtime_type_high_mem, state, active_slot, opened_at)"
        " VALUES ('cgb-old', 'T4', 0, 'ended', NULL, '2026-11-01T07:00:00Z')"
    )
    conn.executemany(f"INSERT INTO download_jobs ({_LEGACY_COLUMNS}) VALUES ({', '.join('?' * 13)})", jobs)


def _legacy_job_rows(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(row) for row in conn.execute(f"SELECT {_LEGACY_COLUMNS} FROM download_jobs ORDER BY id")]


def _download_jobs_columns(conn: sqlite3.Connection) -> list[tuple]:
    return [
        (row["name"], row["type"], row["notnull"], row["dflt_value"], row["pk"])
        for row in conn.execute("PRAGMA table_info(download_jobs)")
    ]


# ---- 004 US1-DB-03


def test_舊資料庫升級後保留三筆舊項目且下載項目表與全新庫一致(tmp_path: Path) -> None:
    # Arrange:舊庫寫入舊庫三筆;另建一個全新庫當對照
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    _insert_legacy_jobs(old)
    old.close()
    fresh = connect(tmp_path / "fresh.sqlite3")
    create_schema(fresh)

    # Act:以新的連線開同一個檔
    conn = connect(db_path)
    error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        error = exc

    # Assert:則1 沒有丟出例外
    assert error is None
    # Assert:則2 user_version 為 2(005 起 0 → 1 之後接著做 1 → 2,plan.md Q41)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則3 13 個舊欄位三筆都和寫入的相同;則4 三筆的 session_name 都是 NULL
    assert _legacy_job_rows(conn) == _LEGACY_JOBS
    assert [row[0] for row in conn.execute("SELECT session_name FROM download_jobs ORDER BY id")] == [None] * 3
    # Assert:則5 沒有留下重建用的暫存表
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'download_jobs_new'").fetchall() == []
    # Assert:則6 索引
    indexes = {row["name"]: row["unique"] for row in conn.execute("PRAGMA index_list(download_jobs)")}
    assert indexes["idx_download_jobs_state"] == 0
    assert indexes["idx_download_jobs_session"] == 0
    assert indexes["uq_download_jobs_pending_model_ci"] == 1
    # Assert:則7 外鍵
    foreign_keys = [
        (row["table"], row["from"], row["to"], row["on_delete"]) for row in conn.execute("PRAGMA foreign_key_list(download_jobs)")
    ]
    assert foreign_keys == [("sessions", "session_name", "name", "CASCADE")]
    # Assert:則8 每一欄的定義依序和全新庫的相同
    assert _download_jobs_columns(conn) == _download_jobs_columns(fresh)
    conn.close()
    fresh.close()


# ---- 004 US1-DB-04


def test_升級後的資料庫寫得進自動下載來源_大小寫只差_重複位置_負的大小_manual_都寫不進去(tmp_path: Path) -> None:
    # Arrange:舊庫寫入舊庫三筆後升級,另插入 cgb-new(ready)
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    _insert_legacy_jobs(old)
    old.close()
    conn = connect(db_path)
    create_schema(conn)
    _insert_session(conn, "cgb-new", "ready", 1)

    # Act & Assert:則1 origin 為 auto 的項目寫得進去
    _insert_job(conn, "phi4:14b", "phi4:14b", 4, "queued", session_name="cgb-new", origin="auto")
    assert conn.execute("SELECT origin FROM download_jobs WHERE queue_position = 4").fetchone()["origin"] == "auto"

    # Act & Assert:則2 和 A(qwen2.5:7b)只差大小寫的 pending_model 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "Qwen2.5:7B", "Qwen2.5:7B", 5, "queued")

    # Act & Assert:則3 origin 為 manual 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "gemma3:4b", "gemma3:4b", 6, "queued", origin="manual")

    # Act & Assert:則4 和 A 相同的 queue_position 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "mistral:7b", "mistral:7b", 1, "queued")

    # Act & Assert:則5 負的 size_bytes 寫不進去
    with pytest.raises(sqlite3.IntegrityError):
        _insert_job(conn, "gemma3:12b", "gemma3:12b", 7, "queued", size_bytes=-1)
    conn.close()


def _deny_setting_user_version(action: int, arg1: str | None, arg2: str | None, *_: object) -> int:
    """遷移的最後一步是設定 user_version;只在「設定」時(arg2 有值)拒絕,讀取照常(testplan.md § 2.2)。"""
    if action == sqlite3.SQLITE_PRAGMA and arg1 == "user_version" and arg2 is not None:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _sqlite_master_names(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("SELECT name FROM sqlite_master")}


# ---- 004 US1-DB-05


def test_遷移中途失敗時整個還原_原例外往上丟_下次啟動可再升級(tmp_path: Path) -> None:
    # Arrange:舊庫寫入舊庫三筆與一筆精選;開檔後拒絕設定 user_version
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    _insert_legacy_jobs(old)
    old.execute("INSERT INTO curated_models (name) VALUES ('qwen2.5:latest')")
    old.close()
    conn = connect(db_path)
    conn.set_authorizer(_deny_setting_user_version)

    # Act:第一次呼叫
    error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001 - 要確認丟出的是 sqlite3.DatabaseError
        error = exc

    # Assert:則1 丟出 sqlite3.DatabaseError(含子類)
    assert isinstance(error, sqlite3.DatabaseError)
    # Assert:則2 user_version 仍是 0
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    # Assert:則3 download_jobs 沒有 session_name;則4 13 個舊欄位三筆都和寫入的相同
    assert "session_name" not in [row["name"] for row in conn.execute("PRAGMA table_info(download_jobs)")]
    assert _legacy_job_rows(conn) == _LEGACY_JOBS
    # Assert:則5 沒有留下 download_jobs_new 與新索引;則6 舊的 idx_download_jobs_state 仍在
    names = _sqlite_master_names(conn)
    assert names.isdisjoint({"download_jobs_new", "idx_download_jobs_session", "uq_download_jobs_pending_model_ci"})
    assert "idx_download_jobs_state" in names
    # Assert:則7 curated_models 也沒被改
    assert "auto_download" not in [row["name"] for row in conn.execute("PRAGMA table_info(curated_models)")]

    # Act:放行後第二次呼叫
    conn.set_authorizer(None)
    retry_error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001
        retry_error = exc

    # Assert:則8 第二次沒有丟出例外,之後 user_version 為 2(005 起 0 → 1 之後接著做 1 → 2,plan.md Q41)
    assert retry_error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


# ---- 004 US1-DB-06


def test_升級過的資料庫再啟動一次不重跑遷移_項目的所屬工作階段不變(tmp_path: Path) -> None:
    # Arrange:舊庫寫入舊庫三筆後升級;另插入 cgb-new 與屬於它的自動下載項目 D
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    _insert_legacy_jobs(old)
    old.close()
    conn = connect(db_path)
    create_schema(conn)
    _insert_session(conn, "cgb-new", "ready", 1)
    _insert_job(conn, "phi4:14b", "phi4:14b", 4, "queued", session_name="cgb-new", origin="auto")

    # Act:再呼叫一次(模擬後端重新啟動)
    error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        error = exc

    # Assert:則1 沒有丟出例外;則2 user_version 為 2(005 起第二次啟動接著做 1 → 2,plan.md Q41)
    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則3 D 的 session_name 仍是 cgb-new;則4 download_jobs 有 4 筆
    assert conn.execute("SELECT session_name FROM download_jobs WHERE queue_position = 4").fetchone()[0] == "cgb-new"
    assert conn.execute("SELECT count(*) FROM download_jobs").fetchone()[0] == 4
    conn.close()


# ---- 004 US1-DB-07


def test_從沒開過工作階段的舊資料庫也升級_sessions_表在就是舊庫(tmp_path: Path) -> None:
    # Arrange:舊庫不寫任何資料列(sessions 表存在、0 筆)
    db_path = tmp_path / "cgb.sqlite3"
    _build_v0(db_path).close()
    conn = connect(db_path)

    # Act
    create_schema(conn)

    # Assert:則1 user_version 為 2(005 起 0 → 1 之後接著做 1 → 2,plan.md Q41);則2 download_jobs 有 session_name
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert "session_name" in [row["name"] for row in conn.execute("PRAGMA table_info(download_jobs)")]
    conn.close()


# ---- 004 US1-DB-08


def test_舊資料庫有只差大小寫的排隊項目時留_id_最小的並把刪掉的名稱寫進日誌(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Arrange:舊庫 download_jobs 三筆,id 1、2 的 pending_model 只差大小寫,id 3 已完成(pending_model 為 NULL)
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    jobs = [
        (1, "Qwen2.5:7b", "Qwen2.5:7b", 1, 0, "queued", None, None, "user", 0, "2026-11-01T08:00:00Z", None, None),
        (2, "qwen2.5:7b", "qwen2.5:7b", 2, 0, "queued", None, None, "user", 0, "2026-11-01T08:01:00Z", None, None),
        (
            3, "qwen2.5:7b", None, 3, 0, "completed", None, None, "user", 0,
            "2026-11-01T08:02:00Z", "2026-11-01T08:03:00Z", "2026-11-01T08:04:00Z",
        ),
    ]  # fmt: skip
    _insert_legacy_jobs(old, jobs)
    old.close()
    conn = connect(db_path)
    caplog.set_level(logging.INFO)

    # Act
    error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        error = exc

    # Assert:則1 沒有丟出例外
    assert error is None
    # Assert:則2 留下 id 1、3(id 2 被刪);則3 id 1 的 pending_model 仍是 Qwen2.5:7b
    rows = [(row["id"], row["pending_model"]) for row in conn.execute("SELECT id, pending_model FROM download_jobs ORDER BY id")]
    assert rows == [(1, "Qwen2.5:7b"), (3, None)]
    # Assert:則4 不分大小寫的唯一索引建起來了
    indexes = {row["name"]: row["unique"] for row in conn.execute("PRAGMA index_list(download_jobs)")}
    assert indexes["uq_download_jobs_pending_model_ci"] == 1
    # Assert:則5 日誌有一筆含被刪那一筆的名稱;則6 user_version 為 2(005 起 0 → 1 之後接著做 1 → 2,plan.md Q41)
    assert any("qwen2.5:7b" in record.getMessage() for record in caplog.records)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


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


# ---- 004 US3-DB-01


def test_全新資料庫的精選項目有自動下載欄_且有自動下載結果表_結果項目表與不分大小寫的名稱唯一索引(tmp_path: Path) -> None:
    # Arrange:tmp_path 裡還沒有資料庫檔
    conn = connect(tmp_path / "cgb.sqlite3")

    # Act
    create_schema(conn)

    # Assert:則1 curated_models 有 auto_download 欄,INTEGER、NOT NULL、預設 '0'
    auto_download = [
        (row["type"], row["notnull"], row["dflt_value"])
        for row in conn.execute("PRAGMA table_info(curated_models)")
        if row["name"] == "auto_download"
    ]
    assert auto_download == [("INTEGER", 1, "0")]
    # Assert:則2 auto_download_results 的欄名依序,主鍵只有 session_name
    results = [(row["name"], row["pk"]) for row in conn.execute("PRAGMA table_info(auto_download_results)")]
    assert results == [
        ("session_name", 1),
        ("target_count", 0),
        ("state", 0),
        ("dismissed", 0),
        ("finished_at", 0),
    ]
    # Assert:則3 auto_download_items 的欄名依序,主鍵依序是 session_name、position
    items = [(row["name"], row["pk"]) for row in conn.execute("PRAGMA table_info(auto_download_items)")]
    assert items == [
        ("session_name", 1),
        ("position", 2),
        ("model", 0),
        ("reason", 0),
        ("reason_code", 0),
        ("message", 0),
        ("size_bytes", 0),
        ("free_disk_bytes", 0),
        ("vram_bytes", 0),
    ]
    # Assert:則4 index_list(curated_models) 有唯一的 uq_curated_models_name_ci
    indexes = {row["name"]: row["unique"] for row in conn.execute("PRAGMA index_list(curated_models)")}
    assert indexes["uq_curated_models_name_ci"] == 1
    conn.close()


# ---- 004 US3-DB-02


def test_舊資料庫升級後精選項目的_id_與內容不變_自動下載都是否_刪過的_id_不重用(tmp_path: Path) -> None:
    # Arrange:舊庫依序寫入 4 筆精選,再刪掉 id 4
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    old.execute(
        "INSERT INTO curated_models (name, description, recommended_runtime_type_gpu, recommended_runtime_type_high_mem)"
        " VALUES ('llama3.2:3b', '平常用', 'T4', 0)"
    )
    old.execute(
        "INSERT INTO curated_models (name, recommended_runtime_type_gpu, recommended_runtime_type_high_mem)"
        " VALUES ('qwen2.5:14b', 'H100', 1)"
    )
    old.execute("INSERT INTO curated_models (name) VALUES ('gemma2:2b')")
    old.execute("INSERT INTO curated_models (name) VALUES ('phi3:mini')")
    old.execute("DELETE FROM curated_models WHERE id = 4")
    old.close()
    conn = connect(db_path)

    # Act:升級後讀出精選清單,再寫入一筆新的
    create_schema(conn)
    read_error: sqlite3.Error | None = None
    rows: list[tuple] = []
    try:
        rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT id, name, description, recommended_runtime_type_gpu, recommended_runtime_type_high_mem,"
                " auto_download FROM curated_models ORDER BY id"
            )
        ]
    except sqlite3.Error as exc:
        read_error = exc
    conn.execute("INSERT INTO curated_models (name) VALUES ('mistral:7b')")
    new_id = conn.execute("SELECT id FROM curated_models WHERE name = 'mistral:7b'").fetchone()["id"]

    # Assert:則1 讀得出來,id 依序為 1、2、3
    assert read_error is None
    assert [row[0] for row in rows] == [1, 2, 3]
    # Assert:則2 3 列的 auto_download 都是 0
    assert [row[5] for row in rows] == [0, 0, 0]
    # Assert:則3 id 2 的建議類型 H100、高 RAM 1
    assert rows[1][3:5] == ("H100", 1)
    # Assert:則4 id 1 的說明「平常用」、建議 T4
    assert rows[0][2:4] == ("平常用", "T4")
    # Assert:則5 id 3 的建議類型與高 RAM 都是 NULL
    assert rows[2][3:5] == (None, None)
    # Assert:則6 新寫入的 mistral:7b 的 id 為 5(刪過的 4 不重用)
    assert new_id == 5
    conn.close()


def _table_info(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(f"PRAGMA table_info({table})")]


# ---- 004 US3-DB-03


def test_舊資料庫升級後的自動下載結果表_結果項目表_自動下載欄與名稱唯一索引和全新庫一致(tmp_path: Path) -> None:
    # Arrange:舊庫寫入 1 筆精選;另開一個全新庫
    old = _build_v0(tmp_path / "old.sqlite3")
    old.execute("INSERT INTO curated_models (name) VALUES ('qwen2.5:latest')")
    fresh = connect(tmp_path / "fresh.sqlite3")

    # Act:兩個庫各跑 create_schema
    create_schema(old)
    create_schema(fresh)

    # Assert:則1 遷移後的 auto_download_results 與全新庫的完全相同
    assert _table_info(old, "auto_download_results") == _table_info(fresh, "auto_download_results") != []
    # Assert:則2 遷移後的 auto_download_items 與全新庫的完全相同
    assert _table_info(old, "auto_download_items") == _table_info(fresh, "auto_download_items") != []
    # Assert:則3 auto_download 那一列除了 cid 之外與全新庫的相同
    migrated_column = [row[1:] for row in _table_info(old, "curated_models") if row[1] == "auto_download"]
    fresh_column = [row[1:] for row in _table_info(fresh, "curated_models") if row[1] == "auto_download"]
    assert migrated_column == fresh_column != []
    # Assert:則4 遷移後有唯一的 uq_curated_models_name_ci
    indexes = {row["name"]: row["unique"] for row in old.execute("PRAGMA index_list(curated_models)")}
    assert indexes.get("uq_curated_models_name_ci") == 1
    old.close()
    fresh.close()


# ---- 004 US3-DB-04


def test_精選項目已有自動下載欄時升級不重複加欄_使用者設過的值不變_仍補建新表(tmp_path: Path) -> None:
    # Arrange:舊庫 2 筆精選,已手動加好 auto_download 欄且 id 1 設為 1;user_version 仍是 0
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    old.execute("INSERT INTO curated_models (name) VALUES ('qwen2.5:latest')")
    old.execute("INSERT INTO curated_models (name) VALUES ('llama3.2:3b')")
    old.execute("ALTER TABLE curated_models ADD COLUMN auto_download INTEGER NOT NULL DEFAULT 0 CHECK (auto_download IN (0, 1))")
    old.execute("UPDATE curated_models SET auto_download = 1 WHERE id = 1")
    old.close()
    conn = connect(db_path)

    # Act
    error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        error = exc

    # Assert:則1 沒有丟出例外
    assert error is None
    # Assert:則2 auto_download 欄只有 1 列
    assert [row["name"] for row in conn.execute("PRAGMA table_info(curated_models)")].count("auto_download") == 1
    # Assert:則3 id 1 的 auto_download 仍是 1
    assert conn.execute("SELECT auto_download FROM curated_models WHERE id = 1").fetchone()[0] == 1
    # Assert:則4 兩張新表都建起來了
    assert {"auto_download_results", "auto_download_items"} <= _sqlite_master_names(conn)
    conn.close()


# ---- 004 US3-DB-05


def test_舊資料庫有只差大小寫的精選名稱時留_id_最小的並把刪掉的名稱寫進日誌(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Arrange:舊庫 3 筆精選,id 1 與 id 3 的名稱只差大小寫
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    old.execute("INSERT INTO curated_models (name) VALUES ('qwen2.5:latest')")
    old.execute("INSERT INTO curated_models (name) VALUES ('llama3.2:3b')")
    old.execute("INSERT INTO curated_models (name, description) VALUES ('qwen2.5:Latest', '大寫那筆')")
    old.close()
    conn = connect(db_path)

    # Act
    error: sqlite3.Error | None = None
    with caplog.at_level(logging.INFO):
        try:
            create_schema(conn)
        except sqlite3.Error as exc:
            error = exc

    # Assert:則1 沒有丟出例外
    assert error is None
    # Assert:則2 讀到 2 列,依序為 id 1 的 qwen2.5:latest、id 2 的 llama3.2:3b
    rows = [(row["id"], row["name"]) for row in conn.execute("SELECT id, name FROM curated_models ORDER BY id")]
    assert rows == [(1, "qwen2.5:latest"), (2, "llama3.2:3b")]
    # Assert:則3 不分大小寫的唯一索引建起來了
    assert "uq_curated_models_name_ci" in [row["name"] for row in conn.execute("PRAGMA index_list(curated_models)")]
    # Assert:則4 user_version 為 2(005 起 0 → 1 之後接著做 1 → 2,plan.md Q41)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則5 有一筆 WARNING 以上的日誌含被刪那一筆的名稱
    assert any(record.levelno >= logging.WARNING and "qwen2.5:Latest" in record.getMessage() for record in caplog.records)
    conn.close()


# ---- 004 US3-DB-06


def test_精選項目的遷移中途失敗時整個還原_下次啟動可再升級(tmp_path: Path) -> None:
    # Arrange:舊庫 1 筆精選;開檔後拒絕設定 user_version
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v0(db_path)
    old.execute("INSERT INTO curated_models (name, description) VALUES ('qwen2.5:latest', '平常用')")
    old.close()
    conn = connect(db_path)
    conn.set_authorizer(_deny_setting_user_version)

    # Act:第一次呼叫
    error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001 - 要確認丟出的是 sqlite3.DatabaseError
        error = exc

    # Assert:則1 丟出 sqlite3.DatabaseError(含子類)
    assert isinstance(error, sqlite3.DatabaseError)
    # Assert:則2 curated_models 沒有 auto_download
    assert "auto_download" not in [row["name"] for row in conn.execute("PRAGMA table_info(curated_models)")]
    # Assert:則3、則4 沒有留下兩張新表與 uq_curated_models_name_ci
    names = _sqlite_master_names(conn)
    assert names.isdisjoint({"auto_download_results", "auto_download_items", "uq_curated_models_name_ci"})
    # Assert:則5 id 1 的 name 與 description 沒變
    assert [tuple(row) for row in conn.execute("SELECT name, description FROM curated_models WHERE id = 1")] == [
        ("qwen2.5:latest", "平常用")
    ]

    # Act:放行後第二次呼叫
    conn.set_authorizer(None)
    retry_error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001
        retry_error = exc

    # Assert:則6 第二次沒有丟出例外,auto_download 只有 1 列
    assert retry_error is None
    assert [row["name"] for row in conn.execute("PRAGMA table_info(curated_models)")].count("auto_download") == 1
    conn.close()


def _open_db(tmp_path: Path, kind: str) -> sqlite3.Connection:
    """`kind` 為 `fresh` 是全新庫;`migrated` 是空的舊庫(001~003 建的)跑過 `create_schema` 的遷移後。"""
    db_path = tmp_path / f"{kind}.sqlite3"
    if kind == "migrated":
        _build_v0(db_path).close()
    conn = connect(db_path)
    create_schema(conn)
    return conn


def _rejected(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> bool:
    """執行 sql,被資料庫的約束(CHECK、NOT NULL、UNIQUE、主鍵)擋下時回 True,寫得進去時回 False。"""
    try:
        conn.execute(sql, params)
    except sqlite3.IntegrityError:
        return True
    return False


# ---- 004 US3-DB-07


@pytest.mark.parametrize("kind", ["fresh", "migrated"])
def test_精選項目的自動下載只收_0_與_1_預設為否_NULL_與其他值都寫不進去(tmp_path: Path, kind: str) -> None:
    # Arrange:全新庫,或舊庫跑過遷移後
    conn = _open_db(tmp_path, kind)

    # Act
    a_rejected = _rejected(conn, "INSERT INTO curated_models (name) VALUES ('a:latest')")
    b_rejected = _rejected(conn, "INSERT INTO curated_models (name, auto_download) VALUES ('b:latest', 1)")
    c_rejected = _rejected(conn, "INSERT INTO curated_models (name, auto_download) VALUES ('c:latest', 2)")
    d_rejected = _rejected(conn, "INSERT INTO curated_models (name, auto_download) VALUES ('d:latest', -1)")
    e_rejected = _rejected(conn, "INSERT INTO curated_models (name, auto_download) VALUES ('e:latest', 'true')")
    f_rejected = _rejected(conn, "INSERT INTO curated_models (name, auto_download) VALUES ('f:latest', NULL)")
    update_rejected = _rejected(conn, "UPDATE curated_models SET auto_download = 2 WHERE name = 'b:latest'")
    values = {row["name"]: row["auto_download"] for row in conn.execute("SELECT name, auto_download FROM curated_models")}

    # Assert:則1 a:latest 寫得進去,auto_download 為 0
    assert not a_rejected
    assert values["a:latest"] == 0
    # Assert:則2 b:latest 寫得進去,auto_download 為 1
    assert not b_rejected
    assert values["b:latest"] == 1
    # Assert:則3 c、d、e 各被 CHECK 擋下
    assert (c_rejected, d_rejected, e_rejected) == (True, True, True)
    # Assert:則4 f:latest(NULL)被 NOT NULL 擋下
    assert f_rejected
    # Assert:則5 UPDATE 被擋下,b:latest 仍是 1
    assert update_rejected
    assert values["b:latest"] == 1
    assert sorted(values) == ["a:latest", "b:latest"]
    conn.close()


# ---- 004 US3-DB-08


@pytest.mark.parametrize("kind", ["fresh", "migrated"])
def test_精選名稱不分大小寫不重複_不同版本可並存_改自己的大小寫可以_名稱照原樣存(tmp_path: Path, kind: str) -> None:
    # Arrange:全新庫,或舊庫跑過遷移後;先寫入三筆精選
    conn = _open_db(tmp_path, kind)
    conn.execute("INSERT INTO curated_models (name) VALUES ('qwen2.5:7b')")
    conn.execute("INSERT INTO curated_models (name) VALUES ('hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M')")
    conn.execute("INSERT INTO curated_models (name) VALUES ('llama3.2:3b')")

    # Act
    upper_rejected = _rejected(conn, "INSERT INTO curated_models (name) VALUES ('Qwen2.5:7B')")
    hf_rejected = _rejected(
        conn, "INSERT INTO curated_models (name) VALUES ('hf.co/Bartowski/smollm2-135m-instruct-gguf:q4_k_m')"
    )
    other_version_rejected = _rejected(conn, "INSERT INTO curated_models (name) VALUES ('qwen2.5:latest')")
    own_case_rejected = _rejected(conn, "UPDATE curated_models SET name = 'LLAMA3.2:3b' WHERE id = 3")
    own_case_name = conn.execute("SELECT name FROM curated_models WHERE id = 3").fetchone()["name"]
    clash_rejected = _rejected(conn, "UPDATE curated_models SET name = 'QWEN2.5:7b' WHERE id = 3")

    # Assert:則1 前兩句 INSERT 各被擋下
    assert (upper_rejected, hf_rejected) == (True, True)
    # Assert:則2 qwen2.5:latest 寫得進去
    assert not other_version_rejected
    # Assert:則3 改自己的大小寫成功,id 3 的名稱照原樣是 LLAMA3.2:3b
    assert not own_case_rejected
    assert own_case_name == "LLAMA3.2:3b"
    # Assert:則4 改成和 id 1 只差大小寫被擋下
    assert clash_rejected
    conn.close()


# ---- 004 US3-DB-09


def test_自動下載結果一個工作階段只有一列_目標數可為_0_狀態與撤除旗標有限定值(tmp_path: Path) -> None:
    # Arrange:全新庫
    conn = _open_db(tmp_path, "fresh")
    insert = "INSERT INTO auto_download_results (session_name, target_count) VALUES (?, ?)"

    # Act
    first_rejected = _rejected(conn, insert, ("cgb-a", 2))
    first_row = tuple(
        conn.execute("SELECT state, dismissed, finished_at FROM auto_download_results WHERE session_name = 'cgb-a'").fetchone()
    )
    again_rejected = _rejected(conn, insert, ("cgb-a", 2))
    zero_rejected = _rejected(conn, insert, ("cgb-zero", 0))
    negative_rejected = _rejected(conn, insert, ("cgb-neg", -1))
    missing_target_rejected = _rejected(conn, "INSERT INTO auto_download_results (session_name) VALUES ('cgb-null')")
    bad_state_rejected = _rejected(
        conn, "INSERT INTO auto_download_results (session_name, target_count, state) VALUES ('cgb-s', 1, 'pending')"
    )
    bad_dismissed_rejected = _rejected(
        conn, "INSERT INTO auto_download_results (session_name, target_count, dismissed) VALUES ('cgb-d', 1, 2)"
    )
    update_rejected = _rejected(
        conn,
        "UPDATE auto_download_results SET state = 'done', finished_at = '2026-11-14T08:00:30Z', dismissed = 1"
        " WHERE session_name = 'cgb-a'",
    )
    updated_row = tuple(
        conn.execute("SELECT state, dismissed FROM auto_download_results WHERE session_name = 'cgb-a'").fetchone()
    )

    # Assert:則1 ① 讀回 state 為 running、dismissed 為 0、finished_at 為 NULL
    assert not first_rejected
    assert first_row == ("running", 0, None)
    # Assert:則2 ② 被擋下
    assert again_rejected
    # Assert:則3 ③ 寫得進去
    assert not zero_rejected
    # Assert:則4~則7 ④~⑦ 各被擋下
    assert (negative_rejected, missing_target_rejected, bad_state_rejected, bad_dismissed_rejected) == (True,) * 4
    # Assert:則8 ⑧ 成功,讀回 state 為 done、dismissed 為 1
    assert not update_rejected
    assert updated_row == ("done", 1)
    conn.close()


# ---- 004 US3-DB-10


def test_自動下載結果項目的原因只收四種_排入的項目原因可為空_同一位置只有一筆(tmp_path: Path) -> None:
    # Arrange:全新庫,auto_download_results 已有 cgb-a、cgb-b 兩列
    conn = _open_db(tmp_path, "fresh")
    conn.execute("INSERT INTO auto_download_results (session_name, target_count) VALUES ('cgb-a', 5)")
    conn.execute("INSERT INTO auto_download_results (session_name, target_count) VALUES ('cgb-b', 1)")
    insert = "INSERT INTO auto_download_items (session_name, position, model, reason, reason_code, message) VALUES (?, ?, ?, ?, ?, ?)"

    # Act
    accepted = [
        not _rejected(conn, insert, ("cgb-a", 0, "qwen2.5:7b", None, None, None)),
        not _rejected(conn, insert, ("cgb-a", 1, "qwen2.5:32b", "DISK_SPACE_INSUFFICIENT", None, "剩餘空間不足")),
        not _rejected(conn, insert, ("cgb-a", 2, "hf.co/x/y:Q4_K_M", "SIZE_UNAVAILABLE", "HF_TIMEOUT", "取不到大小")),
        not _rejected(conn, insert, ("cgb-a", 3, "llama3.1:70b", "MAY_NOT_FIT", None, "這台可能無法載入")),
        not _rejected(conn, insert, ("cgb-b", 0, "qwen2.5:7b", "DISK_SPACE_UNKNOWN", "COLAB_EXEC_FAILED", "讀不到剩餘空間")),
    ]
    count = conn.execute("SELECT count(*) FROM auto_download_items").fetchone()[0]
    unknown_reasons = [row[0] for row in conn.execute("SELECT reason FROM auto_download_items WHERE session_name = 'cgb-b'")]
    unlisted_reason_rejected = _rejected(conn, insert, ("cgb-a", 4, "gemma2:2b", "DISK_FULL", None, "空間不足"))
    lowercase_reason_rejected = _rejected(conn, insert, ("cgb-a", 4, "gemma2:2b", "disk_space_insufficient", None, "空間不足"))
    duplicate_position_rejected = _rejected(conn, insert, ("cgb-a", 1, "phi3:mini", None, None, None))
    missing_position_rejected = _rejected(conn, insert, ("cgb-a", None, "phi3:mini", None, None, None))
    missing_model_rejected = _rejected(conn, insert, ("cgb-a", 5, None, None, None, None))

    # Assert:則1 ①~⑤ 都寫得進去,共 5 列
    assert accepted == [True] * 5
    assert count == 5
    # Assert:則2 ⑤ 讀回的 reason 為 DISK_SPACE_UNKNOWN
    assert unknown_reasons == ["DISK_SPACE_UNKNOWN"]
    # Assert:則3~則7 ⑥~⑩ 各被擋下
    assert (
        unlisted_reason_rejected,
        lowercase_reason_rejected,
        duplicate_position_rejected,
        missing_position_rejected,
        missing_model_rejected,
    ) == (True,) * 5
    conn.close()


def _foreign_key_list(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return [(row["table"], row["from"], row["to"], row["on_delete"]) for row in conn.execute(f"PRAGMA foreign_key_list({table})")]


# ---- 004 US3-DB-11


def test_外鍵維持關閉_結果項目表與結果表的外鍵宣告在遷移前後相同_刪結果列不會自己刪項目(tmp_path: Path) -> None:
    # Arrange:全新庫(A)與舊庫跑過遷移後(B)
    fresh = _open_db(tmp_path, "fresh")
    migrated = _open_db(tmp_path, "migrated")

    # Act:A 寫入 sessions、結果列、項目後刪掉結果列
    fresh_foreign_keys = fresh.execute("PRAGMA foreign_keys").fetchone()[0]
    _insert_session(fresh, "cgb-a", "ready", 1)
    fresh.execute("INSERT INTO auto_download_results (session_name, target_count) VALUES ('cgb-a', 1)")
    fresh.execute("INSERT INTO auto_download_items (session_name, position, model) VALUES ('cgb-a', 0, 'qwen2.5:7b')")
    fresh.execute("DELETE FROM auto_download_results WHERE session_name = 'cgb-a'")
    remaining_items = fresh.execute("SELECT count(*) FROM auto_download_items WHERE session_name = 'cgb-a'").fetchone()[0]

    # Assert:則1 A 的 foreign_keys 為 0
    assert fresh_foreign_keys == 0
    # Assert:則2 A 的 auto_download_items 外鍵指向 auto_download_results,ON DELETE CASCADE
    assert _foreign_key_list(fresh, "auto_download_items") == [("auto_download_results", "session_name", "session_name", "CASCADE")]
    # Assert:則3 A 的 auto_download_results 外鍵指向 sessions,ON DELETE CASCADE
    assert _foreign_key_list(fresh, "auto_download_results") == [("sessions", "session_name", "name", "CASCADE")]
    # Assert:則4 A 刪除後 auto_download_items 仍有 cgb-a 的 1 列
    assert remaining_items == 1
    # Assert:則5 B 的 foreign_keys 為 0
    assert migrated.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    # Assert:則6、則7 B 的兩張表外鍵與 A 的相同
    assert _foreign_key_list(migrated, "auto_download_items") == _foreign_key_list(fresh, "auto_download_items")
    assert _foreign_key_list(migrated, "auto_download_results") == _foreign_key_list(fresh, "auto_download_results")
    fresh.close()
    migrated.close()


# ---- 004 US3-DB-12


def test_後端重新啟動後精選清單_自動下載設定與自動下載結果都還在(tmp_path: Path) -> None:
    # Arrange:全新庫寫入兩筆精選、cgb-a 的結果列(已完成、已撤除)與一筆結果項目
    db_path = tmp_path / "cgb.sqlite3"
    conn = connect(db_path)
    create_schema(conn)
    conn.execute(
        "INSERT INTO curated_models (name, auto_download, description, recommended_runtime_type_gpu,"
        " recommended_runtime_type_high_mem) VALUES ('qwen2.5:7b', 1, '每次都要', 'L4', 0)"
    )
    conn.execute("INSERT INTO curated_models (name, auto_download) VALUES ('llama3.2:3b', 0)")
    conn.execute(
        "INSERT INTO auto_download_results (session_name, target_count, state, dismissed, finished_at)"
        " VALUES ('cgb-a', 1, 'done', 1, '2026-11-14T08:00:30Z')"
    )
    conn.execute(
        "INSERT INTO auto_download_items (session_name, position, model, reason, reason_code, message)"
        " VALUES ('cgb-a', 0, 'qwen2.5:7b', NULL, NULL, NULL)"
    )

    # Act:關閉連線,以新的連線開同一個檔並再跑一次 create_schema(模擬後端重新啟動)
    conn.close()
    reopened = connect(db_path)
    create_schema(reopened)

    # Assert:則1 精選的名稱與自動下載照舊
    assert [tuple(row) for row in reopened.execute("SELECT name, auto_download FROM curated_models ORDER BY id")] == [
        ("qwen2.5:7b", 1),
        ("llama3.2:3b", 0),
    ]
    # Assert:則2 qwen2.5:7b 的說明與建議類型照舊
    assert [
        tuple(row)
        for row in reopened.execute(
            "SELECT description, recommended_runtime_type_gpu FROM curated_models WHERE name = 'qwen2.5:7b'"
        )
    ] == [("每次都要", "L4")]
    # Assert:則3 cgb-a 的結果列仍在,state 為 done、dismissed 為 1
    assert [
        tuple(row) for row in reopened.execute("SELECT state, dismissed FROM auto_download_results WHERE session_name = 'cgb-a'")
    ] == [("done", 1)]
    # Assert:則4 auto_download_items 仍有 cgb-a 的 1 列
    assert reopened.execute("SELECT count(*) FROM auto_download_items WHERE session_name = 'cgb-a'").fetchone()[0] == 1
    # Assert:則5 user_version 為 2(005 起全新庫直接建到第 2 版,plan.md Q41)
    assert reopened.execute("PRAGMA user_version").fetchone()[0] == 2
    reopened.close()


# ---- 004 US3-DB-13


@pytest.mark.parametrize("kind", ["fresh", "migrated"])
def test_自動下載結果項目的大小_剩餘空間_顯存三欄可為空_有值時照原值讀回(tmp_path: Path, kind: str) -> None:
    # Arrange:全新庫,或舊庫跑過遷移後;auto_download_results 先有 cgb-a
    conn = _open_db(tmp_path, kind)
    conn.execute("INSERT INTO auto_download_results (session_name, target_count) VALUES ('cgb-a', 2)")

    # Act
    columns = {
        row["name"]: (row["type"], row["notnull"])
        for row in conn.execute("PRAGMA table_info(auto_download_items)")
        if row["name"] in ("size_bytes", "free_disk_bytes", "vram_bytes")
    }
    minimal_rejected = _rejected(
        conn, "INSERT INTO auto_download_items (session_name, position, model) VALUES ('cgb-a', 0, 'qwen2.5:7b')"
    )
    minimal_sizes = [
        tuple(row)
        for row in conn.execute(
            "SELECT size_bytes, free_disk_bytes, vram_bytes FROM auto_download_items WHERE position = 0"
        )
    ]
    full_rejected = _rejected(
        conn,
        "INSERT INTO auto_download_items (session_name, position, model, reason, reason_code, message, size_bytes,"
        " free_disk_bytes, vram_bytes) VALUES ('cgb-a', 1, 'llama3.2:latest', 'DISK_SPACE_INSUFFICIENT', NULL, '空間不足',"
        " 2019393189, 516912668, NULL)",
    )
    full_sizes = [
        tuple(row)
        for row in conn.execute(
            "SELECT size_bytes, free_disk_bytes, vram_bytes FROM auto_download_items WHERE position = 1"
        )
    ]

    # Assert:則1 三欄都是 INTEGER、可為 NULL
    assert columns == {"size_bytes": ("INTEGER", 0), "free_disk_bytes": ("INTEGER", 0), "vram_bytes": ("INTEGER", 0)}
    # Assert:則2 ① 寫入成功,三欄都是 NULL
    assert not minimal_rejected
    assert minimal_sizes == [(None, None, None)]
    # Assert:則3 ② 讀回 (2019393189, 516912668, None)
    assert not full_rejected
    assert full_sizes == [(2019393189, 516912668, None)]
    conn.close()


_SCHEMA_V1 = Path(__file__).parent.parent / "fixtures" / "db" / "schema_v1.sql"


def _build_v1(db_path: Path) -> sqlite3.Connection:
    """以凍結的 004 DDL 建出 v1 舊庫,檔尾的 PRAGMA 把 `user_version` 設成 1(plan.md Q28、Q42)。"""
    conn = connect(db_path)
    conn.executescript(_SCHEMA_V1.read_text(encoding="utf-8"))
    return conn


# ---- 005 US1-DB-01

# 「session_tunings 的欄名」:contracts/store.dbml § Table session_tunings,依宣告順序(testplan.md § 2.3 US1-DB-01 則3)
_SESSION_TUNINGS_COLUMNS = [
    "id", "session_name", "at", "finished_at", "trigger", "attempt",
    "requested_num_parallel", "requested_context_length", "requested_max_loaded_models",
    "gpu_name", "vram_total_bytes", "system_memory_total_bytes", "probed_at",
    "num_parallel", "num_parallel_source", "context_length", "context_length_source",
    "max_loaded_models", "max_loaded_models_source", "flash_attention", "flash_attention_source",
    "kv_cache_type", "kv_cache_type_source", "result", "reason_code", "remote_stage", "message",
]  # fmt: skip


def test_全新資料庫建出_user_version_為_2_有三張設定表_開啟紀錄的欄位_索引與外鍵照規格_外鍵仍關閉(tmp_path: Path) -> None:
    # Arrange:tmp_path 裡還沒有資料庫檔
    conn = connect(tmp_path / "cgb.sqlite3")

    # Act
    create_schema(conn)

    # Assert:則1 user_version 為 2
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則2 三張新表都建了
    assert {"runtime_type_tunings", "session_tunings", "session_tuning_models"} <= _sqlite_master_names(conn)
    # Assert:則3 session_tunings 的欄名依序照規格
    assert [row["name"] for row in conn.execute("PRAGMA table_info(session_tunings)")] == _SESSION_TUNINGS_COLUMNS
    # Assert:則4 一般索引與兩個部分唯一索引
    indexes = {row["name"]: row["unique"] for row in conn.execute("PRAGMA index_list(session_tunings)")}
    assert "idx_session_tunings_session" in indexes
    assert (indexes.get("uq_session_tunings_open"), indexes.get("uq_session_tunings_in_progress")) == (1, 1)
    # Assert:則5 只有一個外鍵,指向 sessions(name),刪除時 cascade
    assert _foreign_key_list(conn, "session_tunings") == [("sessions", "session_name", "name", "CASCADE")]
    # Assert:則6 同一條連線沒有開 foreign_keys
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    conn.close()


# 「開啟那一筆(A100)」:testplan.md § 2.3
_OPEN_TUNING_A100 = {
    "session_name": "cgb-a",
    "at": "2026-11-15T08:00:00Z",
    "finished_at": "2026-11-15T08:00:00Z",
    "trigger": "open",
    "attempt": None,
    "requested_num_parallel": None,
    "requested_context_length": None,
    "requested_max_loaded_models": None,
    "gpu_name": "NVIDIA A100-SXM4-40GB",
    "vram_total_bytes": 42949672960,
    "system_memory_total_bytes": 89120571392,
    "probed_at": "2026-11-15T07:59:50Z",
    "num_parallel": 8,
    "num_parallel_source": "auto",
    "context_length": 8192,
    "context_length_source": "auto",
    "max_loaded_models": 2,
    "max_loaded_models_source": "auto",
    "flash_attention": 1,
    "flash_attention_source": "auto",
    "kv_cache_type": "q8_0",
    "kv_cache_type_source": "auto",
    "result": "applied",
    "reason_code": None,
    "remote_stage": None,
    "message": None,
}


def _insert_tuning(conn: sqlite3.Connection, **overrides: object) -> None:
    """以「開啟那一筆(A100)」為底寫一筆 session_tunings,只換 overrides 給的欄位。"""
    columns = {**_OPEN_TUNING_A100, **overrides}
    conn.execute(
        f"INSERT INTO session_tunings ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        tuple(columns.values()),
    )


def _tuning_rejected(conn: sqlite3.Connection, **overrides: object) -> bool:
    """寫一筆 session_tunings,被約束擋下時回 True。"""
    try:
        _insert_tuning(conn, **overrides)
    except sqlite3.IntegrityError:
        return True
    return False


# ---- 005 US1-DB-02


def test_開啟那一筆的顯示記憶體以整數位元組存_量到的硬體與五項設定照原值讀回_一個工作階段只有一筆_開啟那一筆不帶_attempt(
    tmp_path: Path,
) -> None:
    # Arrange:全新庫;cgb-a(A100,ready)、cgb-b(T4,ended)、cgb-c(L4,ended)
    conn = connect(tmp_path / "cgb.sqlite3")
    create_schema(conn)
    _insert_session(conn, "cgb-a", "ready", 1, runtime_type_gpu="A100")
    _insert_session(conn, "cgb-b", "ended", None, runtime_type_gpu="T4", end_reason="USER_ENDED")
    _insert_session(conn, "cgb-c", "ended", None, runtime_type_gpu="L4", end_reason="USER_ENDED")

    # Act:①寫入開啟那一筆(A100);②讀回
    first_rejected = _tuning_rejected(conn)
    row = conn.execute("SELECT * FROM session_tunings WHERE session_name = 'cgb-a'").fetchone()
    types = tuple(conn.execute("SELECT typeof(vram_total_bytes), typeof(system_memory_total_bytes) FROM session_tunings").fetchone())
    # Act:③ cgb-a 第二筆開啟;④ cgb-b 的開啟那一筆(T4);⑤ cgb-c 的開啟那一筆帶了 attempt
    second_open_rejected = _tuning_rejected(conn, at="2026-11-15T08:10:00Z", finished_at="2026-11-15T08:10:00Z")
    t4_rejected = _tuning_rejected(
        conn,
        session_name="cgb-b",
        gpu_name="Tesla T4",
        vram_total_bytes=16106127360,
        num_parallel=2,
        context_length=4096,
        max_loaded_models=1,
    )
    attempt_rejected = _tuning_rejected(conn, session_name="cgb-c", attempt="requested")

    # Assert:則1 ① 寫得進去
    assert not first_rejected
    # Assert:則2 讀回的兩個記憶體位元組數
    assert (row["vram_total_bytes"], row["system_memory_total_bytes"]) == (42949672960, 89120571392)
    # Assert:則3 兩欄的 typeof 都是 integer
    assert types == ("integer", "integer")
    # Assert:則4 GPU 名稱與量測時間
    assert (row["gpu_name"], row["probed_at"]) == ("NVIDIA A100-SXM4-40GB", "2026-11-15T07:59:50Z")
    # Assert:則5 五項設定
    settings = ("num_parallel", "context_length", "max_loaded_models", "flash_attention", "kv_cache_type")
    assert tuple(row[name] for name in settings) == (8, 8192, 2, 1, "q8_0")
    # Assert:則6 五個來源都是 auto、result 為 applied
    assert [row[f"{name}_source"] for name in settings] == ["auto"] * 5
    assert row["result"] == "applied"
    # Assert:則7 ③ 同一個工作階段第二筆開啟寫不進去
    assert second_open_rejected
    # Assert:則8 ④ 另一個工作階段的開啟那一筆寫得進去
    assert not t4_rejected
    # Assert:則9 ⑤ 開啟那一筆帶了 attempt 寫不進去
    assert attempt_rejected
    conn.close()


# ---- 005 US1-DB-03

_TUNING_VALUES = ("num_parallel", "context_length", "max_loaded_models", "flash_attention", "kv_cache_type")


def test_讀不到顯示記憶體與讀不到設定檔時開啟那一筆寫得進去_範圍外與清單外的值寫不進去_外鍵未開不檢查參照(tmp_path: Path) -> None:
    # Arrange:全新庫;cgb-a、cgb-b 與 cgb-c3~cgb-c9
    conn = connect(tmp_path / "cgb.sqlite3")
    create_schema(conn)
    for name in ["cgb-a", "cgb-b", *(f"cgb-c{n}" for n in range(3, 10))]:
        _insert_session(conn, name, "ended", None, end_reason="USER_ENDED")

    # Act:① 讀不到顯示記憶體,五項都用 Ollama 的預設值
    no_vram_rejected = _tuning_rejected(
        conn,
        gpu_name=None,
        vram_total_bytes=None,
        system_memory_total_bytes=13605273600,
        **{name: None for name in _TUNING_VALUES},
        **{f"{name}_source": "ollama_default" for name in _TUNING_VALUES},
    )
    no_vram = conn.execute("SELECT * FROM session_tunings WHERE session_name = 'cgb-a'").fetchone()
    # Act:② 遠端 Ollama 已在執行而讀不到設定檔,五項與來源全部 NULL
    no_tuning_rejected = _tuning_rejected(
        conn,
        session_name="cgb-b",
        **{name: None for name in _TUNING_VALUES},
        **{f"{name}_source": None for name in _TUNING_VALUES},
    )
    # Act:③~⑨ 各寫在還沒有開啟那一筆的 cgb-c3~cgb-c9
    bad_values = [
        {"vram_total_bytes": -1},
        {"num_parallel": 0},
        {"flash_attention": 2},
        {"num_parallel_source": "default"},
        {"kv_cache_type": "q4_0"},
        {"trigger": "restart"},
        {"result": None},
    ]
    bad_rejected = [_tuning_rejected(conn, session_name=f"cgb-c{n}", **bad) for n, bad in zip(range(3, 10), bad_values)]
    # Act:⑩ sessions 沒有的工作階段
    unknown_session_rejected = _tuning_rejected(conn, session_name="cgb-zzz")

    # Assert:則1 ① 寫得進去;則2 顯示記憶體讀回 NULL
    assert not no_vram_rejected
    assert no_vram["vram_total_bytes"] is None
    # Assert:則3 來源為 ollama_default、值為 NULL
    assert (no_vram["num_parallel_source"], no_vram["num_parallel"]) == ("ollama_default", None)
    # Assert:則4 ② 寫得進去
    assert not no_tuning_rejected
    # Assert:則5~則11 ③~⑨ 都寫不進去
    assert bad_rejected == [True] * 7
    # Assert:則12 ⑩ 寫得進去(foreign_keys 未開,不檢查參照)
    assert not unknown_session_rejected
    conn.close()


# 「v1 舊庫資料」:testplan.md § 2.3。sessions 依 name 排序的 18 個欄位(001 的 name ~ release_warning_detected_at)
_SESSION_COLUMNS = (
    "name", "runtime_type_gpu", "runtime_type_high_mem", "state", "active_slot", "step", "end_reason", "reason_code",
    "message", "opened_at", "ready_at", "ended_at", "last_request_at", "reconnect_started_at", "reconnect_deadline",
    "release_warning_reason_code", "release_warning_message", "release_warning_detected_at",
)  # fmt: skip
_V1_SESSIONS = [
    (
        "cgb-live", "A100", 0, "ready", 1, None, None, None,
        None, "2026-11-15T07:00:00Z", "2026-11-15T07:04:00Z", None, "2026-11-15T07:30:00Z", None, None,
        None, None, None,
    ),
    (
        "cgb-old1", "T4", 0, "ended", None, None, "USER_ENDED", None,
        None, "2026-11-10T08:00:00Z", "2026-11-10T08:03:00Z", "2026-11-10T09:00:00Z", "2026-11-10T08:50:00Z", None, None,
        None, None, None,
    ),
    (
        "cgb-old2", "L4", 1, "lost", None, None, "RECONNECT_TIMEOUT", "TUNNEL_TIMEOUT",
        "重連逾時", "2026-11-12T10:00:00Z", "2026-11-12T10:02:00Z", "2026-11-12T11:05:00Z", None,
        "2026-11-12T11:00:00Z", "2026-11-12T11:05:00Z",
        "COLAB_STOP_UNCONFIRMED", "無法確認已釋放", "2026-11-12T11:06:00Z",
    ),
]  # fmt: skip
# session_transitions 依 id 排序的全部欄位
_TRANSITION_COLUMNS = ("id", "session_name", "at", "state", "step", "end_reason", "reason_code")
_V1_TRANSITIONS = [
    (1, "cgb-old1", "2026-11-10T08:00:00Z", "opening", "allocating", None, None),
    (2, "cgb-old1", "2026-11-10T08:03:00Z", "ready", None, None, None),
    (3, "cgb-old1", "2026-11-10T09:00:00Z", "ended", None, "USER_ENDED", None),
    (4, "cgb-old2", "2026-11-12T11:05:00Z", "lost", None, "RECONNECT_TIMEOUT", "TUNNEL_TIMEOUT"),
    (5, "cgb-live", "2026-11-15T07:04:00Z", "ready", None, None, None),
]


def _insert_v1_data(conn: sqlite3.Connection) -> None:
    """在 v1 舊庫以舊版欄位寫入「v1 舊庫資料」。"""
    for values in _V1_SESSIONS:
        row = dict(zip(_SESSION_COLUMNS, values))
        _insert_session(conn, row.pop("name"), row.pop("state"), row.pop("active_slot"), **row)
    conn.executemany(
        f"INSERT INTO session_transitions ({', '.join(_TRANSITION_COLUMNS)}) VALUES ({', '.join('?' * 7)})", _V1_TRANSITIONS
    )
    _insert_job(conn, "qwen2.5:7b", None, 1, "completed", size_bytes=4683087332, session_name="cgb-live")
    conn.execute("INSERT INTO auto_download_results (session_name, target_count, state) VALUES ('cgb-live', 1, 'done')")
    conn.execute("INSERT INTO auto_download_items (session_name, position, model) VALUES ('cgb-live', 0, 'qwen2.5:7b')")
    conn.execute("INSERT INTO curated_models (name, auto_download) VALUES ('qwen2.5:7b', 1)")


def _open_v1_with_data(db_path: Path) -> sqlite3.Connection:
    """建出 v1 舊庫、寫入「v1 舊庫資料」,關掉後以新的 connect 開同一個檔(後端啟動)。"""
    old = _build_v1(db_path)
    _insert_v1_data(old)
    old.close()
    return connect(db_path)


def _rows(conn: sqlite3.Connection, table: str, columns: tuple[str, ...], order_by: str) -> list[tuple]:
    return [tuple(row) for row in conn.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order_by}")]


def _count(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


# ---- 005 US1-DB-04


def test_v1_舊庫升級到第_2_版_工作階段_狀態變化紀錄_下載與自動下載_精選都照舊_不補設定紀錄(tmp_path: Path) -> None:
    # Arrange:v1 舊庫寫入 v1 舊庫資料
    conn = _open_v1_with_data(tmp_path / "cgb.sqlite3")

    # Act
    error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        error = exc

    # Assert:則1 沒有丟出例外;則2 user_version 為 2
    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則3 sessions 的 18 個欄位三筆都照舊
    assert _rows(conn, "sessions", _SESSION_COLUMNS, "name") == _V1_SESSIONS
    # Assert:則4 session_transitions 五筆都照舊(含 id)
    assert _rows(conn, "session_transitions", _TRANSITION_COLUMNS, "id") == _V1_TRANSITIONS
    # Assert:則5 download_jobs 那一筆仍屬於 cgb-live
    assert [row[0] for row in conn.execute("SELECT session_name FROM download_jobs")] == ["cgb-live"]
    # Assert:則6 自動下載結果與結果項目各仍有 cgb-live 的 1 筆
    assert _count(conn, "SELECT count(*) FROM auto_download_results WHERE session_name = 'cgb-live'") == 1
    assert _count(conn, "SELECT count(*) FROM auto_download_items WHERE session_name = 'cgb-live'") == 1
    # Assert:則7 精選的自動下載仍是 1
    assert _count(conn, "SELECT auto_download FROM curated_models WHERE name = 'qwen2.5:7b'") == 1
    # Assert:則8、則9 不替既有的工作階段補設定紀錄,類型覆蓋值沒有列
    assert _count(conn, "SELECT count(*) FROM session_tunings") == 0
    assert _count(conn, "SELECT count(*) FROM runtime_type_tunings") == 0
    # Assert:則10 沒有留下重建用的暫存表
    assert _sqlite_master_names(conn).isdisjoint({"sessions_new", "session_transitions_new"})
    conn.close()


def _unique_index_columns(conn: sqlite3.Connection, table: str) -> list[list[str]]:
    """table 每個 unique 為 1 的索引各含哪些欄位(index_info)。"""
    return [
        [info["name"] for info in conn.execute(f"PRAGMA index_info('{index['name']}')")]
        for index in conn.execute(f"PRAGMA index_list({table})")
        if index["unique"] == 1
    ]


# ---- 005 US1-DB-05


def test_v1_舊庫重建後工作階段與狀態變化紀錄的表和全新庫相同_索引重建_其他表的外鍵仍指向_sessions_序號接續(tmp_path: Path) -> None:
    # Arrange:v1 舊庫寫入 v1 舊庫資料後跑過 create_schema;另開一個全新庫
    conn = _open_v1_with_data(tmp_path / "cgb.sqlite3")
    create_schema(conn)
    fresh = connect(tmp_path / "fresh.sqlite3")
    create_schema(fresh)

    # Act
    session_index_names = {row["name"] for row in conn.execute("PRAGMA index_list(sessions)")}
    transition_index_names = {row["name"] for row in conn.execute("PRAGMA index_list(session_transitions)")}
    foreign_key_tables = {
        table: [(row["table"], row["on_delete"]) for row in conn.execute(f"PRAGMA foreign_key_list({table})")]
        for table in ("session_transitions", "download_jobs", "auto_download_results")
    }
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    new_id = conn.execute(
        "INSERT INTO session_transitions (session_name, at, state) VALUES ('cgb-live', '2026-11-15T08:00:00Z', 'ready')"
    ).lastrowid

    # Assert:則1、則2 兩張表的欄位定義與全新庫完全相同
    assert _table_info(conn, "sessions") == _table_info(fresh, "sessions") != []
    assert _table_info(conn, "session_transitions") == _table_info(fresh, "session_transitions") != []
    # Assert:則3 sessions 的兩個索引重建了;則4 active_slot 仍是唯一
    assert {"idx_sessions_opened_at", "idx_sessions_state"} <= session_index_names
    assert ["active_slot"] in _unique_index_columns(conn, "sessions")
    # Assert:則5 session_transitions 的索引重建了
    assert "idx_session_transitions_session" in transition_index_names
    # Assert:則6~則8 三張表的外鍵仍指向 sessions
    assert foreign_key_tables["session_transitions"] == [("sessions", "CASCADE")]
    assert [table for table, _ in foreign_key_tables["download_jobs"]] == ["sessions"]
    assert [table for table, _ in foreign_key_tables["auto_download_results"]] == ["sessions"]
    # Assert:則9 沒有參照不到的列
    assert violations == []
    # Assert:則10 新的狀態變化紀錄序號接著最大的 id
    assert new_id == 6
    conn.close()
    fresh.close()


# ---- 005 US1-DB-06


def test_連線開了外鍵時不遷移_丟出含_foreign_keys_的例外_狀態變化紀錄與下載佇列一筆都沒少(tmp_path: Path) -> None:
    # Arrange:v1 舊庫寫入 v1 舊庫資料;開檔後先開外鍵
    db_path = tmp_path / "cgb.sqlite3"
    conn = _open_v1_with_data(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Act:呼叫 create_schema;關掉後以新的 connect(外鍵為 0)讀回
    error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001 - 要確認丟出了例外與它的訊息
        error = exc
    conn.close()
    reopened = connect(db_path)

    # Assert:則1 丟出例外,訊息含 foreign_keys
    assert error is not None and "foreign_keys" in str(error)
    # Assert:則2 user_version 仍是 1
    assert reopened.execute("PRAGMA user_version").fetchone()[0] == 1
    # Assert:則3 狀態變化紀錄仍有 5 筆
    assert _count(reopened, "SELECT count(*) FROM session_transitions") == 5
    # Assert:則4 下載佇列仍有 cgb-live 的 1 筆
    assert _count(reopened, "SELECT count(*) FROM download_jobs WHERE session_name = 'cgb-live'") == 1
    # Assert:則5 自動下載結果仍有 1 筆
    assert _count(reopened, "SELECT count(*) FROM auto_download_results") == 1
    # Assert:則6 沒有建出 session_tunings
    assert "session_tunings" not in _sqlite_master_names(reopened)
    reopened.close()


def _deny_user_version_2(action: int, arg1: str | None, arg2: str | None, *_: object) -> int:
    """1 → 2 的最後一步是設 user_version = 2;只擋這一句,0 → 1 設的 1 與讀取照常(testplan.md § 2.3)。"""
    if action == sqlite3.SQLITE_PRAGMA and arg1 == "user_version" and arg2 == "2":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


# ---- 005 US1-DB-07


def test_v1_升級中途失敗時整個還原_原例外往上丟_沒有留下新表與暫存表_下次啟動可再升級(tmp_path: Path) -> None:
    # Arrange:v1 舊庫寫入 v1 舊庫資料;開檔後拒絕設 user_version = 2
    conn = _open_v1_with_data(tmp_path / "cgb.sqlite3")
    conn.set_authorizer(_deny_user_version_2)

    # Act:第一次呼叫
    error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001 - 要確認丟出的是 sqlite3.DatabaseError
        error = exc

    # Assert:則1 丟出 sqlite3.DatabaseError(含子類);則2 user_version 仍是 1
    assert isinstance(error, sqlite3.DatabaseError)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    # Assert:則3 沒有三張新表;則4 沒有重建用的暫存表
    names = _sqlite_master_names(conn)
    assert names.isdisjoint({"runtime_type_tunings", "session_tunings", "session_tuning_models"})
    assert names.isdisjoint({"sessions_new", "session_transitions_new"})
    # Assert:則5 sessions 仍是舊的 CHECK,applying_tuning 寫不進去
    assert _rejected(conn, "UPDATE sessions SET state = 'applying_tuning' WHERE name = 'cgb-live'")
    # Assert:則6 狀態變化紀錄五筆照舊;則7 舊的兩個索引仍在
    assert _rows(conn, "session_transitions", _TRANSITION_COLUMNS, "id") == _V1_TRANSITIONS
    assert {"idx_sessions_state", "idx_session_transitions_session"} <= names

    # Act:放行後第二次呼叫
    conn.set_authorizer(None)
    retry_error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001
        retry_error = exc

    # Assert:則8 第二次沒有丟出例外,之後 user_version 為 2
    assert retry_error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    conn.close()


def _open_v0_with_data(db_path: Path) -> sqlite3.Connection:
    """v0 舊庫(004 之前)寫入 cgb-old(ended)、一筆狀態變化紀錄與一筆排隊中的下載,關掉後以新的 connect 開同一個檔。"""
    old = _build_v0(db_path)
    _insert_session(old, "cgb-old", "ended", None, end_reason="USER_ENDED")
    old.execute(
        "INSERT INTO session_transitions (session_name, at, state, end_reason)"
        " VALUES ('cgb-old', '2026-11-09T09:00:00Z', 'ended', 'USER_ENDED')"
    )
    _insert_job(old, "qwen2.5:7b", "qwen2.5:7b", 1, "queued")
    old.close()
    return connect(db_path)


# ---- 005 US1-DB-08


def test_v0_舊庫一次啟動就升到第_2_版_下載項目有所屬工作階段_工作階段收得下套用設定的狀態(tmp_path: Path) -> None:
    # Arrange:v0 舊庫寫入 cgb-old、一筆狀態變化紀錄與一筆排隊中的下載
    conn = _open_v0_with_data(tmp_path / "cgb.sqlite3")

    # Act:只呼叫一次
    error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        error = exc

    # Assert:則1 沒有丟出例外;則2 user_version 為 2
    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則3 download_jobs 有 session_name;則4 有 session_tunings
    assert "session_name" in [row["name"] for row in conn.execute("PRAGMA table_info(download_jobs)")]
    assert "session_tunings" in _sqlite_master_names(conn)
    # Assert:則5 工作階段寫得進套用設定中與重啟遠端 Ollama 的步驟
    assert not _rejected(
        conn, "UPDATE sessions SET state = 'applying_tuning', step = 'restarting_ollama' WHERE name = 'cgb-old'"
    )
    # Assert:則6 狀態變化紀錄仍有 1 筆
    assert _count(conn, "SELECT count(*) FROM session_transitions") == 1
    conn.close()


# ---- 005 US1-DB-09


def test_v0_舊庫升到第_2_版失敗時停在第_1_版_下次啟動只再做_1_到_2(tmp_path: Path) -> None:
    # Arrange:v0 舊庫寫入同 US1-DB-08 的資料;開檔後拒絕設 user_version = 2
    conn = _open_v0_with_data(tmp_path / "cgb.sqlite3")
    conn.set_authorizer(_deny_user_version_2)

    # Act:第一次呼叫
    error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001 - 要確認丟出的是 sqlite3.DatabaseError
        error = exc

    # Assert:則1 丟出 sqlite3.DatabaseError(含子類);則2 user_version 停在 1
    assert isinstance(error, sqlite3.DatabaseError)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    # Assert:則3 0 → 1 已 commit,download_jobs 有 session_name;則4 沒有 session_tunings
    assert "session_name" in [row["name"] for row in conn.execute("PRAGMA table_info(download_jobs)")]
    assert "session_tunings" not in _sqlite_master_names(conn)

    # Act:放行後第二次呼叫
    conn.set_authorizer(None)
    retry_error: Exception | None = None
    try:
        create_schema(conn)
    except Exception as exc:  # noqa: BLE001
        retry_error = exc

    # Assert:則5 第二次沒有丟出例外,之後 user_version 為 2
    assert retry_error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則6 download_jobs 沒有再重建一次:session_name 仍是 NULL、pending_model 照舊
    assert [tuple(row) for row in conn.execute("SELECT session_name, pending_model FROM download_jobs")] == [
        (None, "qwen2.5:7b")
    ]
    conn.close()


# ---- 005 US1-DB-10


def test_已是第_2_版的庫重新啟動不重跑遷移_開啟那一筆還在_比第_2_版新的庫不動也不降版(tmp_path: Path) -> None:
    # Arrange:情況 A 全新庫有 cgb-a(ready)與開啟那一筆(A100)
    db_path = tmp_path / "cgb.sqlite3"
    conn = connect(db_path)
    create_schema(conn)
    _insert_session(conn, "cgb-a", "ready", 1, runtime_type_gpu="A100")
    _insert_tuning(conn)
    # Arrange:情況 B 另一個全新庫,user_version 改成 3(用舊版後端開新版的資料庫)
    newer = connect(tmp_path / "newer.sqlite3")
    create_schema(newer)
    newer.execute("PRAGMA user_version = 3")
    sessions_sql = newer.execute("SELECT sql FROM sqlite_master WHERE name = 'sessions'").fetchone()[0]

    # Act:A 關掉後以新的 connect 開同一個檔再跑 create_schema(後端重新啟動)
    conn.close()
    conn = connect(db_path)
    restart_error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        restart_error = exc
    # Act:B 呼叫 create_schema
    newer_error: sqlite3.Error | None = None
    try:
        create_schema(newer)
    except sqlite3.Error as exc:
        newer_error = exc

    # Assert:則1 A 沒有丟出例外;則2 開啟那一筆仍在、值照舊;則3 user_version 為 2
    assert restart_error is None
    assert [tuple(row) for row in conn.execute("SELECT vram_total_bytes, num_parallel FROM session_tunings")] == [
        (42949672960, 8)
    ]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則4 B 沒有丟出例外;則5 user_version 仍是 3;則6 sessions 的 DDL 沒變
    assert newer_error is None
    assert newer.execute("PRAGMA user_version").fetchone()[0] == 3
    assert newer.execute("SELECT sql FROM sqlite_master WHERE name = 'sessions'").fetchone()[0] == sessions_sql
    conn.close()
    newer.close()


# ---- 005 US1-DB-11


def test_v1_舊庫有清單外的結束原因時照樣升級_結束原因照原值保留(tmp_path: Path) -> None:
    # Arrange:v1 舊庫寫入 v1 舊庫資料,另寫 cgb-odd 與它的狀態變化紀錄,結束原因都是清單外的 SESSION_EXPIRED
    db_path = tmp_path / "cgb.sqlite3"
    old = _build_v1(db_path)
    _insert_v1_data(old)
    _insert_session(old, "cgb-odd", "ended", None, end_reason="SESSION_EXPIRED")
    old.execute(
        "INSERT INTO session_transitions (session_name, at, state, end_reason)"
        " VALUES ('cgb-odd', '2026-11-13T09:00:00Z', 'ended', 'SESSION_EXPIRED')"
    )
    old.close()
    conn = connect(db_path)

    # Act
    error: sqlite3.Error | None = None
    try:
        create_schema(conn)
    except sqlite3.Error as exc:
        error = exc

    # Assert:則1 沒有丟出例外;則2 user_version 為 2
    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    # Assert:則3 cgb-odd 的結束原因照原值
    assert conn.execute("SELECT end_reason FROM sessions WHERE name = 'cgb-odd'").fetchone()[0] == "SESSION_EXPIRED"
    # Assert:則4 它的狀態變化紀錄的結束原因照原值
    assert [row[0] for row in conn.execute("SELECT end_reason FROM session_transitions WHERE session_name = 'cgb-odd'")] == [
        "SESSION_EXPIRED"
    ]
    conn.close()
