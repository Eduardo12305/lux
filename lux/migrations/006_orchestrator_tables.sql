-- lux/migrations/006_orchestrator_tables.sql
-- Tabelas do Task Orchestrator

CREATE TABLE IF NOT EXISTS managed_tasks (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    description      TEXT NOT NULL,
    priority         TEXT NOT NULL,
    status           TEXT NOT NULL,
    dependencies     TEXT,
    dependents       TEXT,
    toolsets         TEXT,
    subagent_task_id TEXT,
    subagent_session_id TEXT,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    completed_at     TEXT,
    result_summary   TEXT,
    error            TEXT
);

CREATE INDEX IF NOT EXISTS idx_managed_tasks_user   ON managed_tasks(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_managed_tasks_status ON managed_tasks(status, priority);

INSERT INTO schema_version (version, applied_at, description)
VALUES (6, datetime('now'), 'Orchestrator: managed_tasks');
