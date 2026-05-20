## ADR-001: aiosqlite for Async SQLite

**Status:** Accepted

**Context:** Lux needs persistent local storage accessible from async Python code. SQLite is the obvious embedded database choice, but the standard `sqlite3` module blocks the event loop on every query. We needed an async-compatible driver that integrates naturally with `asyncio`.

**Decision:** Use `aiosqlite`, a wrapper around the standard `sqlite3` module that executes all database operations in a background thread, exposing a native `async`/`await` API.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| aiosqlite | Mature, thin wrapper over stdlib, no C extensions | Thread-based, not truly async I/O |
| sqlite3 (stdlib) + run_in_executor | No extra dependency | Boilerplate, easy to forget, no connection management |
| SQLAlchemy + aiosqlite | ORM, migrations | Heavy dependency for what we need |
| asyncpg (PostgreSQL) | Truly async, powerful | Requires external server, overkill for local storage |

**Consequences:** Acceptable trade-off of thread-pool based execution over raw async I/O. No need for an external database server. The `aiosqlite` API provides context-manager connections and row factories that match our ergonomic needs.

**Implementation:** `lux/storage/database.py`
