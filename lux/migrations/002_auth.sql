-- lux/migrations/002_auth.sql
-- Whitelist e pairing codes para sistema de auth

CREATE TABLE IF NOT EXISTS whitelist (
    platform TEXT NOT NULL,
    user_id  TEXT NOT NULL,
    label    TEXT DEFAULT '',
    added_at TEXT NOT NULL,
    PRIMARY KEY (platform, user_id)
);

CREATE TABLE IF NOT EXISTS pairing_codes (
    code        TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    platform    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_limits (
    user_id    TEXT NOT NULL,
    endpoint   TEXT NOT NULL,
    window_start TEXT NOT NULL,
    count      INT NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, endpoint, window_start)
);

CREATE TABLE IF NOT EXISTS password_hashes (
    user_id   TEXT PRIMARY KEY,
    hash      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO schema_version (version, applied_at, description)
VALUES (2, datetime('now'), 'Auth tables: whitelist, pairing_codes, rate_limits, password_hashes');
