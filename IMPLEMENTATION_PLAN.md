# IMPLEMENTATION_PLAN.md — Projeto Lux v2.0
# Gerado automaticamente como Passo 1 do Cenário A
# Data: 2026-05-19

---

## 1. GAPS DE ARQUITETURA IDENTIFICADOS

Cada gap do documento foi analisado e uma decisão técnica foi tomada:

---

### GAP 1 — Biblioteca de SQLite Async

**Problema:** A arquitetura usa SQLite + FTS5 para session storage e busca textual, mas não especifica qual biblioteca Python usar. As operações de DB são chamadas de dentro do agent loop assíncrono (async/await), então é obrigatório usar uma biblioteca async para não bloquear o event loop.

**Decisão:** `aiosqlite`

**Justificativa:**
- `aiosqlite` é puro async, não requer thread pool — essencial para operações de DB dentro do agent loop que não deve ser bloqueado
- FTS5 funciona nativamente com `aiosqlite` (basta executar as queries SQL de criação das virtual tables)
- `databases` adiciona uma camada de abstração desnecessária e não expõe o FTS5 diretamente (requer raw SQL de qualquer forma)
- `sqlalchemy[asyncio]` é pesado demais (~3MB extra) para o que precisamos — o schema é simples e usamos raw SQL para FTS5
- `aiosqlite` é a escolha mais leve (~50KB), madura (5k+ stars), e usada por projetos similares

**Alternativas rejeitadas:**
| Biblioteca | Rejeitada porque |
|---|---|
| `databases` | Encapsula demais; FTS5 requer raw SQL mesmo |
| `sqlalchemy[asyncio]` | Overhead de ORM desnecessário; ~3MB; complexidade extra para migrations |
| `sqlite3` (sync) | Bloqueia o event loop; exigiria `run_in_executor` para cada operação |

**Impacto em outros módulos:**
- `memory/session_db.py`: usa `aiosqlite` diretamente
- `agent/state.py`: `AgentState.to_openai_messages()` é sync, não afetado
- Nenhum outro módulo acessa SQLite diretamente

---

### GAP 2 — Serialização do AgentState para Checkpoint

**Problema:** A arquitetura menciona checkpoints (`checkpoint_path` no `AgentState`) mas não especifica formato de serialização. O `AgentState` contém objetos complexos (dataclasses aninhados, `asyncio.Event`, referências a managers).

**Decisão:** `dataclasses_json` + exclusão seletiva de campos não serializáveis

**Justificativa:**
- `dataclasses_json` serializa dataclasses diretamente para JSON, sem boilerplate de `to_dict()`
- JSON é human-readable (útil para debugging de checkpoints) e versionável (ao contrário de pickle)
- Campos não serializáveis (`interrupt_event: asyncio.Event`, referências a managers) são marcados com `exclude=lambda` ou `field(metadata=config(exclude=True))`
- `orjson` seria mais rápido mas não suporta dataclasses nativamente — exigiria serializers manuais
- `pickle` é inseguro e quebra entre versões de Python
- `msgpack` é binário, não debugável, e não suporta dataclasses nativamente

**Implementação:**
- Cada dataclass em `agent/state.py` herda de uma `SerializableMixin` com `to_json()` e `from_json()`
- `asyncio.Event` é reconstruído no `from_json()` (sempre começa como `not set`)
- Referências a managers (`memory_manager`, `tool_registry`, etc.) são resolvidas via DI no `from_json()`
- Checkpoints são salvos em `~/.lux/checkpoints/{session_id}_{timestamp}.json`

**Impacto:**
- `agent/state.py`: todos os dataclasses ganham métodos de serialização
- `agent/agent.py`: métodos `save_checkpoint()` e `load_checkpoint()`
- Interface CLI: comando `/checkpoint`

---

### GAP 3 — Gerenciamento de Contexto de llama-server (Isolamento de KV Cache)

**Problema:** Com `--parallel 2` no llama-server 14B, dois usuários/sessões compartilham o mesmo processo. O llama.cpp usa slot_id para isolar KV cache entre requests, mas a arquitetura não especifica como mapear session_id → slot_id, nem o que acontece quando ambos os slots estão ocupados.

**Decisão:** `slot_id` por session_id na camada `llama_client.py`, com fila de espera

**Justificativa:**
- O llama-server já gerencia slots internamente via `/slots` API — cada request pode opcionalmente especificar `slot_id`
- Mapeamos `session_id` → `slot_id` no `LlamaClient`: uma sessão sempre usa o mesmo slot, preservando o KV cache
- Quando ambos os slots estão ocupados, o terceiro request aguarda em `asyncio.Queue` com timeout de 30s
- Isso é mais simples que `llama-swap` (que exigiria proxy extra) e mais eficiente que um servidor por usuário (VRAM proibitiva)
- O `--no-context-shift` garante que o llama-server nunca descarta contexto silenciosamente — se o contexto estourar, recebemos erro e podemos comprimir

**Implementação (CORRIGIDA — race condition eliminada):**
```python
class LlamaClient:
    _slot_sessions: dict[str, int] = {}  # session_id → slot_id
    _available_slots: asyncio.Queue[int]  # slots livres
    _acquisition_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    # defaultdict(asyncio.Lock) não funciona — Lock() precisa ser criado sob demanda
    
    async def acquire_slot(self, session_id: str) -> int:
        if session_id not in self._acquisition_locks:
            self._acquisition_locks[session_id] = asyncio.Lock()
        async with self._acquisition_locks[session_id]:
            # Re-verifica dentro do lock — outro coroutine pode ter alocado
            if session_id in self._slot_sessions:
                return self._slot_sessions[session_id]
            slot = await asyncio.wait_for(self._available_slots.get(), timeout=30)
            self._slot_sessions[session_id] = slot
            return slot
    
    async def release_slot(self, session_id: str):
        if session_id in self._slot_sessions:
            await self._available_slots.put(self._slot_sessions.pop(session_id))
```
**Por que a correção é necessária:** Entre o `if session_id in self._slot_sessions` e o `await self._available_slots.get()`, há um yield point. Dois coroutines da mesma sessão podem passar pelo `if` antes do primeiro escrever em `_slot_sessions`, resultando em dois slots diferentes para a mesma sessão. O `asyncio.Lock` por session_id torna a aquisição atômica.

**Impacto:**
- `models/llama_client.py`: adiciona gestão de slots
- `agent/agent.py`: adquire slot no início da sessão, libera no `_cleanup()`
- `docker-compose.yml`: sem mudanças (continua com `--parallel 2`)

---

### GAP 4 — Formato de Saída do Qwen3 com Thinking

**Problema:** O Qwen3-14B com `--thinking` retorna `...<think>conteúdo do raciocínio</think>...` no response. A arquitetura armazena `thinking_content` no `Message` mas não especifica como parsear, exibir na CLI, ou usar no prompt.

**Decisão:** Parser de streaming com state machine, thinking visível via toggle na CLI

**Justificativa:**
- O llama-server com `--thinking` retorna o thinking content como parte do streaming — precisamos parsear `...<think>...</think>...` em tempo real, extraindo o conteúdo de raciocínio para `thinking_content` e o resto para `content`
- Na **CLI**: o thinking content é oculto por padrão, mas visível com `/think on` (toggle). Quando visível, aparece em cor diferente (dim/itálico) no terminal
- No **prompt**: o thinking content NÃO é enviado de volta para o LLM em iterações seguintes (ocuparia muito contexto). É armazenado apenas para debugging e trajetória
- Para **gateway** (Telegram/Discord): thinking nunca é enviado (seria confuso)
- O `Message.thinking_content` é populado pelo parser de streaming

**Implementação (CORRIGIDA — 4 estados explícitos + buffer de lookahead):**
```python
from enum import Enum, auto

class ThinkingState(Enum):
    IDLE = auto()       # acumulando content normal
    IN_OPEN = auto()    # viu "<" mas ainda não sabe se é "<think>"
    THINKING = auto()   # dentro de <think>...</think>
    IN_CLOSE = auto()   # viu "<" dentro de thinking, pode ser "</think>"

class ThinkingParser:
    """
    State machine para parsear thinking content do stream do Qwen3.
    
    Trata 4 estados:
      IDLE     → acumula content, detecta "<think>"
      IN_OPEN  → buffer de lookahead para confirmar "<think>" vs "<" comum
      THINKING → acumula thinking_content, detecta "</think>"
      IN_CLOSE → buffer de lookahead para confirmar "</think>" vs "<" dentro do thinking
    
    Edge cases tratados:
      - "<" legítimo dentro do thinking (ex: comparações "x < y", tags HTML)
      - "<think>" aparece tokenizado ("<", "think", ">") — buffer de lookahead cobre
      - "</think>" parcial ("</", "think", ">") — idem
      - Thinking aninhado (Qwen3 não gera, mas se gerar tratamos como erro de parse)
    """
    
    THINK_OPEN = "<think>"
    THINK_CLOSE = "</think>"
    
    def __init__(self):
        self._state = ThinkingState.IDLE
        self._buffer = ""          # acumula caracteres para match de tags
        self._thinking_parts: list[str] = []
        self._content_parts: list[str] = []
    
    def feed(self, token: str) -> tuple[Optional[str], Optional[str]]:
        """
        Retorna (thinking_token, content_token) — exatamente um é None.
        Deve ser chamado para cada token do stream do LLM.
        """
        thinking_out: Optional[str] = None
        content_out: Optional[str] = None
        
        for char in token:
            match self._state:
                case ThinkingState.IDLE:
                    if char == "<":
                        self._state = ThinkingState.IN_OPEN
                        self._buffer = "<"
                    else:
                        content_out = (content_out or "") + char
                
                case ThinkingState.IN_OPEN:
                    self._buffer += char
                    if self.THINK_OPEN.startswith(self._buffer):
                        if self._buffer == self.THINK_OPEN:
                            self._state = ThinkingState.THINKING
                            self._buffer = ""
                        # else: continua acumulando (ex: "<th" → espera "ink>")
                    else:
                        # Não era "<think>", flush do buffer como content normal
                        self._state = ThinkingState.IDLE
                        content_out = (content_out or "") + self._buffer
                        self._buffer = ""
                
                case ThinkingState.THINKING:
                    if char == "<":
                        self._state = ThinkingState.IN_CLOSE
                        self._buffer = "<"
                    else:
                        thinking_out = (thinking_out or "") + char
                
                case ThinkingState.IN_CLOSE:
                    self._buffer += char
                    if self.THINK_CLOSE.startswith(self._buffer):
                        if self._buffer == self.THINK_CLOSE:
                            self._state = ThinkingState.IDLE
                            self._buffer = ""
                        # else: continua acumulando (ex: "</th" → espera "ink>")
                    else:
                        # "<" dentro do thinking que não é "</think>", flush
                        self._state = ThinkingState.THINKING
                        thinking_out = (thinking_out or "") + self._buffer
                        self._buffer = ""
        
        return (thinking_out, content_out)
    
    def flush(self) -> tuple[str, str]:
        """Retorna (thinking_content, content) acumulado até agora."""
        # Se terminou em estado parcial, trata o buffer
        if self._buffer:
            if self._state in (ThinkingState.THINKING, ThinkingState.IN_CLOSE):
                self._thinking_parts.append(self._buffer)
            else:
                self._content_parts.append(self._buffer)
            self._buffer = ""
        return ("".join(self._thinking_parts), "".join(self._content_parts))
```

**Impacto:**
- `models/llama_client.py`: integra `ThinkingParser` no streaming
- `agent/state.py`: `Message.thinking_content` já existe, populado pelo parser
- `interfaces/cli.py`: toggle `/think on|off` para exibir thinking
- `prompt/assembler.py`: thinking NÃO vai para o system prompt

---

### GAP 5 — Estratégia de Embedding para FTS5 + Qdrant Combinados

**Problema:** A arquitetura tem dois sistemas de busca (FTS5 lexical + Qdrant semântico) mas não especifica o algoritmo de merge/ranking dos resultados.

**Decisão:** RRF (Reciprocal Rank Fusion) com peso 60% FTS5 / 40% Qdrant

**Justificativa:**
- **RRF** é o padrão da indústria para combinar resultados de múltiplos retrievers: `score(i) = 1/(k + rank_fts5(i)) + 1/(k + rank_qdrant(i))` com `k=60`
- **Pesos assimétricos (60/40)** porque FTS5 é mais confiável para recall exato (o usuário sabe o que disse), enquanto Qdrant é melhor para recall conceitual (o usuário não lembra as palavras)
- Resultados com score < threshold (0.05) são descartados
- Resultados duplicados (mesmo conteúdo) são mergeados, mantendo o maior score
- O LLM recebe os resultados mergeados já ordenados por score, com indicação da fonte (FTS5 ou semântica)

**Alternativas rejeitadas:**
| Opção | Rejeitada porque |
|---|---|
| Pesos fixos (soma ponderada) | Scores de FTS5 (bm25) e Qdrant (cosine) estão em escalas diferentes — incomparáveis |
| Resultado primário + complementar | Pode perder resultados relevantes que só aparecem no complementar |
| Apenas FTS5 | Perde recall conceitual ("algo sobre machine learning" não casa lexicalmente) |

**Implementação:**
```python
async def merge_search_results(
    fts5_results: list[SessionSearchResult],
    qdrant_results: list[MemoryChunk],
    fts5_weight: float = 0.6,
    k: int = 60,
) -> list[MergedResult]:
```

**Impacto:**
- `memory/manager.py`: adiciona `combined_search()` que chama ambos e faz merge
- `tools/implementations/memory_tools.py`: tool `combined_search` exposta ao LLM
- Testes unitários específicos para o algoritmo RRF

---

### GAP 6 — Rate Limiting do llama-server

**Problema:** Com `--parallel 2` no 14B, apenas 2 requests simultâneos são processados. Múltiplos usuários + cron jobs + subagentes podem gerar mais requests do que slots disponíveis, causando erros 503 do llama-server.

**Decisão:** `asyncio.Queue` com prioridade + `asyncio.Semaphore` por modelo

**Justificativa:**
- **Semáforo** (`asyncio.Semaphore(parallel_slots)`) como primeira linha: garante que nunca enviamos mais requests que slots
- **Queue com prioridade** como segunda linha: requests interativos (usuário esperando) têm prioridade sobre batch (cron, subagente)
- **Timeout + retry com backoff exponencial** para casos onde o semáforo não libera a tempo
- **Circuit breaker** simplificado: se o llama-server retornar 5xx 3 vezes consecutivas, pausa requests por 30s e notifica

**Alternativas rejeitadas:**
| Opção | Rejeitada porque |
|---|---|
| Apenas semáforo | Requests podem ficar bloqueados indefinidamente sem timeout |
| Apenas retry | Sem backpressure, pode sobrecarregar o servidor com retries |
| Fila sem prioridade | Cron job pode bloquear usuário interativo |

**Implementação:**
```python
class LlamaClient:
    _semaphores: dict[str, asyncio.Semaphore]  # model_name → semaphore
    _circuit_state: dict[str, CircuitState]     # model_name → state
    
    async def chat_completion(
        self, 
        messages: list[dict],
        priority: RequestPriority = RequestPriority.INTERACTIVE,
        ...
    ) -> dict:
```

**Impacto:**
- `models/llama_client.py`: semáforo, fila, circuit breaker
- `agent/agent.py`: define prioridade do request (INTERACTIVE vs BATCH)
- `cron/scheduler.py`: requests de cron sempre BATCH

---

### GAP 7 — Ciclo de Vida do Whisper

**Problema:** O Whisper é "sob demanda" mas a arquitetura não especifica: quando descarregar (timeout? threshold?), o que fazer se o load falhar por VRAM insuficiente, como sincronizar entre múltiplos usuários.

**Decisão:** `WhisperLifecycleManager` com timeout de inatividade (60s), ref-count, e graceful degradation

**Justificativa:**
- **Timeout de inatividade de 60s**: após 60s sem uso, o Whisper é descarregado automaticamente para liberar VRAM (~0.5GB)
- **Reference counting**: múltiplos usuários/sessões podem usar o Whisper simultaneamente (refcount > 0 → mantém carregado)
- **Load failure handling**: se `can_load_model("whisper-small")` retornar False, o STT falha graciosamente — retorna `None` e loga warning. O agente continua funcionando (só perde entrada de voz)
- **Lock de carregamento**: `asyncio.Lock` garante que apenas uma thread carrega o modelo por vez — evita race condition se dois usuários falam ao mesmo tempo
- **Sincronização entre usuários**: refcount é compartilhado — se user A está usando e user B também pede STT, o modelo permanece carregado até ambos terminarem + timeout

**Implementação (CORRIGIDA — acquire atômico com verificação prévia de VRAM):**
```python
class WhisperLifecycleManager:
    _refcount: int = 0
    _last_used: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _unload_task: Optional[asyncio.Task] = None
    _vram_guard: VRAMGuard  # injetado no __init__
    _stt_loader: Callable[[], Awaitable[None]]  # função que carrega o modelo
    
    async def acquire(self) -> bool:
        """
        Adquire o Whisper para uso. Retorna True se o modelo está carregado
        e pronto para transcrição, False se não foi possível carregar
        (VRAM insuficiente).
        
        ATÔMICO: refcount só é incrementado após carga bem-sucedida.
        Se retornar False, o caller deve tratar como "STT indisponível".
        """
        async with self._lock:
            if self._refcount == 0:
                # Verifica VRAM ANTES de tentar carregar
                if not await self._vram_guard.can_load_model("whisper-small", 0.5):
                    return False  # NÃO incrementa refcount
                try:
                    await self._stt_loader()
                except Exception as e:
                    logger.error(f"Falha ao carregar Whisper: {e}")
                    return False  # NÃO incrementa refcount
            self._refcount += 1
            self._last_used = time.monotonic()
            if self._unload_task and not self._unload_task.done():
                self._unload_task.cancel()
                self._unload_task = None
            return True
    
    async def release(self):
        """Libera uma referência. Se refcount chegar a 0, agenda unload após timeout."""
        async with self._lock:
            self._refcount = max(0, self._refcount - 1)
            self._last_used = time.monotonic()
            if self._refcount == 0:
                self._unload_task = asyncio.create_task(
                    self._auto_unload_after_timeout()
                )
    
    async def _auto_unload_after_timeout(self, timeout: float = 60.0):
        await asyncio.sleep(timeout)
        async with self._lock:
            if self._refcount == 0:
                await self._stt_unloader()  # descarrega o modelo da VRAM
```

**Impacto:**
- `voice/stt.py`: integra `WhisperLifecycleManager`
- `voice/pipeline.py`: `listen_once()` chama `acquire()`/`release()`
- `models/vram_guard.py`: sem mudanças (já tem `can_load_model`)
- Múltiplos usuários via gateway: refcount resolve a concorrência

---

### GAP 8 — Persistência de Configuração de Skills (Versionamento)

**Problema:** Skills criadas autonomamente são salvas em `~/.lux/skills/`. Mas: corrupção de arquivo, identificação de skills bundled vs. autônomas, rollback de skills com bug.

**Decisão:** `SkillVersionStore` com backup automático e metadata de origem

**Justificativa:**
- **Backup automático**: antes de sobrescrever um SKILL.md, o conteúdo anterior é copiado para `~/.lux/skills/.backups/{name}.{timestamp}.md.bak`
- **Metadata de origem**: skills bundled têm `author: lux-core` no frontmatter; skills autônomas têm `author: lux-agent`. O `SkillManager` filtra por origem quando necessário
- **Rollback**: o comando `/skill rollback <name>` lista backups disponíveis e restaura. Máximo de 5 backups por skill (os mais antigos são rotacionados)
- **Validação na criação**: skills criadas autonomamente passam por validador de estrutura mínima (tem frontmatter? tem `## Procedimento`? etc.) antes de serem salvas
- **Corrupção**: se o parser falhar ao carregar um SKILL.md, a skill é marcada como `broken` e não aparece na lista L0. O usuário é notificado no próximo `/doctor`

**Implementação:**
```python
class SkillVersionStore:
    MAX_BACKUPS = 5
    
    def backup(self, skill_name: str, content: str): ...
    def list_backups(self, skill_name: str) -> list[SkillBackup]: ...
    def restore(self, skill_name: str, backup_id: str) -> str: ...
    def validate_skill_md(self, content: str) -> list[str]:  # lista de erros
```

**Impacto:**
- `skills/manager.py`: usa `SkillVersionStore` em `create_skill_from_task()` e `update_skill()`
- `skills/loader.py`: validação na carga, fallback para último backup se corrompido
- `interfaces/cli.py`: comandos `/skill backup`, `/skill rollback`

---

### GAP 9 — Startup Sequence e Health Checks

**Problema:** A arquitetura não define ordem de inicialização dos serviços nem o que fazer se um serviço não responde.

**Decisão:** `StartupCoordinator` com health checks, retry com backoff, e graceful degradation

**Justificativa:**
- **Ordem de inicialização**: llama-server (14B → 1.7B) → Qdrant → Redis → gateway → scheduler. O llama-server precisa estar pronto antes de qualquer coisa porque o health check do Lux depende dele
- **Health checks**: cada serviço tem endpoint/ping específico:
  - llama-server: `GET /health` → espera HTTP 200
  - Qdrant: `GET /collections` → espera HTTP 200
  - Redis: `PING` → espera `PONG`
- **Retry com backoff**: cada serviço tem 30s de timeout total, com retries a cada 2s, 4s, 8s, 16s (exponencial)
- **Graceful degradation**: se Qdrant não subir, busca semântica é desabilitada (FTS5 continua funcionando). Se Redis não subir, gateway funciona sem cache de sessão. Se llama-server não subir → FATAL (não inicia)
- **Status report**: `StartupCoordinator` retorna dict com status de cada serviço, usado pelo `/status` e `/doctor`

**Implementação:**
```python
class StartupCoordinator:
    SERVICES = ["llama_main", "llama_aux", "qdrant", "redis"]
    
    async def startup(self) -> StartupReport:
        """Inicializa serviços na ordem correta com health checks."""
    
    async def health_check(self, service: str) -> bool: ...
    
    async def shutdown(self): ...
```

**Impacto:**
- `lux/main.py`: entry point usa `StartupCoordinator.startup()` antes de criar o agente
- `docker-compose.yml`: `depends_on` com `condition: service_healthy`
- `interfaces/cli.py`: comando `/doctor` mostra status

---

### GAP 10 — Migração de Schema do SQLite

**Problema:** O schema do SQLite vai evoluir com o tempo. A arquitetura não menciona migrações.

**Decisão:** `SchemaVersionManager` com migrations SQL versionadas, similar ao Alembic mas minimalista

**Justificativa:**
- Não precisamos de Alembic completo (SQLAlchemy dependency) — implementamos um gerenciador simples de versão de schema
- Tabela `schema_version` armazena a versão atual do schema
- Migrations são arquivos SQL em `lux/migrations/` nomeados `001_initial.sql`, `002_add_xxx.sql`, etc.
- Cada migration tem `UP` (aplicar) e `DOWN` (reverter) — como Alembic
- Na inicialização, `SchemaVersionManager` verifica a versão atual e aplica migrations pendentes em ordem
- `aiosqlite` executa as migrations dentro de uma transação — se falhar, rollback automático

**Implementação:**
```python
class SchemaVersionManager:
    async def ensure_latest(self, db: aiosqlite.Connection): ...
    async def migrate_up(self, db, from_version: int, to_version: int): ...
    async def migrate_down(self, db, from_version: int, to_version: int): ...
```

**Impacto:**
- `memory/session_db.py`: chama `SchemaVersionManager.ensure_latest()` em `_init_schema()`
- Novo diretório: `lux/migrations/`
- Sem impacto em outros módulos

---

### GAP 11 — Cold Start dos Modelos (Process Launcher)

**Problema:** O `StartupCoordinator` (GAP 9) faz health check do llama-server, mas não define quem inicia o llama-server. A arquitetura pressupõe que o llama-server já está rodando (via docker-compose ou manual), mas o `setup-lux.sh` e o comando `lux` precisam verificar se o processo está ativo e, se não estiver, iniciá-lo. Sem isso, o primeiro `lux` após um reboot falha no health check sem explicação clara.

**Decisão:** `ProcessLauncher` integrado ao `StartupCoordinator`

**Justificativa:**
- O `ProcessLauncher` verifica se o llama-server está rodando antes de tentar health check
- Se não estiver rodando, inicia com os parâmetros corretos (definidos em `config.py`)
- Aguarda warmup: 15-30s para o 14B, 5-10s para o 1.7B (polling no `/health` endpoint)
- Se o processo falhar ao iniciar (ex: modelo não encontrado, VRAM insuficiente), reporta erro claro com ação sugerida
- Suporta tanto docker-compose (verifica container) quanto processo local (verifica PID)
- Não inicia se `LUX_MANAGED_PROCESSES=false` (modo "já está rodando")

**Implementação:**
```python
class ProcessLauncher:
    """Gerencia ciclo de vida dos processos llama-server."""
    
    async def ensure_running(self, model_name: str) -> ProcessStatus:
        """
        Verifica se o llama-server para model_name está rodando.
        Se não estiver, inicia via subprocess com os parâmetros do config.
        Aguarda warmup (health check polling).
        Retorna: RUNNING, STARTING, FAILED, NOT_NEEDED
        """
    
    async def stop(self, model_name: str): ...
    
    async def stop_all(self): ...
```

**Impacto:**
- `lux/main.py`: `StartupCoordinator` ganha `ProcessLauncher` como dependência
- `config.py`: novas env vars `LUX_MANAGED_PROCESSES`, `LUX_LLAMA_SERVER_BIN`
- `scripts/setup-lux.sh`: não precisa mais iniciar llama-server manualmente
- `docker-compose.yml`: pode marcar `llama-server` como opcional (modo host)

---

## 2. DEPENDÊNCIAS CRÍTICAS DE IMPLEMENTAÇÃO

Grafo de dependências entre módulos (A → B significa "A depende de B"):

```
FASE 1 (Core Foundation):
  config.py
  constants.py
    ├── agent/state.py ─────────── (sem dependências internas)
    ├── models/llama_client.py ─── (depende de: config.py)
    ├── models/vram_guard.py ───── (depende de: config.py)
    ├── models/embedder.py ─────── (depende de: config.py)
    ├── prompt/soul.py ─────────── (depende de: constants.py)
    ├── prompt/formatting.py ───── (depende de: nada)
    ├── memory/session_db.py ───── (depende de: config.py, constants.py)
    ├── memory/manager.py ──────── (depende de: agent/state.py, memory/session_db.py, models/embedder.py)
    ├── memory/nudge.py ────────── (depende de: agent/state.py)
    ├── memory/semantic.py ─────── (depende de: config.py, models/embedder.py)
    ├── prompt/context_files.py ── (depende de: constants.py)
    ├── prompt/assembler.py ────── (depende de: agent/state.py, prompt/soul.py, prompt/formatting.py, memory/manager.py, skills/manager.py, tools/registry.py)
    └── agent/agent.py ─────────── (depende de: TODOS acima + model_router + budget + trajectory)

FASE 2 (Tools, Skills, Compressão):
  tools/base.py ────────────────── (depende de: agent/state.py)
  tools/toolsets.py ────────────── (depende de: nada)
  tools/registry.py ────────────── (depende de: tools/base.py, tools/toolsets.py, agent/state.py)
  tools/approval.py ────────────── (depende de: agent/state.py, tools/toolsets.py)
  tools/implementations/* ──────── (depende de: tools/base.py, tools/registry.py, agent/state.py)
  skills/loader.py ─────────────── (depende de: nada)
  skills/manager.py ────────────── (depende de: skills/loader.py, agent/state.py)
  skills/creator.py ────────────── (depende de: skills/manager.py, agent/state.py, models/llama_client.py)
  compression/compressor.py ────── (depende de: agent/state.py, memory/manager.py, memory/session_db.py, models/llama_client.py)
  compression/lineage.py ───────── (depende de: memory/session_db.py)
  agent/model_router.py ────────── (depende de: agent/state.py, config.py)
  agent/budget.py ──────────────── (depende de: nada)
  agent/trajectory.py ──────────── (depende de: agent/state.py, memory/session_db.py)
  agent/auxiliary_client.py ────── (depende de: models/llama_client.py, agent/model_router.py)

FASE 3 (Subagentes, Plugins, Scheduler):
  tools/implementations/subagent.py ─ (depende de: agent/agent.py, tools/base.py)
  plugins/base.py ────────────────── (depende de: agent/state.py)
  plugins/manager.py ─────────────── (depende de: plugins/base.py)
  cron/jobs.py ───────────────────── (depende de: config.py)
  cron/scheduler.py ──────────────── (depende de: cron/jobs.py, agent/agent.py)
  cron/triggers.py ───────────────── (depende de: agent/state.py, cron/scheduler.py)

FASE 4 (Voz e Gateway):
  voice/vad.py ───────────────────── (depende de: nada — bindings C)
  voice/stt.py ───────────────────── (depende de: models/vram_guard.py, config.py)
  voice/tts.py ───────────────────── (depende de: config.py)
  voice/wake_word.py ─────────────── (depende de: nada)
  voice/pipeline.py ──────────────── (depende de: voice/vad, stt, tts, wake_word, models/vram_guard)
  gateway/pairing.py ─────────────── (depende de: config.py)
  gateway/session_store.py ───────── (depende de: memory/session_db.py)
  gateway/delivery.py ────────────── (depende de: nada)
  gateway/runner.py ──────────────── (depende de: agent/agent.py, gateway/*)
  gateway/platforms/* ────────────── (depende de: gateway/runner.py)

FASE 5 (IDE, Interfaces):
  acp/protocol.py ────────────────── (depende de: nada)
  acp/server.py ──────────────────── (depende de: acp/protocol.py, agent/agent.py)
  interfaces/cli.py ──────────────── (depende de: agent/agent.py, TODOS os managers)
  interfaces/hermes_cli/* ────────── (depende de: interfaces/cli.py)

LEGENDA:
  "depende de: nada" = módulo autossuficiente, pode ser implementado primeiro
```

---

## 3. DECISÕES DE IMPLEMENTAÇÃO NÃO COBERTAS PELA ARQUITETURA

### 3.1 Framework HTTP para llama_client
**Decisão:** `httpx` com `http2=True`

- `httpx` suporta async nativo, HTTP/2, e tem API similar a `requests` (curva de aprendizado zero)
- `aiohttp` é mais rápido em benchmarks mas requer mais boilerplate e tem API diferente
- Streaming de respostas do llama-server é feito via `httpx.stream("POST", ..., json=...)`
- Timeout configurável por request (30s padrão, 120s para thinking mode)

### 3.2 Gerenciador de Dependências e Build System
**Decisão:** `uv` + `pyproject.toml` (PEP 621)

- `uv` é 10-100x mais rápido que pip, tem lock file (`uv.lock`), e suporta PEP 621
- `pyproject.toml` com `[project]` para metadados, `[tool.uv]` para dependências
- Scripts de entry point: `lux = "lux.main:main"`, `lux-gateway = "lux.gateway.runner:main"`
- Test runner: `pytest` com `pytest-asyncio` para testes async
- Linter: `ruff` (substitui flake8, isort, pyupgrade)
- Type checker: `mypy --strict`

### 3.3 Biblioteca de Embedding
**Decisão:** `sentence-transformers` para `all-MiniLM-L6-v2`

- `sentence-transformers` é a biblioteca padrão para embeddings com suporte a GPU via PyTorch
- Modelo `all-MiniLM-L6-v2` tem 384 dims, ~0.1GB VRAM, e é state-of-the-art para similaridade semântica
- Embeddings rodam localmente, sem chamada de API
- Alternativa: `fastembed` da Qdrant (mais leve, puramente ONNX) — mas `sentence-transformers` é mais maduro e usado pelo Hermes

### 3.4 Biblioteca para Fila/Redis (Gateway)
**Decisão:** `redis-py` com `asyncio` (redis[hiredis])

- Gateway usa Redis para: message queue entre plataformas, session cache, rate limiting
- `redis-py` suporta async nativo desde v4.5
- Se Redis não estiver disponível, gateway funciona sem cache (graceful degradation)

### 3.5 TUI Framework (CLI)
**Decisão:** `textual` >= 0.50

- Especificado na arquitetura. `textual` é o framework TUI mais popular para Python (25k+ stars)
- Suporta widgets ricos: input, histórico, painéis, barras de status
- Layout da CLI definido na seção 21 da arquitetura

### 3.6 Biblioteca de VAD (Voice Activity Detection)
**Decisão:** `silero-vad` via `pyaudio`

- SileroVAD é state-of-the-art para VAD (MIT license), roda em CPU (~3ms por frame)
- `pyaudio` para captura de microfone (PortAudio bindings)
- Alternativa: `webrtcvad` (mais simples, menos preciso) — Silero é superior

### 3.7 Biblioteca STT (Whisper)
**Decisão (CORRIGIDA):** Binário `whisper-cli` via `asyncio.create_subprocess_exec` (consistente com Piper TTS)

- A arquitetura especifica Whisper como binário local (`whisper.cpp`), não como biblioteca Python
- Invocamos via subprocess assíncrono: `whisper-cli -m models/ggml-small.bin -l pt -f {audio_file} --print-progress=false -otxt`
- Mesma abordagem do Piper TTS (decisão 3.8) — consistência de design
- **Rejeitado:** `whisper-cpp-python` — biblioteca de terceiros não oficial com manutenção irregular; bindings quebram com atualizações do whisper.cpp
- Modelo: `ggml-small.bin` (~466MB VRAM), baixado pelo `setup_models.sh`

### 3.8 Biblioteca TTS (Text-to-Speech)
**Decisão:** `piper-tts` via subprocess (CLI tool)

- Piper TTS é o motor de síntese de voz local mais rápido, CPU-only
- Invocamos via subprocess: `echo "texto" | piper --model pt_BR-faber-medium --output-raw -`
- Alternativa: `piper-phonemize` + Python bindings — mais complexo de instalar. Subprocess é mais portável
- Voz padrão: `pt_BR-faber-medium` (masculina, natural)

### 3.9 Biblioteca para Qdrant
**Decisão:** `qdrant-client` >= 1.9

- Client oficial, suporta async, filtros, e todos os recursos do Qdrant
- Usado em `memory/semantic.py` para busca vetorial

### 3.10 Biblioteca de Cron/Scheduling
**Decisão:** `APScheduler` 4.x com asyncio

- APScheduler é o scheduler mais popular para Python, suporta cron expressions e triggers condicionais
- v4.x tem suporte nativo a asyncio (AsyncIOScheduler)
- Alternativa: `schedule` — mais simples mas sem persistência. APScheduler suporta job stores (SQLite, Redis)

### 3.11 WebSocket Server (ACP)
**Decisão:** `websockets` (biblioteca padrão)

- `websockets` é madura, async nativa, e tem API simples
- ACP usa WebSocket para comunicação bidirecional com IDEs
- Alternativa: `aiohttp` com websocket — mas `websockets` é mais focada e leve

### 3.12 Biblioteca para Wake Word Detection
**Decisão:** `openwakeword` (MIT, CPU, ~10ms)

- `openwakeword` é state-of-the-art para wake word detection on-device
- Suporta modelos customizados (treinamos "lux" como wake word)
- Alternativa: `porcupine` (Picovoice) — requer licença comercial. `openwakeword` é MIT

---

## 4. RISCOS TÉCNICOS IDENTIFICADOS

### RISCO 1 — Deadlock no Agent Loop com Tool Calls Paralelas + Interrupção
**Descrição:** Se o usuário interromper (`interrupt_event.set()`) enquanto tool calls paralelas estão executando em `ThreadPoolExecutor`, as threads podem continuar executando com referências ao `AgentState` que está sendo modificado pelo `_cleanup()`.

**Probabilidade:** M (acontece em uso normal com `/stop` durante ferramentas longas)

**Impacto:** A (corrupção de estado, race condition, crash)

**Mitigação:**
- Tool calls usam `ThreadPoolExecutor` com `timeout` por tool
- `_cleanup()` chama `pool.shutdown(wait=False, cancel_futures=True)` (Python 3.9+)
- `AgentState` é tratado como imutável durante tool execution — resultados são acumulados em variável local e só mergeados após todas as threads terminarem
- Teste específico: `test_interrupt_during_parallel_tools`

### RISCO 2 — Conflito de Slot no llama-server
**Descrição:** Se duas sessões tentarem usar o mesmo `slot_id` (bug no mapeamento), o llama-server pode retornar resultados misturados (KV cache de uma sessão vaza para outra).

**Probabilidade:** B (só acontece com bug no `LlamaClient._slot_sessions`)

**Impacto:** A (vazamento de contexto entre usuários — grave violação de privacidade)

**Mitigação:**
- Cada `session_id` tem seu próprio `slot_id`, alocado atomicamente via `asyncio.Queue`
- `LlamaClient` loga `(session_id, slot_id)` em cada request para auditoria
- Teste: `test_slot_isolation` — duas sessões paralelas não veem o contexto uma da outra
- Se detectarmos resposta com conteúdo de outro usuário, `circuit_breaker` abre imediatamente

### RISCO 3 — Perda de Dados na Compressão por Bug no Tool Pair Rescue
**Descrição:** `_rescue_tool_pairs()` tem lógica complexa de backtracking. Se houver bug, um `tool_call` pode ser comprimido sem seu `tool_result`, invalidando o histórico para o LLM.

**Probabilidade:** M (lógica de compressão é complexa e edge cases são sutis)

**Impacto:** A (LLM recebe histórico inválido → comportamento imprevisível)

**Mitigação:**
- Testes exaustivos para `_rescue_tool_pairs()`: 15+ cenários (single pair, multiple pairs, nested, edge do buffer)
- Pós-condição verificada em runtime: após `_rescue_tool_pairs()`, todo `tool_call` em `to_compress` + `rescued` tem seu `tool_result` correspondente
- Se a verificação falhar, a compressão é abortada (não comprime — segurança > performance)

### RISCO 4 — Memory Leak no Streaming de Voz
**Descrição:** `VoicePipeline.speak_streaming()` acumula tokens em buffer. Se o LLM gerar uma resposta muito longa sem pontuação (ex: bloco de código), o buffer pode crescer indefinidamente.

**Probabilidade:** B (acontece com respostas longas sem sentence enders)

**Impacto:** M (consumo de memória, mas não crash — Python limita string a tamanho máximo)

**Mitigação:**
- Buffer máximo de 4096 caracteres — se exceder, flush forçado (sintetiza o que tem)
- `speak_streaming()` tem timeout de 300s (5 min) — depois disso, força flush e encerra
- Teste: `test_tts_buffer_overflow`

### RISCO 5 — Qwen3-14B Alucinação de Tool Calls
**Descrição:** Qwen3 pode alucinar tool calls com argumentos inválidos ou chamar ferramentas que não existem. A arquitetura delega validação ao `ToolRegistry.execute()` mas não impede que o LLM invente ferramentas.

**Probabilidade:** M (comum em LLMs, especialmente sem fine-tuning específico para as ferramentas do Lux)

**Impacto:** M (tool call falha, mas o erro é retornado ao LLM que pode corrigir)

**Mitigação:**
- `ToolRegistry.execute()` valida schema com Pydantic — argumentos inválidos → `ToolResult.error()` com detalhes
- Ferramentas não encontradas → `ToolResult.error(f"Ferramenta '{name}' não existe. Disponíveis: {lista}")`
- O LLM recebe o erro e geralmente corrige na próxima iteração
- Log de tool calls inválidas para analytics (padrões de alucinação)
- Se mais de 3 tool calls consecutivas falharem, injetamos nudge: "[SISTEMA] Verifique se as ferramentas chamadas existem e os argumentos estão corretos."

### RISCO 6 — Race Condition no MemoryManager com Múltiplas Sessões
**Descrição:** Se o mesmo usuário tiver duas sessões simultâneas (CLI + Telegram), ambas podem escrever em `MEMORY.md` ao mesmo tempo, causando corrupção de arquivo.

**Probabilidade:** B (usuário avançado com gateway ativo + CLI)

**Impacto:** M (perda de entradas de memória, arquivo corrompido)

**Mitigação:**
- `MemoryManager.apply_memory_action()` usa `asyncio.Lock` por `(user_id, target)` — escrita serializada
- Operações de leitura (`load_frozen_snapshot`) não precisam de lock
- Se o arquivo estiver corrompido (parse falha), backup é restaurado automaticamente
- Teste: `test_concurrent_memory_writes`

### RISCO 7 — Exaustão de VRAM por KV Cache Crescente
**Descrição:** O KV cache do llama-server cresce com o contexto. Se o `--no-context-shift` estiver ativo e o contexto não for comprimido a tempo, o cache pode exceder o orçamento de VRAM.

**Probabilidade:** M (em conversas longas sem compressão)

**Impacto:** A (OOM kill pelo SO ou crash do llama-server)

**Mitigação:**
- `VRAMGuard.monitor_loop()` detecta uso > 88% e força compressão de contexto
- Se > 94%, `_handle_oom()` descarrega modelos sob demanda e reduz ctx_size
- `ContextCompressor.compress()` é chamado proativamente em 50% (CLI) ou 85% (gateway)
- Teste: `test_vram_pressure_forces_compression`

### RISCO 8 — Dependência Circular PromptAssembler ↔ SkillManager ↔ ToolRegistry
**Descrição:** `PromptAssembler` precisa de `SkillManager` para lista L0 e de `ToolRegistry` para schemas ativos. `SkillManager.get_skills_list_l0()` precisa do `UserProfile` (do `AgentState`). `ToolRegistry.get_active_schemas()` também. Se mal implementado, cria ciclo de imports.

**Probabilidade:** M (comum em projetos com DI manual)

**Impacto:** M (erro de import, mas resolvível com lazy imports ou DI)

**Mitigação (CORRIGIDA — Protocol-based DI, não lazy imports):**
- **`lux/interfaces/protocols.py`** define `Protocol` classes que `PromptAssembler` espera:
  ```python
  class SkillListProvider(Protocol):
      def get_skills_list_l0(self, user: UserProfile, channel: Channel) -> list[SkillSummary]: ...
  
  class ToolSchemaProvider(Protocol):
      def get_active_schemas(self, user: UserProfile, toolsets: list[str]) -> list[dict]: ...
  
  class SoulProvider(Protocol):
      def load(self, user: UserProfile) -> str: ...
  ```
- `PromptAssembler.__init__` recebe esses callables/protocols, NUNCA as classes concretas
- `main.py` como composition root: instancia `SkillManager`, `ToolRegistry`, `SoulLoader` e os passa como dependências para `PromptAssembler`
- Nenhum módulo em `prompt/` importa de `skills/`, `tools/`, ou `agent/`
- Isso **elimina estruturalmente** o ciclo, sem workarounds de lazy import

### RISCO 9 — Incompatibilidade de Versão GGUF entre llama.cpp e modelos Qwen3
**Descrição:** Modelos Qwen3 podem usar features do formato GGUF que versões antigas do llama.cpp não suportam (ex: arquitetura nova, tokenizer novo).

**Probabilidade:** B (modelos Qwen3 são recentes, GGUF está estável)

**Impacto:** A (llama-server não carrega o modelo → Lux não funciona)

**Mitigação:**
- `scripts/setup_models.sh` baixa versões específicas dos modelos (com hash verificável)
- `llama-server` é buildado de source com versão fixa (documentada em README)
- `StartupCoordinator.health_check()` detecta falha de carga e reporta
- Documentação clara sobre versões compatíveis

### RISCO 10 — Performance do Qwen3-1.7B em Português
**Descrição:** O Qwen3-1.7B é usado para tarefas de classificação (intent, memory extraction, etc.) que exigem compreensão de português. Modelos pequenos podem ter performance ruim em pt-BR.

**Probabilidade:** M (modelo pequeno + idioma não-inglês)

**Impacto:** M (classificações erradas → comportamento subótimo, não crash)

**Mitigação:**
- Tarefas do 1.7B são de baixo risco: classificação de intent, extração de entidades, parsing de confirmação
- Se a classificação falhar, o 14B é usado como fallback (detectado por baixa confiança)
- Log de acurácia do 1.7B para monitoramento contínuo
- Possibilidade de swap futuro para modelo pt-BR fine-tuned (ex: Sabiá-7B se houver VRAM)

---

## 5. ORDEM DE IMPLEMENTAÇÃO

### Batch 1 — Tipos e Configuração (arquivos sem dependências internas)
```
1. lux/constants.py                     # LUX_HOME, paths
2. lux/config.py                         # pydantic-settings, todas as env vars
3. lux/__init__.py                       # versão, exports
4. .env.example                          # todas as variáveis
```
**Paralelizável:** Sim (3 e 4 podem ser feitos junto com 5-6)

### Batch 2 — Tipos de Dados Core (depende de: nada)
```
5. lux/agent/state.py                    # TODOS os dataclasses (~800 linhas)
   - Message, AgentState, UserProfile
   - ToolCall, ToolResult, MemoryDelta, MemoryChunk
   - Skill, SkillSummary, SkillMetadata
   - ApprovalRequest, ApprovalResult, ApprovalPattern
   - SubagentTask, TodoItem
   - ConversationResult, LLMResponse, TrajectoryStep
   - Todos os enums: Role, Channel, Task, Intent, etc.
6. lux/agent/__init__.py
7. tests/unit/test_state.py              # testes de serialização, alternação de roles
```
**Paralelizável:** Não — Batch 3 depende dos tipos definidos aqui

### Batch 3 — Modelos e Serviços Externos (depende de: state, config)
```
 8. lux/models/llama_client.py           # HTTP client + slot management + thinking parser + rate limiting (GAP 3, 4, 6)
 9. lux/models/vram_guard.py             # VRAMGuard (GAP parcial)
10. lux/models/embedder.py               # sentence-transformers wrapper
11. lux/models/__init__.py
12. lux/models/manager.py                # ModelManager (coordena llama_client + vram_guard + embedder)
13. tests/unit/test_llama_client.py
14. tests/unit/test_vram_guard.py
15. tests/unit/test_embedder.py
```
**Paralelizável:** 8, 9, 10 podem ser feitos em paralelo (dependem apenas de state + config)

### Batch 4 — Memória Core (depende de: state, config, models)
```
16. lux/migrations/001_initial.sql       # schema SQL inicial
17. lux/memory/session_db.py             # SessionDB com FTS5 + SchemaVersionManager (GAP 1, 10)
18. lux/memory/semantic.py               # Qdrant wrapper + merge RRF (GAP 5)
19. lux/memory/manager.py                # MemoryManager (GAP 5)
20. lux/memory/nudge.py                  # MemoryNudgeSystem
21. lux/memory/__init__.py
22. tests/unit/test_session_db.py
23. tests/unit/test_memory_manager.py
24. tests/unit/test_semantic.py
```
**Paralelizável:** 17 e 18 podem ser feitos em paralelo; 19 depende de ambos

### Batch 5 — Prompt e Skills Base (depende de: state, memory)
```
25. lux/prompt/soul.py                   # SOUL.md loader
26. lux/prompt/formatting.py             # helpers de formatação
27. lux/prompt/context_files.py          # ContextFileLoader
28. lux/skills/loader.py                 # parser SKILL.md + validação (GAP 8 parcial)
29. lux/skills/__init__.py
30. tests/unit/test_soul.py
31. tests/unit/test_context_files.py
32. tests/unit/test_skill_loader.py
```
**Paralelizável:** 25, 26, 27, 28 são independentes entre si

### Batch 6 — Tools e Aprovação (depende de: state)
```
33. lux/tools/base.py                    # Tool ABC
34. lux/tools/toolsets.py                # definições de Toolset
35. lux/tools/registry.py                # ToolRegistry
36. lux/tools/approval.py                # ApprovalSystem
37. lux/tools/__init__.py
38. tests/unit/test_tool_registry.py
39. tests/unit/test_approval.py
```
**Paralelizável:** 33-36 podem ser feitos na ordem listada (dependem sequencialmente mas o batch todo pode ser feito junto)

### Batch 7 — Integração: Skills Manager + PromptAssembler (depende de: state, memory, skills/loader, tools)
```
40. lux/interfaces/protocols.py          # Protocols para DI (SkillListProvider, ToolSchemaProvider, SoulProvider)
41. lux/skills/manager.py                # SkillManager com version store (GAP 8)
42. lux/skills/creator.py                # criação autônoma de skills (GAP 8)
43. lux/prompt/assembler.py              # PromptAssembler — recebe Protocols, NÃO classes concretas
44. lux/interfaces/__init__.py
45. tests/unit/test_skill_manager.py
46. tests/unit/test_prompt_assembler.py
```
**Paralelizável:** 40 é independente de tudo; 41 e 43 podem ser feitos em paralelo (43 depende apenas de 40, não de 41); 42 depende de 41

### Batch 8 — Compressão e Agente Auxiliares (depende de: state, memory, models, prompt)
```
45. lux/compression/lineage.py           # session lineage helpers
46. lux/compression/compressor.py        # ContextCompressor (GAP 3, 4)
47. lux/compression/__init__.py
48. lux/agent/model_router.py            # ModelRouter
49. lux/agent/budget.py                  # IterationBudget
50. lux/agent/trajectory.py              # TrajectorySaver
51. lux/agent/auxiliary_client.py        # AuxiliaryLLMClient
52. tests/unit/test_compressor.py
53. tests/unit/test_model_router.py
54. tests/unit/test_budget.py
```
**Paralelizável:** 45+46, 48, 49, 50, 51 são independentes entre si

### Batch 9 — Agent Loop Principal (depende de: TODOS os módulos acima)
```
55. lux/agent/agent.py                   # AIAgent — loop principal (~2000 linhas)
56. tests/unit/test_agent.py
57. tests/e2e/test_agent_loop.py         # E2E: conversa simples
```
**Paralelizável:** Não — é o ponto de integração de tudo

**Ordem interna de implementação do `agent.py` (SUB-ITENS OBRIGATÓRIOS):**
```
55.1 _init_state()                 — cria AgentState, carrega frozen snapshot, inicializa contexto
55.2 _interruptible_llm_call()     — HTTP ao llama-server com timeout + interrupt detection
55.3 _execute_single_tool()        — dispatch para ToolRegistry + approval + hooks + agent-level tools
55.4 _execute_tool_calls()         — orquestração paralela (ThreadPoolExecutor) + sequencial (interativas)
55.5 _needs_preflight_compression()— verifica threshold e dispara ContextCompressor
55.6 _get_budget_warning()         — delega para IterationBudget
55.7 _flush_pending_memory()       — aplica MemoryDelta pendentes ao MemoryManager
55.8 _finalize()                   — persiste sessão, salva trajetória, libera slot
55.9 _agent_loop()                 — loop principal que orquestra 55.1-55.8
55.10 run_conversation()           — wrapper público: init → loop → cleanup
55.11 chat()                       — interface simplificada (str → str)
55.12 save_checkpoint() / load_checkpoint() — serialização (GAP 2)
```
**Cada sub-item deve ser testável isoladamente antes de integrar ao loop.**

### Batch 10 — Implementações de Ferramentas (depende de: tools, agent)
```
58. lux/tools/implementations/terminal.py
59. lux/tools/implementations/filesystem.py
60. lux/tools/implementations/web.py
61. lux/tools/implementations/email.py
62. lux/tools/implementations/calendar.py
63. lux/tools/implementations/tasks.py
64. lux/tools/implementations/git.py
65. lux/tools/implementations/memory_tools.py
66. lux/tools/implementations/skills_tools.py
67. lux/tools/implementations/system.py
68. lux/tools/implementations/subagent.py
69. lux/tools/implementations/__init__.py
70. tests/unit/test_terminal.py
71. tests/unit/test_filesystem.py
       ... (um teste por implementação)
```
**Paralelizável:** Totalmente — cada implementação é independente

### Batch 11 — Subagentes e Plugins (depende de: agent, tools)
```
78. lux/plugins/base.py                  # Plugin ABC
79. lux/plugins/manager.py               # PluginManager
80. lux/plugins/__init__.py
81. tests/unit/test_plugins.py
```
**Paralelizável:** 78, 79 sequenciais mas podem ser feitos junto com Batch 12

### Batch 12 — Scheduler e Proatividade (depende de: agent, skills, tools)
```
82. lux/cron/jobs.py                     # CronJob, jobs.json store
83. lux/cron/scheduler.py                # CronScheduler
84. lux/cron/triggers.py                 # ProactiveTriggerEngine
85. lux/cron/__init__.py
86. tests/unit/test_scheduler.py
```
**Paralelizável:** 82, 83, 84 sequenciais

### Batch 13 — Voz (depende de: models/vram_guard, config)
```
87. lux/voice/vad.py                     # SileroVAD
88. lux/voice/wake_word.py               # WakeWordDetector
89. lux/voice/stt.py                     # WhisperSTT + lifecycle manager (GAP 7)
90. lux/voice/tts.py                     # PiperTTS
91. lux/voice/pipeline.py                # VoicePipeline
92. lux/voice/__init__.py
93. tests/unit/test_voice_pipeline.py
```
**Paralelizável:** 87-90 são independentes entre si; 91 depende de todos

### Batch 14 — Gateway (depende de: agent, memory/session_db)
```
 94. lux/gateway/pairing.py              # DM pairing / autorização
 95. lux/gateway/session_store.py        # SessionStore
 96. lux/gateway/delivery.py             # message delivery
 97. lux/gateway/platforms/telegram.py   # TelegramAdapter
 98. lux/gateway/platforms/discord.py    # DiscordAdapter
 99. lux/gateway/platforms/slack.py      # SlackAdapter
100. lux/gateway/platforms/email.py      # EmailAdapter
101. lux/gateway/platforms/webhook.py    # WebhookAdapter
102. lux/gateway/platforms/__init__.py
103. lux/gateway/runner.py               # GatewayRunner
104. lux/gateway/__init__.py
105. tests/unit/test_gateway.py
```
**Paralelizável:** 94-96, 97-101 são totalmente paralelizáveis; 103 depende de todos

### Batch 15 — ACP (IDE Integration) (depende de: agent)
```
106. lux/acp/protocol.py                 # ACPRequest/Response
107. lux/acp/server.py                   # ACPServer
108. lux/acp/__init__.py
109. tests/unit/test_acp.py
```
**Paralelizável:** Sim

### Batch 16 — Interfaces (depende de: TODOS os módulos)
```
110. lux/interfaces/cli.py               # CLI Textual (~1500 linhas)
111. lux/interfaces/gradio_ui.py         # WebUI opcional
112. lux/interfaces/hermes_cli/main.py   # subcomandos
113. lux/interfaces/hermes_cli/commands.py
114. lux/interfaces/hermes_cli/setup.py
115. lux/interfaces/hermes_cli/auth.py
116. lux/interfaces/hermes_cli/__init__.py
117. lux/interfaces/__init__.py
118. tests/unit/test_cli.py
```
**Paralelizável:** 110 e 111 podem ser feitos em paralelo (interfaces independentes)

### Batch 17 — Entry Point e Composição (depende de: TODOS)
```
119. lux/main.py                         # composition root, DI, StartupCoordinator (GAP 9)
120. tests/e2e/test_memory_persistence.py
121. tests/e2e/test_skill_progressive_disclosure.py
122. tests/e2e/test_context_compression.py
123. tests/e2e/test_voice_pipeline.py
```
**Paralelizável:** Testes E2E podem ser escritos em paralelo

### Batch 18 — Infraestrutura e Scripts
```
124. pyproject.toml
125. docker-compose.yml
126. Makefile
127. scripts/setup-lux.sh
128. scripts/setup_models.sh
129. scripts/setup_services.sh
130. scripts/create_admin.py
131. README.md
132. CHANGELOG.md
133. docs/adr/ADR-001-aiosqlite.md
134. docs/adr/ADR-002-serialization.md
135. docs/adr/ADR-003-slot-management.md
       ... (um ADR por GAP, 10 ADRs)
```

---

## 6. RESUMO DE DECISÕES (GAPS → SOLUÇÕES)

| GAP | Decisão | Biblioteca/Framework |
|-----|---------|---------------------|
| 1 | SQLite Async | `aiosqlite` |
| 2 | Serialização Checkpoint | `dataclasses_json` + exclusão seletiva |
| 3 | Isolamento KV Cache | `slot_id` por session, `asyncio.Lock` por session_id |
| 4 | Thinking Parser | State machine 4 estados (IDLE/IN_OPEN/THINKING/IN_CLOSE) |
| 5 | Merge FTS5 + Qdrant | RRF (Reciprocal Rank Fusion) com k=60, peso 60/40 |
| 6 | Rate Limiting llama | `asyncio.Semaphore` + `asyncio.Queue` + circuit breaker |
| 7 | Whisper Lifecycle | Timeout 60s + refcount atômico (só incrementa pós-load) |
| 8 | Skill Versionamento | Backup automático + validação + rollback |
| 9 | Startup Sequence | `StartupCoordinator` + health checks + retry backoff |
| 10 | Schema Migrations | `SchemaVersionManager` com SQL versionado |
| 11 | Cold Start Modelos | `ProcessLauncher` integrado ao `StartupCoordinator` |
