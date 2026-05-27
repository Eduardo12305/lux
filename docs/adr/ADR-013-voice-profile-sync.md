## ADR-013: Sincronizacao de Voice Profile entre Sessoes Paralelas

**Status:** Accepted

**Context:** Duas sessões ativas podem chamar `update_profile()` simultaneamente, causando cálculo de centroide com dados parciais.

**Decision:** `asyncio.Lock` por `user_id` no `VoiceProfileStore.update_centroid()`. Similar à solução do MemoryManager para escritas concorrentes em MEMORY.md.

**Consequences:** Escritas no voice profile são serializadas por usuário. Leitura não bloqueia escrita. Trade-off: overhead mínimo de lock para um único usuário por vez.

**Implementation:** `lux/speaker/profile_store.py:47` — `_locks: dict[str, asyncio.Lock]`
