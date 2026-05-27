-- lux/migrations/004_platform_links.sql
-- Memoria unificada: linka plataformas ao mesmo perfil Lux

CREATE TABLE IF NOT EXISTS platform_links (
    platform          TEXT NOT NULL,
    platform_user_id  TEXT NOT NULL,
    lux_user_id       TEXT NOT NULL REFERENCES user_profiles(user_id),
    linked_at         TEXT NOT NULL,
    PRIMARY KEY (platform, platform_user_id)
);

CREATE INDEX IF NOT EXISTS idx_platform_links_lux ON platform_links(lux_user_id);

INSERT INTO schema_version (version, applied_at, description)
VALUES (4, datetime('now'), 'Platform links: unified memory across Telegram/Discord/CLI');
