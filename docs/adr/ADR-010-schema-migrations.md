## ADR-010: SchemaVersionManager for Database Migrations

**Status:** Accepted

**Context:** Lux's SQLite schema will evolve across versions. We need a reliable way to apply schema changes without data loss, track which migrations have been applied, and prevent running mismatched code against an outdated schema.

**Decision:** Implement `SchemaVersionManager` that reads migration files from a `migrations/` directory, compares applied versions in a `schema_version` table, and runs pending migrations in order within a transaction. Each migration is a numbered SQL file with an optional Python post-processing hook. Migrations are irreversible (forward-only) to keep complexity manageable.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| Custom SchemaVersionManager | Full control, zero external deps, lightweight | Custom code to maintain |
| Alembic | Industry standard, battle-tested | Heavy dependency, SQLite support is secondary, async awkward |
| Flyway | Cross-DB, mature | Java dependency, separate process, overkill |
| Schema-as-code (Django-style models) | Declarative | Requires ORM, tight coupling |

**Consequences:** All schema changes go through migration files, which are source-controlled. The `schema_version` table serves as a single source of truth for database state. Forward-only migrations mean rollback requires restoring from backup (which we already have via ADR-008's backup patterns). Migration failures leave the database in its previous consistent state due to transactional application.

**Implementation:** `lux/storage/migrations.py`
