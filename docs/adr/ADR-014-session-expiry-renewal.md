## ADR-014: Politica de Expiracao de Sessao com Renovacao por Voz Continua

**Status:** Accepted

**Context:** Sessão de voz expira em 24h, mas sessão ativa com verificação contínua deve ser renovada.

**Decision:** `last_activity` atualizado a cada mensagem. `expires_at` renovado (sliding window de 24h) se `last_activity < 1h` e verificação contínua passou. GUEST mantém expiração hard de 4h.

**Consequences:** Sessões de voz são renovadas automaticamente enquanto o usuário continua falando. Sessões GUEST nunca são renovadas — devem reautenticar a cada 4h.

**Implementation:** `lux/auth/session_store.py:update_activity()` + `lux/speaker/continuous.py`
