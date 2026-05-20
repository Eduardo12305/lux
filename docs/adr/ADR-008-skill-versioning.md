## ADR-008: SkillVersionStore with Backup+Rollback

**Status:** Accepted

**Context:** Lux supports an extensible skill system where users and developers can install, update, and remove skills. Skills evolve over time, and a bad update can break functionality. We need a versioning system that allows safe upgrades with the ability to revert to a known-good state.

**Decision:** Implement `SkillVersionStore` backed by SQLite. Each skill installation is versioned. Before an upgrade, the store creates a full backup of the current skill files and metadata. Rollback restores from the most recent backup. The store maintains a version history log with timestamps and checksums for integrity verification.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| SQLite-backed version store with backup | Atomic transactions, proven, self-contained | Custom implementation effort |
| Git-based versioning | Full history, diff storage | Heavy dependency, complex for non-devs |
| File-system snapshots (rsync) | Simple | No metadata, no atomicity guarantees |
| No versioning (overwrite on update) | Trivial | No safety net, bad updates are permanent |

**Consequences:** Users can confidently upgrade skills knowing rollback is one command away. Backup files consume disk space proportional to skill size, but old backups are pruned after N versions (configurable). Checksum verification prevents corruption from being silently persisted.

**Implementation:** `lux/skills/version_store.py`
