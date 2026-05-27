## ADR-012: Liveness Detection (Anti-Replay) para Speaker Verification

**Status:** Accepted

**Context:** ECAPA-TDNN verifica correspondência de padrão vocal mas não detecta replay attacks (gravação reproduzida). Para um assistente pessoal local com acesso físico ao dispositivo, o risco é baixo.

**Decision:** Documentar como limitação conhecida (known limitation). Implementar desafio verbal aleatório como feature opcional (`LUX_LIVENESS_CHALLENGE=false` por padrão).

**Consequences:** Atacante com acesso físico ao microfone pode burlar verificação de voz com gravação prévia — cenário de ameaça em que a segurança física já está comprometida.

**Implementation:** `lux/speaker/verifier.py` — desafio verbal desabilitado por padrão.
