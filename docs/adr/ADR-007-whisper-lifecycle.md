## ADR-007: Atomic Refcount WhisperLifecycleManager

**Status:** Accepted

**Context:** Whisper models (STT) are large and memory-intensive. Running multiple instances wastes GPU/CPU memory. However, loading and unloading the model on every request incurs prohibitive latency. We need a lifecycle manager that keeps the model warm while there are active users and unloads it when idle, without race conditions during concurrent load/unload decisions.

**Decision:** Implement `WhisperLifecycleManager` with an atomic reference counter. Each active STT session increments the refcount on acquisition and decrements on release. When the refcount hits zero, an idle timer starts. If no new session starts before the timer expires, the model is unloaded. All refcount operations use `asyncio.Lock` to prevent races.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| Atomic refcount + idle timer | Predictable, no wasteful loads, proven pattern | Timer tuning is environment-dependent |
| Always-loaded | Zero acquisition latency | Wastes memory for inactive users |
| Load-on-demand, immediate unload | Minimal memory footprint | High latency on every request, thrashing |
| LRU cache with weak references | Pythonic, automatic | No control over unload timing, GC-dependent |

**Consequences:** The refcount approach ensures the model stays loaded as long as at least one session needs it, then gracefully unloads after a configurable idle period. The `asyncio.Lock` serializes load/unload transitions, preventing double-load bugs. Memory is freed when genuinely not needed.

**Implementation:** `lux/voice/lifecycle.py`
