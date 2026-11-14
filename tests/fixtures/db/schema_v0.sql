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
);
CREATE INDEX idx_sessions_opened_at ON sessions (opened_at);
CREATE INDEX idx_sessions_state ON sessions (state);
CREATE TABLE session_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT NOT NULL REFERENCES sessions (name) ON DELETE CASCADE,
    at TEXT NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('opening', 'ready', 'reconnecting', 'ending', 'ended', 'open_failed', 'lost')),
    step TEXT CHECK (step IN ('ending_previous', 'allocating', 'starting_ollama', 'connecting', 'verifying')),
    end_reason TEXT,
    reason_code TEXT
);
CREATE INDEX idx_session_transitions_session ON session_transitions (session_name, at);
CREATE TABLE download_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    pending_model TEXT UNIQUE,
    queue_position INTEGER NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'downloading', 'completed', 'failed')),
    reason_code TEXT,
    message TEXT,
    origin TEXT NOT NULL DEFAULT 'user' CHECK (origin IN ('user', 'restore')),
    preload_on_complete INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX idx_download_jobs_state ON download_jobs (state);
CREATE TABLE curated_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    recommended_runtime_type_gpu TEXT CHECK (recommended_runtime_type_gpu IN ('T4', 'L4', 'G4', 'A100', 'H100')),
    recommended_runtime_type_high_mem INTEGER
);
CREATE TABLE settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    idle_timeout_minutes INTEGER NOT NULL DEFAULT 30,
    low_balance_threshold REAL NOT NULL DEFAULT 10
);
CREATE TABLE usage_snapshots (
    -- WITHOUT ROWID:INTEGER PRIMARY KEY 不再是 rowid 的別名,沒寫 id 時才會用 DEFAULT 1、不會自動遞增(Q76 只留最後一筆)
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    balance REAL NOT NULL,
    rate_per_hour REAL NOT NULL,
    read_at TEXT NOT NULL
) WITHOUT ROWID;
INSERT INTO settings (id) VALUES (1);
