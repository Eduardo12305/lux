## ADR-003: asyncio.Lock per session_id for Slot Isolation

**Status:** Accepted

**Context:** Multiple concurrent conversations must not interfere with each other. Each session has its own model slot (a loaded model instance with KV cache and context window). Operations within a session must be serialized to avoid race conditions on the slot state, but different sessions should run independently and concurrently.

**Decision:** Use an `asyncio.Lock` per `session_id` stored in a dictionary (`dict[str, asyncio.Lock]`). Before any operation on a session's slot, acquire that session's lock. Different sessions hold different locks, so they do not block each other.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| asyncio.Lock per session_id | Simple, built-in, correct isolation | Potential for lock contention if sessions are long-running |
| Global asyncio.Lock | Trivial implementation | All sessions serialize, kills throughput |
| Threading locks + thread pool | Familiar to some developers | Mixing threads and asyncio invites deadlocks |
| Actor model (per-session queues) | Formal guarantees | Heavy infrastructure for a simple problem |

**Consequences:** Lock granularity is per-session, not per-operation-type. A long inference in session A blocks subsequent requests to session A but never to session B. Lock dictionary must be cleaned up when sessions are evicted to prevent memory leaks.

**Implementation:** `lux/inference/slot_manager.py`
