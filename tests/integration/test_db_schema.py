"""E4 資料庫(SQLite)(testplan.md § 2.5;contracts/store.dbml)。

接縫:`db` 模組建立的 schema,以 sqlite3 直接下 SQL(plan.md Q98)。
"""

import logging
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


def test_全新資料庫建出_user_version_為_1_且_download_jobs_有所屬工作階段與不分大小寫的唯一索引(tmp_path: Path) -> None:
    # Arrange:tmp_path 裡還沒有資料庫檔
    conn = connect(tmp_path / "cgb.sqlite3")

    # Act
    create_schema(conn)

    # Assert:則1 user_version 為 1
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
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
    # Assert:則2 user_version 為 1
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
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

    # Assert:則8 第二次沒有丟出例外,之後 user_version 為 1
    assert retry_error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
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

    # Assert:則1 沒有丟出例外;則2 user_version 為 1
    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
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

    # Assert:則1 user_version 為 1;則2 download_jobs 有 session_name
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
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
    # Assert:則5 日誌有一筆含被刪那一筆的名稱;則6 user_version 為 1
    assert any("qwen2.5:7b" in record.getMessage() for record in caplog.records)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
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
