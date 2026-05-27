-- lux/migrations/005_reflection_tables.sql
-- Tabelas do sistema de reflexao e aprendizado continuo

CREATE TABLE IF NOT EXISTS task_reflections (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    what_worked     TEXT NOT NULL,
    what_failed     TEXT NOT NULL,
    root_cause      TEXT,
    lessons         TEXT NOT NULL,
    skill_opp_name  TEXT,
    skill_opp_score REAL,
    memory_saved    BOOLEAN DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_evolutions (
    id              TEXT PRIMARY KEY,
    skill_name      TEXT NOT NULL,
    version_before  TEXT NOT NULL,
    version_after   TEXT NOT NULL,
    trigger_task_id TEXT,
    reason          TEXT NOT NULL,
    quality_before  REAL,
    quality_after   REAL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_queue (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    source_task_id  TEXT NOT NULL,
    usefulness      REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(
    lesson, context, skill_name,
    tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS behavior_profiles (
    user_id         TEXT PRIMARY KEY,
    work_hours_dist TEXT,
    top_tools       TEXT,
    top_skills      TEXT,
    task_types      TEXT,
    correction_count INT DEFAULT 0,
    insights        TEXT,
    last_analyzed   TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_suggestions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_task_id  TEXT NOT NULL,
    dismissed       BOOLEAN DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reflections_user ON task_reflections(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_skill_queue_user  ON skill_queue(user_id, status);
CREATE INDEX IF NOT EXISTS idx_evolutions_skill  ON skill_evolutions(skill_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_suggestions ON memory_suggestions(user_id, dismissed);

INSERT INTO schema_version (version, applied_at, description)
VALUES (5, datetime('now'), 'Reflection: task_reflections, skill_evolutions, skill_queue, lessons_fts, behavior_profiles');
