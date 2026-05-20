-- lux/migrations/001_initial.sql
-- Schema inicial do Lux v1.0.0

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    channel         TEXT NOT NULL,
    parent_id       TEXT REFERENCES sessions(id),
    lineage_root    TEXT,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    message_count   INT DEFAULT 0,
    tokens_used     INT DEFAULT 0,
    iterations_used INT DEFAULT 0,
    compressed      BOOLEAN DEFAULT FALSE,
    compression_count INT DEFAULT 0,
    summary         TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    thinking        TEXT,
    tool_calls      TEXT,
    tool_call_id    TEXT,
    model_used      TEXT,
    tokens_prompt   INT,
    tokens_completion INT,
    latency_ms      INT,
    timestamp       TEXT NOT NULL,
    iteration       INT,
    task_id         TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, thinking,
    content='messages', content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, thinking)
    VALUES (new.rowid, new.content, new.thinking);
END;

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id          TEXT PRIMARY KEY,
    username         TEXT NOT NULL UNIQUE,
    display_name     TEXT NOT NULL,
    role             TEXT NOT NULL DEFAULT 'user',
    preferred_lang   TEXT NOT NULL DEFAULT 'pt-BR',
    response_style   TEXT NOT NULL DEFAULT 'balanced',
    formality        TEXT NOT NULL DEFAULT 'casual',
    voice_enabled    BOOLEAN NOT NULL DEFAULT 0,
    listening_mode   TEXT NOT NULL DEFAULT 'push_to_talk',
    preferred_voice  TEXT DEFAULT 'pt_BR-faber-medium',
    preferred_channel TEXT NOT NULL DEFAULT 'cli',
    enabled_toolsets TEXT NOT NULL DEFAULT '["web","tasks","calendar","memory_tools","skills","system"]',
    approval_patterns TEXT NOT NULL DEFAULT '[]',
    disabled_skills  TEXT NOT NULL DEFAULT '[]',
    work_hours_start TEXT,
    work_hours_end   TEXT,
    timezone         TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    total_sessions   INT NOT NULL DEFAULT 0,
    total_tokens     INT NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    last_seen        TEXT
);

CREATE TABLE IF NOT EXISTS cron_jobs (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    name             TEXT NOT NULL,
    prompt           TEXT NOT NULL,
    schedule         TEXT NOT NULL,
    skills           TEXT NOT NULL DEFAULT '[]',
    toolsets         TEXT NOT NULL DEFAULT '[]',
    delivery_channel TEXT NOT NULL,
    delivery_target  TEXT NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT 1,
    last_run         TEXT,
    next_run         TEXT NOT NULL,
    run_count        INT NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    content          TEXT NOT NULL,
    fire_at          TEXT NOT NULL,
    channel          TEXT NOT NULL,
    fired            BOOLEAN NOT NULL DEFAULT 0,
    fired_at         TEXT,
    snoozed_count    INT NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trajectories (
    id               TEXT PRIMARY KEY,
    task_id          TEXT NOT NULL,
    session_id       TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    steps            TEXT NOT NULL,
    final_response   TEXT,
    quality_score    REAL,
    iterations_used  INT,
    tokens_used      INT,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session  ON messages(session_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user     ON messages(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user     ON sessions(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_lineage  ON sessions(lineage_root);
CREATE INDEX IF NOT EXISTS idx_reminders_fire    ON reminders(fire_at) WHERE fired = 0;
CREATE INDEX IF NOT EXISTS idx_cron_next         ON cron_jobs(next_run) WHERE is_active = 1;

INSERT INTO schema_version (version, applied_at, description)
VALUES (1, datetime('now'), 'Schema inicial do Lux v1.0.0');
