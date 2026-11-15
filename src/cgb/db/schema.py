"""資料表(contracts/store.dbml)。"""

import logging
import sqlite3

_LOG = logging.getLogger(__name__)

_SESSIONS = """
CREATE TABLE sessions (
    name TEXT PRIMARY KEY,
    runtime_type_gpu TEXT NOT NULL CHECK (runtime_type_gpu IN ('T4', 'L4', 'G4', 'A100', 'H100')),
    runtime_type_high_mem INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'opening'
        CHECK (state IN ('opening', 'ready', 'reconnecting', 'ending', 'ended', 'open_failed', 'lost')),
    active_slot INTEGER UNIQUE,
    step TEXT CHECK (step IN ('ending_previous', 'allocating', 'starting_ollama', 'connecting', 'verifying')),
    end_reason TEXT,
    reason_code TEXT,
    message TEXT,
    opened_at TEXT NOT NULL,
    ready_at TEXT,
    ended_at TEXT,
    last_request_at TEXT,
    reconnect_started_at TEXT,
    reconnect_deadline TEXT,
    release_warning_reason_code TEXT,
    release_warning_message TEXT,
    release_warning_detected_at TEXT
)
"""

_SESSION_TRANSITIONS = """
CREATE TABLE session_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT NOT NULL REFERENCES sessions (name) ON DELETE CASCADE,
    at TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('opening', 'ready', 'reconnecting', 'ending', 'ended', 'open_failed', 'lost')),
    step TEXT CHECK (step IN ('ending_previous', 'allocating', 'starting_ollama', 'connecting', 'verifying')),
    end_reason TEXT,
    reason_code TEXT
)
"""

_DOWNLOAD_JOBS = """
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT REFERENCES sessions (name) ON DELETE CASCADE,
    model TEXT NOT NULL,
    pending_model TEXT,
    queue_position INTEGER NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'downloading', 'completed', 'failed')),
    reason_code TEXT,
    message TEXT,
    origin TEXT NOT NULL DEFAULT 'user' CHECK (origin IN ('user', 'restore', 'auto')),
    preload_on_complete INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
)
"""

# 001 的 download_jobs 欄位,遷移時依名稱複製(不能依位置:session_name 插在中間)
_DOWNLOAD_JOBS_V0_COLUMNS = (
    "id, model, pending_model, queue_position, size_bytes, state, reason_code, message,"
    " origin, preload_on_complete, added_at, started_at, finished_at"
)

# 全新庫的 DDL 與既有庫的 ADD COLUMN 共用同一份欄位定義
_CURATED_AUTO_DOWNLOAD_COLUMN = "auto_download INTEGER NOT NULL DEFAULT 0 CHECK (auto_download IN (0, 1))"

_CURATED_MODELS = f"""
CREATE TABLE curated_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    recommended_runtime_type_gpu TEXT CHECK (recommended_runtime_type_gpu IN ('T4', 'L4', 'G4', 'A100', 'H100')),
    recommended_runtime_type_high_mem INTEGER,
    {_CURATED_AUTO_DOWNLOAD_COLUMN}
)
"""

_AUTO_DOWNLOAD_RESULTS = """
CREATE TABLE auto_download_results (
    session_name TEXT PRIMARY KEY REFERENCES sessions (name) ON DELETE CASCADE,
    target_count INTEGER NOT NULL CHECK (target_count >= 0),
    state TEXT NOT NULL DEFAULT 'running' CHECK (state IN ('running', 'done')),
    dismissed INTEGER NOT NULL DEFAULT 0 CHECK (dismissed IN (0, 1)),
    finished_at TEXT
)
"""

_AUTO_DOWNLOAD_ITEMS = """
CREATE TABLE auto_download_items (
    session_name TEXT NOT NULL REFERENCES auto_download_results (session_name) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    model TEXT NOT NULL,
    reason TEXT CHECK (
        reason IN ('DISK_SPACE_INSUFFICIENT', 'SIZE_UNAVAILABLE', 'MAY_NOT_FIT', 'DISK_SPACE_UNKNOWN')
    ),
    reason_code TEXT,
    message TEXT,
    size_bytes INTEGER,
    free_disk_bytes INTEGER,
    vram_bytes INTEGER,
    PRIMARY KEY (session_name, position)
)
"""

_SETTINGS = """
CREATE TABLE settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    idle_timeout_minutes INTEGER NOT NULL DEFAULT 30,
    low_balance_threshold REAL NOT NULL DEFAULT 10
)
"""

_USAGE_SNAPSHOTS = """
CREATE TABLE usage_snapshots (
    -- WITHOUT ROWID:INTEGER PRIMARY KEY 不再是 rowid 的別名,沒寫 id 時才會用 DEFAULT 1、不會自動遞增(Q76 只留最後一筆)
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    balance REAL NOT NULL,
    rate_per_hour REAL NOT NULL,
    read_at TEXT NOT NULL
) WITHOUT ROWID
"""


def create_schema(conn: sqlite3.Connection) -> None:
    # WAL 記在資料庫檔裡,之後新開的連線也沿用(research.md R10)
    conn.execute("PRAGMA journal_mode=WAL")
    if conn.execute("PRAGMA user_version").fetchone()[0] != 0:
        return
    if _has_table(conn, "sessions"):
        _migrate_v0_to_v1(conn)
    else:
        _create_fresh(conn)


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _create_fresh(conn: sqlite3.Connection) -> None:
    """全新資料庫:直接建這一版(contracts/store.dbml)的表與索引,最後設 user_version = 1。"""
    conn.execute(_SESSIONS)
    conn.execute("CREATE INDEX idx_sessions_opened_at ON sessions (opened_at)")
    conn.execute("CREATE INDEX idx_sessions_state ON sessions (state)")
    conn.execute(_SESSION_TRANSITIONS)
    conn.execute("CREATE INDEX idx_session_transitions_session ON session_transitions (session_name, at)")
    conn.execute(_DOWNLOAD_JOBS.format(name="download_jobs"))
    _create_download_jobs_indexes(conn)
    conn.execute(_CURATED_MODELS)
    conn.execute("CREATE UNIQUE INDEX uq_curated_models_name_ci ON curated_models (lower(name))")
    conn.execute(_AUTO_DOWNLOAD_RESULTS)
    conn.execute(_AUTO_DOWNLOAD_ITEMS)
    conn.execute(_SETTINGS)
    # 第一次啟動才以預設值寫入;之後的啟動不覆寫使用者改過的設定(FR-027)
    conn.execute("INSERT INTO settings (id) VALUES (1)")
    conn.execute(_USAGE_SNAPSHOTS)
    conn.execute("PRAGMA user_version = 1")


def _migrate_v0_to_v1(conn: sqlite3.Connection) -> None:
    """既有資料庫(001~003 建的,user_version 為 0):重建 download_jobs(SQLite 不能改 CHECK),session_name 留 NULL;
    精選清單補 auto_download 欄與名稱唯一索引,並建自動下載的兩張新表。

    在一個交易裡做,任何一步失敗整個 rollback、原例外往上丟(plan.md Q39);`connect` 是
    `isolation_level=None`,不會自動開交易,所以明寫 BEGIN。
    """
    conn.execute("BEGIN")
    try:
        _rebuild_download_jobs(conn)
        _migrate_curated_models(conn)
        conn.execute(_AUTO_DOWNLOAD_RESULTS)
        conn.execute(_AUTO_DOWNLOAD_ITEMS)
        conn.execute("PRAGMA user_version = 1")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _migrate_curated_models(conn: sqlite3.Connection) -> None:
    """精選清單:補 auto_download 欄(已有就不再加,R7)、去掉只差大小寫的重複、建不分大小寫的唯一索引。"""
    if "auto_download" not in [row[1] for row in conn.execute("PRAGMA table_info(curated_models)")]:
        conn.execute(f"ALTER TABLE curated_models ADD COLUMN {_CURATED_AUTO_DOWNLOAD_COLUMN}")
    _drop_curated_name_duplicates(conn)
    conn.execute("CREATE UNIQUE INDEX uq_curated_models_name_ci ON curated_models (lower(name))")


def _rebuild_download_jobs(conn: sqlite3.Connection) -> None:
    conn.execute(_DOWNLOAD_JOBS.format(name="download_jobs_new"))
    conn.execute(
        f"INSERT INTO download_jobs_new ({_DOWNLOAD_JOBS_V0_COLUMNS}) SELECT {_DOWNLOAD_JOBS_V0_COLUMNS} FROM download_jobs"
    )
    conn.execute("DROP TABLE download_jobs")
    conn.execute("ALTER TABLE download_jobs_new RENAME TO download_jobs")
    _drop_pending_model_duplicates(conn)
    _create_download_jobs_indexes(conn)


def _drop_pending_model_duplicates(conn: sqlite3.Connection) -> None:
    """只差大小寫的排隊中、下載中項目,每組只留 id 最小的一筆,刪掉的名稱寫進日誌(plan.md Q40)。

    只看 pending_model 不是 NULL 的列;完成、失敗的項目不分組、不刪。
    """
    duplicates = conn.execute(
        "SELECT id, pending_model FROM download_jobs WHERE pending_model IS NOT NULL"
        " AND id NOT IN (SELECT min(id) FROM download_jobs WHERE pending_model IS NOT NULL GROUP BY lower(pending_model))"
    ).fetchall()
    for job_id, pending_model in duplicates:
        conn.execute("DELETE FROM download_jobs WHERE id = ?", (job_id,))
        _LOG.warning("升級資料庫時刪除只差大小寫的重複下載項目:%s(id %s)", pending_model, job_id)


def _drop_curated_name_duplicates(conn: sqlite3.Connection) -> None:
    """只差大小寫的精選名稱,每組只留 id 最小的一筆,刪掉的名稱寫進日誌(plan.md Q40)。"""
    duplicates = conn.execute(
        "SELECT id, name FROM curated_models WHERE id NOT IN (SELECT min(id) FROM curated_models GROUP BY lower(name))"
    ).fetchall()
    for curated_id, name in duplicates:
        conn.execute("DELETE FROM curated_models WHERE id = ?", (curated_id,))
        _LOG.warning("升級資料庫時刪除只差大小寫的重複精選名稱:%s(id %s)", name, curated_id)


def _create_download_jobs_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX idx_download_jobs_state ON download_jobs (state)")
    conn.execute("CREATE INDEX idx_download_jobs_session ON download_jobs (session_name)")
    conn.execute("CREATE UNIQUE INDEX uq_download_jobs_pending_model_ci ON download_jobs (lower(pending_model))")
