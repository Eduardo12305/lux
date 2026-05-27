-- lux/migrations/003_auth_system.sql
-- Tabelas completas de auth, speaker verification e permissoes

-- Estende password_hashes com campos adicionais
ALTER TABLE password_hashes ADD COLUMN pin_hash TEXT;
ALTER TABLE password_hashes ADD COLUMN failed_attempts INT NOT NULL DEFAULT 0;
ALTER TABLE password_hashes ADD COLUMN locked_until TEXT;
ALTER TABLE password_hashes ADD COLUMN password_changed_at TEXT;
ALTER TABLE password_hashes ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0;

-- Perfis de voz (embeddings serializados como JSON)
CREATE TABLE IF NOT EXISTS voice_profiles (
    user_id          TEXT PRIMARY KEY REFERENCES user_profiles(user_id),
    centroid         TEXT NOT NULL,
    n_samples        INT NOT NULL,
    estimated_eer    REAL,
    quality          TEXT NOT NULL,
    enrolled_at      TEXT NOT NULL,
    last_updated     TEXT NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT 1
);

-- Amostras individuais de enrollment
CREATE TABLE IF NOT EXISTS voice_samples (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES user_profiles(user_id),
    embedding        TEXT NOT NULL,
    snr_db           REAL,
    duration_s       REAL,
    phrase_id        INT,
    created_at       TEXT NOT NULL
);

-- Sessoes de autenticacao ativas
CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id       TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES user_profiles(user_id),
    role             TEXT NOT NULL,
    auth_method      TEXT NOT NULL,
    voice_confidence REAL,
    channel          TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    last_activity    TEXT NOT NULL,
    last_voice_check TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT 1,
    revoked_at       TEXT
);

-- Log de auditoria (append-only)
CREATE TABLE IF NOT EXISTS audit_log (
    id               TEXT PRIMARY KEY,
    user_id          TEXT,
    event_type       TEXT NOT NULL,
    channel          TEXT,
    details          TEXT NOT NULL,
    ip_or_source     TEXT,
    created_at       TEXT NOT NULL
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user    ON auth_sessions(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at) WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_audit_log_user        ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_type        ON audit_log(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_voice_samples_user    ON voice_samples(user_id, created_at DESC);

INSERT INTO schema_version (version, applied_at, description)
VALUES (3, datetime('now'), 'Auth system: auth_sessions, voice_profiles, voice_samples, audit_log, extended password_hashes');
