# Lux — Plano Consolidado v1.0.0

> Documento único que condensa 37 arquivos `.md` do projeto.
> Estrutura completa para recriar, entender e estender o assistente.

---

## 1. Visão Geral

**Lux** é um assistente pessoal 100% local (MIT), 16GB VRAM, AMD ROCm/CUDA.
Modelos: Qwen3-14B (principal, ~9.5GB) + Qwen3-1.7B (auxiliar, ~1.2GB) + MiniCPM-o 4.5 (voz unificada).
Serviços: Qdrant (vetorial), Redis (opcional), llama-server (HTTP).

**6 princípios:** local-first, soberania de privacidade, progressive disclosure (L0/L1/L2), agent loop auditável, tool > prompt, agente que cresce com o usuário.

```bash
lux              # CLI interativo (Textual TUI)
lux --voice      # Modo voz contínuo (MiniCPM-o + wake word)
lux --desktop    # Interface Flet
lux --gateway    # Telegram + Discord + Slack + Email + Webhook
lux --doctor     # Diagnóstico
```

---

## 2. Arquitetura de Diretórios

```
lux/
├── agent/          # AIAgent, AgentState, ModelRouter, Budget, Trajectory, AuxiliaryClient
├── models/         # LlamaClient, VRAMGuard, Embedder, ThinkingParser, CircuitBreaker
├── memory/         # MemoryManager, SessionDB (FTS5), SemanticSearch (Qdrant+RRF), Nudge
├── skills/         # SkillManager, SkillLoader, SkillCreator, SkillVersionStore
├── tools/          # ToolRegistry, ApprovalSystem, DesktopUtils + 16 implementações
│   └── implementations/  # terminal, filesystem, web, email, calendar, tasks, git,
│                         # desktop, orchestrator, subagent, memory_tools, skills_tools,
│                         # system, email_classifier, file_watcher, workflow_tools
├── voice/          # Pipeline, VAD, STT (Whisper), TTS (Piper), WakeWord, OmniEngine,
│                   # Interactive, ConversationMode, VoiceTones, EmotionalContext
├── compression/    # ContextCompressor, SessionLineage
├── reflection/     # PostTaskReflector, SkillEvolver, DSPyOptimizer, UserBehaviorAnalyzer
├── orchestrator/   # TaskOrchestrator (MAX_CONCURRENT=3, QUEUE_SIZE=20), ManagedTask
├── workflows/      # WorkflowParser, WorkflowRunner, EventBus, WorkflowCreator
├── plugins/        # PluginManager (6 hooks), LuxPlugin (ABC)
├── gateway/        # GatewayRunner, AuthManager, TelegramAdapter, DiscordAdapter, Slack, Email, Webhook
├── acp/            # ACPServer (WS p/ VS Code/Zed/JetBrains), ACPProtocol
├── cron/           # CronScheduler (APScheduler), ProactiveTriggerEngine (4 triggers)
├── auth/           # PasswordAuthenticator (bcrypt), JWTManager, FirstRunWizard, AdminPasswordGate
├── interfaces/     # LuxTUI (Textual), LuxDesktopApp (Flet), VoiceUI (HUD), HermesCLI
├── prompt/         # PromptAssembler, SoulLoader, ContextFileLoader, Formatting
├── speaker/        # SpeakerVerifier (ECAPA-TDNN, stubs para MiniCPM-o)
├── config.py       # pydantic-settings (~60 campos, prefixo LUX_)
├── constants.py    # Paths, defaults
├── main.py         # Composition root + DI + entry points
└── migrations/     # 001-006 SQL (sessions, auth, platform_links, reflection, orchestrator)

~/.lux/             # Dados do usuário
├── MEMORY.md, USER.md, SOUL.md
├── sessions.db, skills/, plugins/, cron/
├── workflows/      # YAMLs de automação
├── models/         # wakeword/*.onnx, piper/*.onnx
├── calendar/       # {user_id}.json
└── file_index.json, email_index.json
```

---

## 3. Módulos Core

### 3.1 Agent Loop (50 iterações)
- `AIAgent.run_conversation()` → `_init_state()` → `_agent_loop()` → ferramentas em paralelo (ThreadPoolExecutor)
- Budget progressivo (60%, 80%, 95%), interrupção assíncrona
- Compressão de contexto (threshold 0.50 CLI / 0.85 gateway), protege últimos N
- ModelRouter: 14B (conversa, planejamento, tools complexas) / 1.7B (intent, memory, resumo curto)
- Subagentes com budget isolado (max 20 iterações)

### 3.2 Memória (3 camadas)
- **Frozen Snapshot:** MEMORY.md + USER.md (limite chars configurável)
- **FTS5:** SQLite full-text search com lineage de sessão
- **Qdrant:** busca semântica (all-MiniLM-L6-v2, 384 dims)
- **RRF Merge:** Reciprocal Rank Fusion (k=60, peso 60/40) para combinar resultados
- **Namespaces:** `get_namespace()`, `cross_namespace_query()`, `store_namespace()`

### 3.3 Skills (L0/L1/L2)
- **L0:** Lista de nomes + descrições (cache 60s)
- **L1:** Conteúdo completo do SKILL.md
- **L2:** Seção específica (## Procedimento, ## Pitfalls)
- **Descoberta:** `skills/` (bundled) + `~/.lux/skills/` (usuário)
- **Filtro:** plataforma, toolsets, fallback_for_toolsets
- **Criação autônoma:** SkillCreator + SkillVersionStore (backup/rollback)
- **Formato:** frontmatter YAML com metadata.lux (tags, category, requires_toolsets)

### 3.4 Voice Pipeline
```
VAD (webrtcvad) → WakeWord (ONNX, openWakeWord) → STT (faster-whisper large-v3-turbo)
→ IntentClassifier → LLM → TTS (Piper pt_BR-faber-medium) → barge-in
```
- **OmniEngine:** MiniCPM-o 4.5 via llama-omni-cli (áudio PCM → texto, unificado)
- **Wake Word:** "Jarvis" (ONNX, ~415KB), threshold 0.85, detecção contínua
- **Barge-in:** 5 frames de fala interrompem TTS, volta a escutar
- **Roteamento:** conversa simples → MiniCPM-o; tarefa complexa → Qwen3-14B + tools
- **WhisperLifecycleManager:** refcount atômico, timeout 60s inatividade

### 3.5 Gateway Multi-Plataforma
- Telegram (streaming, voice memo), Discord (slash commands, embeds, threads), Slack, Email, Webhook
- AuthManager: JWT, bcrypt rounds=12, DM pairing com TTL, rate limit 30 req/min
- SessionStore: guest 4h, outros 24h com sliding renewal

### 3.6 Cron & Proatividade
- CronScheduler: polling 30s, executa via AIAgent com contexto de skill
- ProactiveTriggerEngine: 4 triggers built-in
  - `vram_high` (>85%), `long_session_no_memory` (>40 msgs), `pending_reminders`, `disk_low` (<5GB)
- AutonomyLevel: SILENT | NOTIFY | CONFIRM

### 3.7 Plugins (6 hooks)
`pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`, `on_session_start`, `on_session_end`, `on_memory_write`
Descoberta automática em `~/.lux/plugins/`.

---

## 4. Ferramentas (43 tools em 14 toolsets)

| Toolset | Tools |
|---------|-------|
| terminal | shell_run, file_read, file_write, file_append, file_delete, directory_list, directory_create, search_files, patch_file |
| web | web_search, web_fetch |
| email | email_list, email_read, email_send, email_query |
| calendar | calendar_read, calendar_create, reminder_set, reminder_list, reminder_cancel |
| tasks | task_create, task_list, task_complete, task_update |
| memory | memory, session_search |
| skills | skills_list, skill_view, skill_create |
| git | git_status, git_diff, git_commit, git_push, git_pull, git_log, git_branch |
| desktop | screenshot, screen_read, mouse_click, mouse_move, keyboard_type, keyboard_press, window_list, window_focus, clipboard_read, clipboard_write, find_on_screen |
| orchestrator | run_task, orchestrator_status, orchestrator_cancel |
| subagent | delegate_task, todo |
| system | status_check |
| file_watcher | file_query |
| workflow | workflow_list, workflow_view, workflow_create, workflow_toggle, workflow_delete |

**Aprovação:** ApprovalSystem (ALWAYS_DANGEROUS: rm -rf /, dd, mkfs; WARN: sudo, drop table, git push --force), AdminPasswordGate para ações críticas.

---

## 5. Workflow Engine (Automações YAML)

Triggers: `on_start`, `on_schedule` (cron), `on_file_change`, `on_email_received`, `on_request`.

Skills built-in para steps: `web_search`, `content_summarizer`, `file_summarizer`, `email_summarizer`, `save_to_memory`, `notify_user`, `index_to_memory`.

Workflows padrão em `~/.lux/workflows/`:
- `briefing_tech.yaml` — busca notícias tech diariamente
- `alerta_vagas.yaml` — notifica vagas de emprego por e-mail
- `reindexar_projeto.yaml` — atualiza índice ao modificar arquivos

Execução em background (asyncio.ensure_future, timeout 120s/step). Agente cria novos via `workflow_create`.

---

## 6. File Watcher & Email Classifier

**FileWatcher:** Scanner recursivo (max_depth=3), watchdog/polling, indexador JSON, `FileQueryTool`.
**EmailClassifier:** Categoriza por interesses (`EMAIL_INTERESTS=nome1:kw1,kw2;nome2:kw3`), sumariza, `EmailQueryTool`.

---

## 7. Reflection Engine

- `PostTaskReflector` — analisa tarefas concluídas (o que funcionou, lições, oportunidades de skill)
- `SkillEvolver` — detecta padrões de uso, sugere evolução (>3 usos, threshold 0.65)
- `UserBehaviorAnalyzer` — a cada 20 sessões, detecta horários, ferramentas top, taxa de correção
- `DSPyOptimizer` — BootstrapFewShot a cada 25 gerações (MIN_QUALITY_SCORE=0.80)

---

## 8. Task Orchestrator

- `TaskOrchestrator`: MAX_CONCURRENT=3, QUEUE_SIZE=20
- `ManagedTask`: status (pending/running/completed/failed/cancelled), priority, dependencies
- Ferramentas: `run_task`, `orchestrator_status`, `orchestrator_cancel`

---

## 9. Segurança

- Auth: bcrypt (rounds=12), fallback SHA-256, lockout 5 tentativas / 15 min
- JWT: HS256, secret em `~/.lux/jwt_secret` (chmod 600)
- FirstRunWizard: setup inicial do admin
- Roles: ADMIN, USER, GUEST (permissões por toolset)
- Speaker: ECAPA-TDNN (placeholder, substituído por MiniCPM-o unificado)

---

## 10. Interfaces

- **LuxTUI:** Textual, VRAM monitor, histórico, comandos `/`
- **LuxDesktopApp:** Flet, streaming texto + TTS
- **VoiceUI:** HUD retrowave com Rich (fallback texto)
- **ACPServer:** WebSocket ws://127.0.0.1:3284 para IDEs
- **HermesCLI:** auth commands (/register, /login, /users, /whitelist)

---

## 11. Skills do Usuário

| Name | Description | Category | Toolsets |
|------|-------------|----------|----------|
| plan | Planejamento multi-step com milestones | productivity | [tasks] |
| browser-control | Controlar browser (abrir URL, navegar, copiar texto) | productivity | [desktop, terminal] |
| form-fill | Preencher formulários via screenshot + OCR + keyboard | productivity | [desktop] |
| code-review | Revisar PR, sugerir melhorias | development | [terminal, git] |
| debug-error | Diagnosticar stack trace, logs, root cause | development | [terminal] |
| git-workflow | Fluxo Git completo (branch, commit, PR, merge) | development | [git, terminal] |
| deploy-docker | Deploy container via SSH | infrastructure | [terminal] |
| email-triage | Triagem de emails (não lidos, urgentes) | productivity | [email] |
| search-knowledge | Busca combinada (web + FTS5 + Qdrant) | productivity | [web, memory_tools] |
| system-health | Diagnóstico de sistema (VRAM, processos, logs) | system | [system, terminal] |

---

## 12. Wake Word ("Jarvis")

- Treinamento: openWakeWord (MMNet + att-conv), PyTorch + ROCm
- Pipeline: TTS synthesis (2000+ positivos) → augmentação → 30 epochs (~2-4h) → ONNX (~415KB)
- Detector: onnxruntime + openWakeWord AudioFeatures (Google Speech Embedding 1x16x96)
- Rolling buffer 2s @ 16kHz, RMS gate 0.02, cooldown 2s
- Threshold 0.85 (FPR < 1%), modelo em `~/.lux/models/wakeword/jarvis.onnx`

---

## 13. GAPs de Arquitetura (11 resolvidos)

| # | Gap | Solução |
|---|-----|---------|
| 1 | SQLite async | aiosqlite |
| 2 | Serialização checkpoint | dataclasses_json |
| 3 | Isolamento KV Cache | asyncio.Lock por session_id |
| 4 | Thinking parser | FSM 4 estados |
| 5 | Merge FTS5+Qdrant | RRF k=60, peso 60/40 |
| 6 | Rate limiting | Semaphore + Queue + CircuitBreaker |
| 7 | Ciclo de vida Whisper | Atomic refcount, timeout 60s |
| 8 | Versão de skills | SkillVersionStore (backup/rollback) |
| 9 | Startup sequence | StartupCoordinator (DAG + health checks) |
| 10 | Migrations SQL | SchemaVersionManager |
| 11 | Cold start modelos | ProcessLauncher |

---

## 14. Dependências Externas

```toml
[voice]    pyaudio, webrtcvad, openwakeword, onnxruntime, librosa, numpy, sounddevice
[desktop]  xdotool, scrot/grim, tesseract-ocr, wmctrl, xclip, imagemagick
[tts]      piper (binário), ffplay/mpv/aplay
[stt]      faster-whisper, ctranslate2
[models]   llama-server (llama.cpp), MiniCPM-o GGUF
[services] qdrant (Docker), redis (Docker opcional)
[dev]      pytest, pytest-asyncio, pytest-mock, pytest-cov
```

---

## 15. Schema do Banco

**001_initial:** sessions, messages, messages_fts (FTS5), user_profiles, cron_jobs, reminders, trajectories
**002_auth / 003_auth_system:** auth_sessions, password_hashes, jwt_secrets
**004_platform_links:** platform_links (Telegram/Discord ↔ user_id)
**005_reflection:** task_reflections, skill_evolutions, skill_queue, lessons_fts (FTS5), behavior_profiles
**006_orchestrator:** managed_tasks (status, priority, dependencies, result)

---

## 16. Decisões de Arquitetura (ADRs 001-015)

| # | Decisão |
|---|---------|
| 001 | aiosqlite como wrapper async do sqlite3 |
| 002 | dataclasses_json para serialização de checkpoints |
| 003 | asyncio.Lock por session_id para slots do llama-server |
| 004 | FSM 4 estados para parse de thinking tags |
| 005 | RRF (k=60) para merge FTS5 + Qdrant |
| 006 | Semaphore + Queue + CircuitBreaker para rate limiting |
| 007 | Refcount atômico no WhisperLifecycleManager |
| 008 | SkillVersionStore com backup + rollback |
| 009 | StartupCoordinator com DAG de dependências |
| 010 | SchemaVersionManager com migrations versionadas |
| 011 | ProcessLauncher para cold start de modelos |
| 012 | Liveness detection como funcionalidade opcional |
| 013 | asyncio.Lock no update_centroid() do VoiceProfileStore |
| 014 | Sliding renewal 24h voz; GUEST expira em 4h fixo |
| 015 | Revoke sessions ao deletar usuário |

---

## 17. Riscos Técnicos

| Risco | Mitigação |
|-------|-----------|
| Deadlock em tool calls paralelas | ThreadPoolExecutor com timeout, cancel_futures |
| Conflito de slot llama-server | slot_id por session, lock atômico, circuit breaker |
| Perda de dados na compressão | rescue_tool_pairs, abort se inválido |
| Memory leak no streaming de voz | Buffer máximo 4096 chars, timeout 300s |
| Alucinação de tool calls | Validação Pydantic, nudge após 3 falhas |
| Race condition MemoryManager | asyncio.Lock por (user_id, target) |
| Exaustão VRAM por KV Cache | VRAMGuard monitor_loop, compressão proativa |
| Incompatibilidade GGUF Qwen3 | Versões fixas, health check |
| Performance 1.7B em pt-BR | Fallback 14B, log de acurácia |

---

*Plano consolidado gerado em 27/05/2026. Substitui 37 arquivos .md do projeto.*
