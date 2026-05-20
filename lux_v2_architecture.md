# Lux — Arquitetura do Assistente Pessoal Local v2.0
> Inspirado na análise do Hermes Agent (NousResearch) | MIT | 100% local | 16GB VRAM

---

## Índice

1. [O que mudou do v1.0 para o v2.0](#1-o-que-mudou)
2. [Filosofia e Princípios](#2-filosofia-e-princípios)
3. [Escolha de Modelos e Orçamento de VRAM](#3-escolha-de-modelos-e-orçamento-de-vram)
4. [Unidades Fundamentais e Tipos de Dados](#4-unidades-fundamentais-e-tipos-de-dados)
5. [Sistema de Memória em Três Camadas](#5-sistema-de-memória-em-três-camadas)
6. [Sistema de Skills com Progressive Disclosure](#6-sistema-de-skills-com-progressive-disclosure)
7. [Agent Loop — Motor de Orquestração](#7-agent-loop--motor-de-orquestração)
8. [Sistema de Prompt Assembly](#8-sistema-de-prompt-assembly)
9. [Compressão de Contexto e Session Lineage](#9-compressão-de-contexto-e-session-lineage)
10. [Sistema de Ferramentas e Toolsets](#10-sistema-de-ferramentas-e-toolsets)
11. [Subagente e Delegação Paralela](#11-subagente-e-delegação-paralela)
12. [Sistema de Aprovação de Comandos](#12-sistema-de-aprovação-de-comandos)
13. [Pipeline de Voz](#13-pipeline-de-voz)
14. [Gerenciador de Modelos e VRAM](#14-gerenciador-de-modelos-e-vram)
15. [Gateway Multi-Plataforma](#15-gateway-multi-plataforma)
16. [Scheduler e Proatividade](#16-scheduler-e-proatividade)
17. [Sistema de Plugins e Hooks](#17-sistema-de-plugins-e-hooks)
18. [Session Storage com FTS5](#18-session-storage-com-fts5)
19. [Personalidade — SOUL.md e Context Files](#19-personalidade--soulmd-e-context-files)
20. [ACP Adapter — Integração com IDEs](#20-acp-adapter--integração-com-ides)
21. [Interfaces e CLI](#21-interfaces-e-cli)
22. [Segurança e Privacidade Local](#22-segurança-e-privacidade-local)
23. [Estrutura de Arquivos](#23-estrutura-de-arquivos)
24. [Esquema de Banco de Dados](#24-esquema-de-banco-de-dados)
25. [Cenários de Uso Completos](#25-cenários-de-uso-completos)
26. [Plano de Implementação](#26-plano-de-implementação)

---

## 1. O que mudou do v1.0 para o v2.0

### Lições do Hermes Agent

Após análise do repositório NousResearch/hermes-agent (153k stars, 8.495 commits, v0.14.0), as seguintes decisões arquiteturais foram incorporadas ou substituídas:

| Área | v1.0 (anterior) | v2.0 (esta versão) | Origem |
|---|---|---|---|
| **Modelo principal** | Llama 3.1 8B | **Qwen3-14B Q4_K_M** | Análise de capacidades |
| **Modelo auxiliar** | TinyLlama 1.1B | **Qwen3-1.7B Q4_K_M** | Hermes: auxiliary_client.py |
| **Memória** | DB estruturado + Qdrant | **SOUL.md + MEMORY.md + USER.md + FTS5 + Qdrant** | Hermes: memory system |
| **Skills** | Inexistente | **Progressive disclosure (L0/L1/L2)** | Hermes: skills system |
| **Sessão** | Redis sliding window | **SQLite + FTS5 com lineage tracking** | Hermes: hermes_state.py |
| **Personalidade** | Config YAML | **SOUL.md editável** | Hermes: SOUL.md |
| **Ferramentas** | Registro plano | **Toolsets com enable/disable por plataforma** | Hermes: toolsets.py |
| **Paralelismo** | Sem delegação | **Subagentes com budget isolado** | Hermes: delegate_tool.py |
| **Plugins** | Inexistente | **Hooks pre/post tool call** | Hermes: plugins.py |
| **Aprovação** | AutonomyLevel global | **Aprovação granular por padrão de comando** | Hermes: approval.py |
| **Contexto** | System prompt estático | **Frozen snapshot + context files (AGENTS.md)** | Hermes: context_engine.py |
| **Compressão** | Sumarização simples | **Lossy compression com lineage + budget warnings** | Hermes: context_compressor.py |
| **IDEs** | Inexistente | **ACP adapter (VS Code, Zed, JetBrains)** | Hermes: acp_adapter/ |
| **Gateway** | Discord only | **Multi-plataforma (Telegram, Discord, Slack, E-mail, WhatsApp)** | Hermes: gateway/ |
| **Trajetórias** | Inexistente | **Trajectory saving para fine-tuning futuro** | Hermes: trajectory.py |

### O que o Hermes não tem e o Lux mantém

| Feature | Por quê manter |
|---|---|
| Qdrant para busca semântica | FTS5 é lexical; Qdrant complementa com similaridade vetorial |
| VRAM Guard com circuit breaker | Hermes roda em cloud; Lux tem budget fixo de 16GB |
| Pipeline de voz (STT/TTS) | Hermes delega para ElevenLabs (cloud); Lux é 100% local |
| Proatividade com triggers cron próprios | Hermes tem cron mas sem triggers condicionais locais |
| Mapa explícito de VRAM por modelo | Necessário para hardware fixo |

---

## 2. Filosofia e Princípios

```
PRINCÍPIO 1 — O AGENTE CRESCE COM VOCÊ (Hermes-inspired)
  Toda interação é oportunidade de aprendizado.
  Skills são criadas autonomamente após tarefas complexas.
  Memória é curada pelo agente — não pelo usuário.
  O modelo de usuário se aprofunda com cada sessão.

PRINCÍPIO 2 — PROGRESSIVE DISCLOSURE DE CONTEXTO
  Contexto não é injetado em bloco — é carregado sob demanda.
  Skills: lista primeiro (L0), conteúdo só se necessário (L1/L2).
  Memória: frozen snapshot leve no prompt, FTS5 para recall profundo.
  Documentação de APIs: indexada no Qdrant, não no prompt.

PRINCÍPIO 3 — AGENT LOOP COMO ESTADO AUDITÁVEL
  Toda iteração é serializável e reproduzível.
  Trajetórias são salvas para diagnóstico e fine-tuning futuro.
  Session lineage rastreia compressões e ramificações.
  Checkpoints permitem retomada exata após falha.

PRINCÍPIO 4 — FERRAMENTA > PROMPT PARA AÇÕES
  Ações do mundo real são executadas via ferramentas, nunca via
  texto livre que o LLM "imagina ter executado".
  Ferramentas retornam resultados estruturados, não strings.
  Comandos perigosos sempre passam pelo approval gate.

PRINCÍPIO 5 — LOCAL-FIRST E DEGRADAÇÃO GRACIOSA
  Zero dependência de cloud em runtime.
  Falha de qualquer serviço auxiliar não derruba o core.
  VRAM guard previne OOM antes de acontecer.
  Fallback model sempre disponível para operações críticas.

PRINCÍPIO 6 — PRIVACIDADE SOBERANA
  Nenhum dado sai da máquina.
  Logs não têm telemetria.
  Áudio descartado após transcrição.
  Usuário controla e exporta todos os seus dados.
```

---

## 3. Escolha de Modelos e Orçamento de VRAM

### 3.1 Justificativa dos Modelos

**Por que Qwen3-14B como modelo principal?**

O Qwen3-14B-Instruct é a escolha superior ao Llama 3.1 8B para um assistente pessoal em 2025-2026 por três razões concretas:

```
CAPACIDADE DE TOOL CALLING
  Qwen3-14B tem function calling nativo robusto, testado em benchmarks
  de tool use (BFCL, ToolBench). O LLama 3.1 8B comete mais erros de
  schema em chamadas de ferramentas complexas — crítico para um assistente
  que executa ações reais no sistema.

THINKING MODE INTEGRADO
  Qwen3-14B suporta /think (raciocínio extendido via <think>...</think>)
  ativável por request. Para tarefas como planejamento de projeto, análise
  de e-mail ou decisões de autonomia, o thinking mode produz resultados
  significativamente melhores sem trocar de modelo.

QUALIDADE EM PORTUGUÊS
  Qwen3 foi treinado com dados multilíngues superiores ao Llama 3.1 8B.
  Melhor fluência em pt-BR, menos code-switching indesejado.
```

**Por que Qwen3-1.7B como modelo auxiliar?**

```
VELOCIDADE PARA TAREFAS CLASSIFICATÓRIAS
  ~0.3s para classificar intent vs ~1.8s com o 14B.
  Tarefas como extração de memória, classificação de urgência
  e confirmações simples não justificam o 14B.

COEXISTÊNCIA EM VRAM
  1.7B Q4_K_M ~1.2GB — cabe confortavelmente ao lado do 14B (~9.5GB).
  Total com KV caches: ~12.2GB — margem de 3.8GB para Whisper e embeddings.
```

### 3.2 Mapa Completo de VRAM (16GB)

```
MODELOS RESIDENTES (sempre em VRAM):
  Qwen3-14B-Instruct Q4_K_M          9.5GB
  Qwen3-1.7B-Instruct Q4_K_M         1.2GB
  all-MiniLM-L6-v2 (embeddings)      0.1GB
  ─────────────────────────────────── ──────
  Subtotal residente                 10.8GB

KV CACHE (configurado):
  14B com ctx=8K, parallel=2         1.8GB
  1.7B com ctx=4K, parallel=4        0.3GB
  ─────────────────────────────────── ──────
  Subtotal KV cache                   2.1GB

SOB DEMANDA (carregado apenas quando ativo):
  Whisper small (STT)                 0.5GB
  bge-reranker-v2-m3 (reranking RAG)  0.7GB
  ─────────────────────────────────── ──────
  Máximo sob demanda simultâneo       1.2GB

─────────────────────────────────────────────
PICO MÁXIMO (todos carregados)        14.1GB ✓
MARGEM DE SEGURANÇA                    1.9GB
─────────────────────────────────────────────
```

### 3.3 Roteamento de Tarefas por Modelo

```python
class ModelRouter:
    """Decide qual modelo usar para cada tipo de tarefa."""

    MAIN_MODEL  = "qwen3-14b-q4"    # llama-server porta 8080
    FAST_MODEL  = "qwen3-1.7b-q4"   # llama-server porta 8081
    AUX_MODEL   = "qwen3-1.7b-q4"   # mesmo servidor, contexto separado

    ROUTING_TABLE = {
        # Tarefas para o modelo principal (14B)
        Task.CONVERSATION:        (MAIN_MODEL, {"temperature": 0.7,  "thinking": False}),
        Task.CONVERSATION_DEEP:   (MAIN_MODEL, {"temperature": 0.6,  "thinking": True}),
        Task.ACTION_PLANNING:     (MAIN_MODEL, {"temperature": 0.2,  "thinking": True}),
        Task.SKILL_CREATION:      (MAIN_MODEL, {"temperature": 0.4,  "thinking": True}),
        Task.SUMMARIZE_LONG:      (MAIN_MODEL, {"temperature": 0.3,  "thinking": False}),
        Task.TOOL_CALL_COMPLEX:   (MAIN_MODEL, {"temperature": 0.1,  "thinking": False}),

        # Tarefas para o modelo auxiliar (1.7B) — mais rápido, menos tokens
        Task.INTENT_CLASSIFY:     (FAST_MODEL, {"temperature": 0.1,  "max_tokens": 128}),
        Task.MEMORY_EXTRACT:      (FAST_MODEL, {"temperature": 0.1,  "max_tokens": 256}),
        Task.SENTIMENT_DETECT:    (FAST_MODEL, {"temperature": 0.1,  "max_tokens": 32}),
        Task.CONFIRMATION_PARSE:  (FAST_MODEL, {"temperature": 0.1,  "max_tokens": 16}),
        Task.SUMMARIZE_SHORT:     (FAST_MODEL, {"temperature": 0.3,  "max_tokens": 512}),
        Task.ENTITY_EXTRACT:      (FAST_MODEL, {"temperature": 0.1,  "max_tokens": 256}),
        Task.SKILL_TRIGGER_CHECK: (FAST_MODEL, {"temperature": 0.1,  "max_tokens": 64}),
    }
```

### 3.4 llama-server — Configuração por Instância

```bash
# Instância MAIN — Qwen3-14B (porta 8080)
llama-server \
  --model /models/Qwen3-14B-Instruct-Q4_K_M.gguf \
  --ctx-size 8192 \
  --parallel 2 \               # 2 usuários simultâneos no 14B
  --batch-size 512 \
  --ubatch-size 256 \
  --cache-type-k q8_0 \        # KV cache quantizado — menos VRAM
  --cache-type-v q8_0 \
  --flash-attn \
  --no-context-shift \         # CRÍTICO: não descarta contexto silenciosamente
  --thinking \                 # habilita <think>...</think> do Qwen3
  --port 8080 \
  --log-format json \
  --host 127.0.0.1             # nunca 0.0.0.0

# Instância AUX — Qwen3-1.7B (porta 8081)
llama-server \
  --model /models/Qwen3-1.7B-Instruct-Q4_K_M.gguf \
  --ctx-size 4096 \
  --parallel 4 \               # leve, suporta mais slots
  --batch-size 256 \
  --cache-type-k q8_0 \
  --cache-type-v q8_0 \
  --port 8081 \
  --log-format json \
  --host 127.0.0.1
```

---

## 4. Unidades Fundamentais e Tipos de Dados

### 4.1 Message

```python
@dataclass
class Message:
    id: str                          # UUID v4
    session_id: str
    user_id: str
    channel: Channel                 # CLI | VOICE | DISCORD | TELEGRAM | SLACK | EMAIL

    # Conteúdo
    role: Role                       # USER | ASSISTANT | SYSTEM | TOOL | THINKING
    content: str
    thinking_content: Optional[str]  # conteúdo <think>...</think> do Qwen3
    tool_calls: list[ToolCall]       # chamadas de ferramenta emitidas pelo LLM
    tool_call_id: Optional[str]      # se role=TOOL, ID da chamada correspondente
    attachments: list[Attachment]    # arquivos, imagens

    # Classificação (preenchido pelo AuxAgent)
    intent: Optional[Intent]
    entities: list[Entity]
    requires_approval: bool

    # Metadados de performance
    timestamp: datetime
    model_used: str
    tokens_prompt: int
    tokens_completion: int
    latency_ms: int
    iteration: int                   # número da iteração no agent loop

    # Rastreabilidade
    task_id: str
    parent_message_id: Optional[str]
    memory_hits: list[str]           # IDs de MemoryEntry que influenciaram
```

### 4.2 AgentState

```python
@dataclass
class AgentState:
    # Identidade
    task_id: str
    session_id: str
    user_id: str
    user_profile: UserProfile
    channel: Channel

    # Contexto do agente
    system_prompt_frozen: str        # snapshot no início da sessão (imutável)
    conversation_history: list[Message]  # histórico em formato OpenAI
    context_files: dict[str, str]    # AGENTS.md, .lux.md etc. por path

    # Memória ativa (carregada do disco no início)
    memory_snapshot: str             # MEMORY.md frozen
    user_snapshot: str               # USER.md frozen
    pending_memory_writes: list[MemoryDelta]  # escritas pendentes para flush

    # Skill ativo
    active_skill: Optional[Skill]
    skill_context: Optional[str]

    # Execução
    current_tool_calls: list[ToolCall]
    tool_results: list[ToolResult]
    pending_approval: Optional[ApprovalRequest]
    subagent_tasks: list[SubagentTask]

    # Budget e controle
    iteration: int
    max_iterations: int              # padrão: 50
    budget_warnings_sent: int        # quantas vezes alertou sobre budget
    is_subagent: bool
    parent_task_id: Optional[str]

    # Compressão
    compression_count: int           # quantas vezes foi comprimido
    session_lineage_id: str          # ID da linhagem de compressão

    # Status
    pipeline_status: PipelineStatus
    interrupt_event: asyncio.Event   # sinaliza interrupção externa
    error: Optional[str]

    # Persistência
    trajectory: list[TrajectoryStep] # para fine-tuning futuro
    checkpoint_path: Optional[str]

    def to_openai_messages(self) -> list[dict]:
        """Converte histórico para formato OpenAI (role/content/tool_calls)."""

    def enforce_alternation(self):
        """
        Garante alternância estrita de roles no histórico.
        Nunca dois assistant ou dois user seguidos.
        tool messages podem ser consecutivos (resultados paralelos).
        """
```

### 4.3 UserProfile

```python
@dataclass
class UserProfile:
    user_id: str
    username: str
    display_name: str
    role: UserRole                    # ADMIN | USER | GUEST

    # Preferências (sincronizadas com USER.md)
    preferred_language: str
    response_style: ResponseStyle     # CONCISE | BALANCED | DETAILED
    formality: Formality
    technical_depth: int              # 0-5
    preferred_channel: Channel

    # Voz
    voice_enabled: bool
    listening_mode: ListeningMode     # OFF | WAKE_WORD | PUSH_TO_TALK | ALWAYS_ON
    preferred_voice: str

    # Autonomia por categoria (granular, por padrão de comando)
    approval_patterns: list[ApprovalPattern]  # padrões regex para auto-approve
    danger_patterns: list[str]                # padrões que SEMPRE pedem aprovação

    # Toolsets habilitados para este usuário
    enabled_toolsets: list[str]       # ["terminal", "web", "email", ...]

    # Contexto de trabalho
    active_projects: list[str]
    work_hours: tuple[time, time]
    timezone: str

    # Skills habilitadas/desabilitadas
    disabled_skills: list[str]
    skill_overrides: dict[str, dict]  # configurações por skill

    created_at: datetime
    last_seen: datetime
    total_sessions: int
    total_tokens_used: int
```

---

## 5. Sistema de Memória em Três Camadas

### 5.1 Arquitetura Completa (Hermes + Qdrant)

```
CAMADA 1 — MEMÓRIA IMEDIATA (MEMORY.md + USER.md — arquivos em disco)
  Inspirado diretamente no Hermes Agent
  
  ~/.lux/memories/MEMORY.md     — notas pessoais do agente
    Limite: 2.200 chars (~800 tokens)
    Conteúdo: fatos do ambiente, convenções, lições aprendidas,
              projetos ativos, histórico de tarefas concluídas
    Formato: entradas separadas por § (section sign)
    
  ~/.lux/memories/USER.md       — perfil do usuário
    Limite: 1.375 chars (~500 tokens)
    Conteúdo: nome, timezone, preferências, estilo de comunicação,
              pet peeves, nível técnico, hábitos de trabalho
    Formato: entradas separadas por §

  FROZEN SNAPSHOT: ambos são carregados UMA VEZ no início da sessão
  e injetados como bloco fixo no system prompt. Não mudam mid-session.
  Mudanças do agente são escritas em disco imediatamente mas só
  aparecem no prompt na sessão seguinte.
  
  Por quê frozen? Preserva o prefix cache do llama-server — o bloco
  de sistema nunca muda, então o KV cache é reutilizado em toda sessão.

CAMADA 2 — SESSÕES E BUSCA FTS5 (SQLite)
  Histórico completo de todas as sessões
  Full-Text Search (FTS5) para busca textual exata em conversas passadas
  Session lineage: cada compressão gera sessão "filha" com referência à mãe
  Usado pelo session_search tool: "o que eu disse sobre X semana passada?"

CAMADA 3 — MEMÓRIA SEMÂNTICA (Qdrant)
  Busca por similaridade vetorial para recall impreciso
  "algo sobre machine learning que discutimos" → embedding → top-K
  Complementa FTS5 (lexical) com busca semântica
  Embeddings: all-MiniLM-L6-v2, 384 dimensões
  Coleções: episodic_memory, workspace_knowledge, skill_patterns
```

### 5.2 MemoryManager — Implementação

```python
class MemoryManager:
    """
    Ponto central de acesso a todas as camadas de memória.
    Implementa o padrão do Hermes: o agente gerencia sua própria memória
    via tool calls, não há extração automática invisível.
    """

    # Limites do Hermes (preservados exatamente)
    MEMORY_MD_LIMIT = 2200    # chars
    USER_MD_LIMIT   = 1375    # chars
    ENTRY_SEPARATOR = "§"     # section sign, único e raro em texto normal

    async def load_frozen_snapshot(self, user_id: str) -> tuple[str, str]:
        """
        Carrega MEMORY.md e USER.md do disco.
        Chamado UMA VEZ no início da sessão.
        Retorna (memory_content, user_content) para injeção no system prompt.
        """
        memory_path = self._memory_path(user_id, "MEMORY.md")
        user_path   = self._memory_path(user_id, "USER.md")

        memory_content = memory_path.read_text() if memory_path.exists() else ""
        user_content   = user_path.read_text()   if user_path.exists()   else ""

        memory_used = len(memory_content)
        user_used   = len(user_content)

        return (
            self._format_memory_block("MEMORY",       memory_content,
                                      memory_used, self.MEMORY_MD_LIMIT),
            self._format_memory_block("USER PROFILE", user_content,
                                      user_used,   self.USER_MD_LIMIT),
        )

    def _format_memory_block(self, title: str, content: str,
                              used: int, limit: int) -> str:
        """
        Formata o bloco de memória exatamente como o Hermes:
        ══════════════════════════════════
        MEMORY (your personal notes) [67% — 1474/2200 chars]
        ══════════════════════════════════
        ...conteúdo...
        """
        pct = int(used / limit * 100) if limit > 0 else 0
        header = f"{'═'*46}\n{title} [{pct}% — {used}/{limit} chars]\n{'═'*46}"
        return f"{header}\n{content}" if content else f"{header}\n(empty)"

    async def apply_memory_action(self, action: MemoryAction,
                                   target: Literal["memory", "user"],
                                   content: Optional[str],
                                   old_text: Optional[str],
                                   user_id: str) -> MemoryResult:
        """
        Executado quando o LLM chama a ferramenta `memory`.
        Ações: add | replace | remove
        
        O agente usa isso autonomamente durante a conversa:
        - add:     nova entrada (verifica limite de chars)
        - replace: substitui por substring match (old_text)
        - remove:  remove por substring match (old_text)
        
        Escreve em disco IMEDIATAMENTE.
        Não afeta o frozen snapshot da sessão atual.
        Afeta sessões futuras.
        """
        path = self._memory_path(user_id,
                                  "MEMORY.md" if target == "memory" else "USER.md")
        limit = self.MEMORY_MD_LIMIT if target == "memory" else self.USER_MD_LIMIT
        current = path.read_text() if path.exists() else ""

        match action:
            case MemoryAction.ADD:
                new_entry = content.strip()
                new_content = f"{current}\n{self.ENTRY_SEPARATOR}\n{new_entry}".strip()
                if len(new_content) > limit:
                    return MemoryResult.error(
                        f"Memória cheia ({len(current)}/{limit} chars). "
                        f"Consolide ou remova entradas antigas antes de adicionar."
                    )
                path.write_text(new_content)
                return MemoryResult.ok(f"Entrada adicionada ({len(new_entry)} chars).")

            case MemoryAction.REPLACE:
                if old_text not in current:
                    return MemoryResult.error(f"Substring '{old_text}' não encontrada.")
                matches = [e for e in current.split(self.ENTRY_SEPARATOR)
                          if old_text in e]
                if len(matches) > 1:
                    return MemoryResult.error(
                        f"Substring '{old_text}' encontrada em {len(matches)} entradas. "
                        f"Use um trecho mais específico."
                    )
                new_content = current.replace(matches[0], content.strip(), 1)
                if len(new_content) > limit:
                    return MemoryResult.error(f"Conteúdo novo excede limite de {limit} chars.")
                path.write_text(new_content)
                return MemoryResult.ok("Entrada substituída.")

            case MemoryAction.REMOVE:
                # Similar ao replace mas sem conteúdo novo
                ...

    async def session_search(self, query: str,
                              user_id: str,
                              limit: int = 5) -> list[SessionSearchResult]:
        """
        Busca FTS5 em todas as sessões passadas do usuário.
        Usado pelo tool session_search para recall cross-session.
        
        Retorna: lista de (session_id, timestamp, snippet, score)
        O LLM pode usar esses resultados para responder perguntas
        sobre conversas passadas com precisão textual exata.
        """
        results = await self.session_db.fts_search(
            query=query,
            user_id=user_id,
            limit=limit
        )
        return [SessionSearchResult.from_row(r) for r in results]

    async def semantic_recall(self, query: str,
                               user_id: str,
                               top_k: int = 5) -> list[MemoryChunk]:
        """
        Busca semântica no Qdrant para recall impreciso.
        Complementa session_search quando o usuário não lembra
        as palavras exatas mas lembra o conceito.
        """
        embedding = await self.embedder.embed(query)
        hits = await self.qdrant.search(
            collection="episodic_memory",
            query_vector=embedding,
            query_filter=Filter(must=[FieldCondition(
                key="user_id", match=MatchValue(value=user_id)
            )]),
            limit=top_k,
        )
        return [MemoryChunk.from_qdrant(h) for h in hits]
```

### 5.3 Nudges Automáticos de Memória

Inspirado no Hermes, o Lux inclui nudges periódicos para que o agente persista conhecimento antes de perder contexto:

```python
class MemoryNudgeSystem:
    """
    Injeta lembretes ephemeros no contexto quando detecta que:
    1. Há informações novas importantes não persistidas ainda
    2. O contexto está se aproximando do limite (>60%)
    3. A sessão está longa (>30 turns) e há coisas novas aprendidas
    """

    NUDGE_AT_CONTEXT_PCT = 0.60     # lembra de salvar quando contexto > 60%
    NUDGE_AT_TURNS = 30             # lembra a cada 30 turns

    def maybe_inject_nudge(self, state: AgentState) -> Optional[str]:
        ctx_usage = self._estimate_context_usage(state)
        turns = state.iteration

        should_nudge = (
            ctx_usage > self.NUDGE_AT_CONTEXT_PCT or
            turns > 0 and turns % self.NUDGE_AT_TURNS == 0
        )
        if not should_nudge:
            return None

        return (
            "[SISTEMA] Lembre-se de persistir quaisquer fatos importantes "
            "aprendidos nesta sessão usando a ferramenta `memory` antes que "
            "o contexto seja comprimido."
        )
```

---

## 6. Sistema de Skills com Progressive Disclosure

### 6.1 Arquitetura

```
PROGRESSIVE DISCLOSURE — 3 NÍVEIS:

Level 0 — skills_list()
  Custo: ~800 tokens (lista de todas as skills com nome + descrição curta)
  Quando: sempre injetado no system prompt (apenas L0)
  Formato: [{name, description, category, slash_command}]

Level 1 — skill_view(name)
  Custo: variável (conteúdo completo do SKILL.md)
  Quando: agente decide que precisa da skill para a tarefa atual
  Formato: conteúdo completo + metadata + procedure

Level 2 — skill_view(name, section)
  Custo: menor que L1 (apenas seção específica)
  Quando: agente já usou a skill antes e só precisa de um passo específico
  Formato: seção específica do SKILL.md
```

### 6.2 Formato SKILL.md

```markdown
---
name: deploy-docker
description: "Deploy de container Docker local ou remoto via SSH"
version: 1.2.0
author: lux-agent                # skills criadas autonomamente têm author: lux-agent
platforms: [linux, macos]
metadata:
  lux:
    tags: [docker, deploy, devops]
    category: infrastructure
    requires_toolsets: [terminal]  # só aparece se terminal está habilitado
    fallback_for_toolsets: [k8s]   # aparece se k8s não disponível
    created_from_task: "task_abc123"  # rastreia a tarefa que gerou a skill
    quality_score: 0.87
    use_count: 12
    last_used: "2026-05-14"
    config:
      - key: docker.registry
        description: "Registry padrão para push"
        default: "localhost:5000"
---

# Deploy Docker

## Quando Usar
Deploy de imagens Docker em ambientes locais ou remotos via SSH.

## Pré-requisitos
- Docker daemon rodando (`docker info`)
- Se remoto: SSH configurado para o host alvo

## Procedimento

### Build Local
```bash
docker build -t {image_name}:{tag} .
docker images | grep {image_name}
```

### Push para Registry
```bash
docker push {registry}/{image_name}:{tag}
```

### Deploy em Host Remoto
```bash
ssh {remote_host} "docker pull {registry}/{image_name}:{tag} && \
  docker stop {container_name} 2>/dev/null; \
  docker run -d --name {container_name} --restart=unless-stopped \
  {registry}/{image_name}:{tag}"
```

## Pitfalls
- `permission denied`: usuário não está no grupo docker — `sudo usermod -aG docker $USER`
- Registry HTTP: adicionar em `insecure-registries` no daemon.json

## Verificação
```bash
docker ps | grep {container_name}
curl http://{host}:{port}/health
```
```

### 6.3 SkillManager

```python
class SkillManager:
    """
    Gerencia o ciclo de vida de skills: descoberta, carregamento,
    injeção no contexto e criação autônoma.
    """

    SKILLS_DIR = Path("~/.lux/skills/").expanduser()
    BUNDLED_DIR = Path("./skills/")    # skills do repositório

    def get_skills_list_l0(self, user: UserProfile,
                            channel: Channel) -> list[SkillSummary]:
        """
        Level 0: lista leve de todas as skills disponíveis.
        Filtra por: plataforma, toolsets ativos, skills desabilitadas.
        Injeta apenas nome + descrição curta (1 linha).
        """
        all_skills = self._load_all_skill_metadata()
        return [
            s for s in all_skills
            if self._is_available(s, user, channel)
        ]

    def get_skill_content_l1(self, skill_name: str) -> str:
        """Level 1: conteúdo completo do SKILL.md."""
        skill_path = self._resolve_skill_path(skill_name)
        return skill_path.read_text()

    def get_skill_section_l2(self, skill_name: str, section: str) -> str:
        """Level 2: seção específica do SKILL.md por heading."""
        content = self.get_skill_content_l1(skill_name)
        return self._extract_section(content, section)

    async def create_skill_from_task(self, state: AgentState,
                                      task_summary: str) -> Optional[Skill]:
        """
        Criação autônoma de skill após tarefa complexa.
        O agente decide quando criar — não há trigger automático forçado.
        
        Heurística: se a tarefa teve >5 steps de ferramenta E
        foi bem-sucedida E não existe skill similar (similaridade < 0.8),
        o agente recebe um nudge para considerar criar uma skill.
        """
        if not self._should_suggest_skill(state):
            return None

        # LLM 14B com thinking mode gera o SKILL.md
        skill_content = await self.main_llm.generate(
            prompt=SKILL_CREATION_PROMPT.format(
                task_summary=task_summary,
                tool_calls=state.tool_results,
                existing_skills=self.get_skills_list_l0(state.user_profile,
                                                         state.channel),
            ),
            temperature=0.4,
            thinking=True,
        )
        skill = Skill.from_markdown(skill_content)
        skill.metadata.author = "lux-agent"
        skill.metadata.created_from_task = state.task_id

        # Salva em disco
        skill_path = self.SKILLS_DIR / f"{skill.name}.md"
        skill_path.write_text(skill_content)
        return skill

    def _is_available(self, skill: SkillMetadata,
                       user: UserProfile,
                       channel: Channel) -> bool:
        """
        Verifica disponibilidade da skill:
        1. Plataforma compatível (linux/macos/windows)
        2. Toolsets requeridos estão ativos
        3. Toolsets de fallback: visível apenas se os toolsets principais ausentes
        4. Não está na lista disabled_skills do usuário
        """
        if skill.name in user.disabled_skills:
            return False
        if skill.platforms and self._get_platform() not in skill.platforms:
            return False
        if skill.requires_toolsets:
            if not all(t in user.enabled_toolsets for t in skill.requires_toolsets):
                return False
        if skill.fallback_for_toolsets:
            # visível APENAS se os toolsets principais NÃO estão disponíveis
            if any(t in user.enabled_toolsets for t in skill.fallback_for_toolsets):
                return False
        return True
```

---

## 7. Agent Loop — Motor de Orquestração

### 7.1 Visão Geral

```python
class AIAgent:
    """
    Motor central do Lux. Inspirado no AIAgent do Hermes (run_agent.py).
    Responsabilidades:
    - Montar system prompt (via PromptAssembler)
    - Selecionar e chamar modelo correto
    - Executar tool calls (sequencial ou paralelo via ThreadPoolExecutor)
    - Gerenciar compressão de contexto
    - Persistir sessão e memória
    - Suportar interrupção e subagentes
    - Salvar trajetória para fine-tuning
    """

    def chat(self, message: str, **kwargs) -> str:
        """Interface simples — retorna string da resposta final."""
        result = self.run_conversation(user_message=message, **kwargs)
        return result["final_response"]

    async def run_conversation(
        self,
        user_message: str,
        system_message: Optional[str] = None,  # auto-montado se None
        conversation_history: Optional[list] = None,  # carregado do DB se None
        task_id: Optional[str] = None,
        max_iterations: int = 50,
        enable_thinking: bool = False,
    ) -> ConversationResult:
        """
        Interface completa — retorna ConversationResult com:
        final_response, messages, usage, trajectory, session_id
        """
        state = await self._init_state(user_message, system_message,
                                        conversation_history, task_id,
                                        max_iterations)
        try:
            return await self._agent_loop(state)
        finally:
            await self._cleanup(state)
```

### 7.2 Agent Loop — Ciclo Completo

```python
    async def _agent_loop(self, state: AgentState) -> ConversationResult:
        """
        Loop principal do agente.
        Termina quando: LLM retorna texto sem tool_calls,
                        budget esgotado, ou interrupção externa.
        """
        while state.iteration < state.max_iterations:
            # 1. Verifica interrupção externa (novo input do usuário, /stop)
            if state.interrupt_event.is_set():
                return self._build_interrupted_result(state)

            # 2. Budget warnings (injetados como mensagem efêmera)
            budget_warning = self._get_budget_warning(state)

            # 3. Verifica se precisa compressão preflight (contexto > 50%)
            if self._needs_preflight_compression(state):
                await self._compress_context(state)

            # 4. Monta mensagens no formato OpenAI
            api_messages = state.to_openai_messages()
            if budget_warning:
                api_messages.append({"role": "user", "content": budget_warning})

            # 5. Nudge de memória (se aplicável)
            memory_nudge = self.memory_nudge.maybe_inject_nudge(state)
            if memory_nudge:
                api_messages.append({"role": "user", "content": memory_nudge})

            # 6. Chama o LLM (interruptível)
            llm_response = await self._interruptible_llm_call(
                messages=api_messages,
                tools=self._get_active_tool_schemas(state),
                model=self.model_router.get_model(Task.CONVERSATION, state),
                enable_thinking=state.current_tool_calls == [],  # thinking só no início
            )

            state.iteration += 1

            # 7. Salva step na trajetória
            self.trajectory_saver.record_step(state, llm_response)

            # 8. Se há tool calls: executa e continua o loop
            if llm_response.tool_calls:
                await self._execute_tool_calls(llm_response.tool_calls, state)
                continue

            # 9. Resposta final: persiste sessão e encerra
            await self._finalize(state, llm_response)
            return self._build_result(state, llm_response)

        # Budget esgotado
        return self._build_budget_exhausted_result(state)
```

### 7.3 Chamada Interruptível ao LLM

```python
    async def _interruptible_llm_call(
        self,
        messages: list[dict],
        tools: list[dict],
        model: ModelConfig,
        enable_thinking: bool = False,
    ) -> LLMResponse:
        """
        Executa chamada HTTP ao llama-server em thread background.
        O loop principal monitora:
          - resposta pronta
          - interrupt_event (usuário mandou nova mensagem)
          - timeout (30s para resposta curta, 120s para thinking)

        Quando interrompido: a thread HTTP é abandonada, NUNCA injetamos
        resposta parcial no histórico.
        """
        result_holder = {}
        error_holder = {}

        def api_call():
            try:
                resp = self.llm_client.chat_completions(
                    messages=messages,
                    tools=tools,
                    model=model.name,
                    temperature=model.temperature,
                    max_tokens=model.max_tokens,
                    extra_body={"thinking": enable_thinking} if enable_thinking else {},
                )
                result_holder["response"] = resp
            except Exception as e:
                error_holder["error"] = e

        thread = threading.Thread(target=api_call, daemon=True)
        thread.start()

        timeout = 120 if enable_thinking else 30
        deadline = asyncio.get_event_loop().time() + timeout

        while thread.is_alive():
            if self.state.interrupt_event.is_set():
                # Não faz join — abandona a thread
                raise AgentInterruptedException("Interrompido por novo input")
            if asyncio.get_event_loop().time() > deadline:
                raise LLMTimeoutException(f"Timeout após {timeout}s")
            await asyncio.sleep(0.05)

        if "error" in error_holder:
            raise error_holder["error"]

        return LLMResponse.from_raw(result_holder["response"])
```

### 7.4 Execução de Tool Calls

```python
    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        state: AgentState,
    ):
        """
        Single tool call  → execução direta no loop principal
        Multiple tool calls → ThreadPoolExecutor (paralelo)
        Tools interativas (clarify, approve) → sempre sequencial

        Ordem dos resultados preservada independente da ordem de conclusão.
        """
        # Separa interativas das paralelas
        interactive = [tc for tc in tool_calls
                       if tc.function.name in INTERACTIVE_TOOLS]
        parallel   = [tc for tc in tool_calls
                       if tc.function.name not in INTERACTIVE_TOOLS]

        results = {}

        # Executa paralelas via ThreadPool
        if parallel:
            with ThreadPoolExecutor(max_workers=min(len(parallel), 4)) as pool:
                futures = {
                    pool.submit(self._execute_single_tool, tc, state): tc.id
                    for tc in parallel
                }
                for future in as_completed(futures):
                    tc_id = futures[future]
                    try:
                        results[tc_id] = future.result()
                    except Exception as e:
                        results[tc_id] = ToolResult.error(str(e))

        # Executa interativas sequencialmente
        for tc in interactive:
            results[tc.id] = await self._execute_single_tool_async(tc, state)

        # Adiciona resultados ao histórico na ordem original
        for tc in tool_calls:
            state.conversation_history.append(Message(
                role=Role.TOOL,
                tool_call_id=tc.id,
                content=results[tc.id].to_string(),
            ))

    def _execute_single_tool(
        self,
        tool_call: ToolCall,
        state: AgentState,
    ) -> ToolResult:
        """
        Execução de uma única ferramenta com hooks de plugin.
        Intercepta ferramentas agent-level antes do registry.
        """
        fn_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        # Ferramentas interceptadas pelo agente (não passam pelo registry)
        if fn_name == "memory":
            return self._handle_memory_tool(args, state)
        if fn_name == "session_search":
            return self._handle_session_search(args, state)
        if fn_name == "delegate_task":
            return self._handle_delegation(args, state)
        if fn_name == "todo":
            return self._handle_todo(args, state)

        # Hooks de plugin (pre)
        self.plugin_manager.fire_pre_tool(fn_name, args, state)

        # Verifica aprovação
        if self.approval_system.requires_approval(fn_name, args, state):
            approval = self.approval_system.request_approval(fn_name, args, state)
            if not approval.approved:
                return ToolResult.rejected(fn_name)

        # Executa via registry
        result = self.tool_registry.execute(fn_name, args, state)

        # Hooks de plugin (post)
        self.plugin_manager.fire_post_tool(fn_name, args, result, state)

        return result
```

### 7.5 Budget e Warnings

```python
class IterationBudget:
    """
    Rastreia uso do budget de iterações.
    Injeta warnings progressivos conforme esgota.
    """

    def __init__(self, max_iterations: int = 50):
        self.max = max_iterations
        self.used = 0

    def get_warning(self) -> Optional[str]:
        remaining = self.max - self.used
        pct_used = self.used / self.max

        if pct_used >= 0.95:
            return (f"[BUDGET CRÍTICO] {remaining} iteração(ões) restantes. "
                    f"Conclua a tarefa IMEDIATAMENTE ou entregue o que foi feito.")
        if pct_used >= 0.80:
            return (f"[BUDGET] {remaining} iterações restantes. "
                    f"Priorize as ações mais importantes.")
        if pct_used >= 0.60:
            return (f"[INFO] {remaining} iterações restantes de {self.max}.")
        return None
```

---

## 8. Sistema de Prompt Assembly

### 8.1 PromptAssembler

```python
class PromptAssembler:
    """
    Monta o system prompt completo a partir de múltiplas fontes.
    Inspirado no prompt_builder.py do Hermes.
    
    ORDEM DE MONTAGEM:
    1. SOUL.md (personalidade)
    2. MEMORY.md (notas do agente) — frozen snapshot
    3. USER.md (perfil do usuário) — frozen snapshot
    4. Context files (AGENTS.md, .lux.md se existirem)
    5. Skills L0 (lista leve)
    6. Toolsets ativos e descrições de ferramentas
    7. Instruções de uso de ferramentas (how-to-use-tools)
    8. Instruções modelo-específicas (Qwen3 thinking, etc.)
    9. Instruções de budget (injetadas dinamicamente se subagente)
    """

    def build_system_prompt(self, state: AgentState) -> str:
        sections = []

        # 1. Personalidade (SOUL.md)
        soul = self._load_soul(state.user_profile)
        if soul:
            sections.append(soul)

        # 2 + 3. Memória frozen (MEMORY.md + USER.md)
        sections.append(state.memory_snapshot)
        sections.append(state.user_snapshot)

        # 4. Context files (AGENTS.md, .lux.md)
        for path, content in state.context_files.items():
            sections.append(f"### Context: {path}\n{content}")

        # 5. Skills L0
        skills_list = self.skill_manager.get_skills_list_l0(
            state.user_profile, state.channel
        )
        if skills_list:
            skills_block = self._format_skills_list(skills_list)
            sections.append(skills_block)

        # 6. Ferramentas ativas
        tools_summary = self._format_active_tools(state)
        sections.append(tools_summary)

        # 7. Instruções de comportamento
        sections.append(self._get_behavior_instructions(state))

        # 8. Instruções modelo-específicas
        sections.append(self._get_model_specific_instructions())

        # 9. Budget (apenas subagentes)
        if state.is_subagent:
            sections.append(self._get_subagent_instructions(state))

        return "\n\n---\n\n".join(filter(None, sections))

    def _format_skills_list(self, skills: list[SkillSummary]) -> str:
        """
        Lista L0 de skills — leve, apenas nome + descrição curta.
        Informa ao agente que pode carregar o conteúdo completo com skill_view().
        """
        lines = ["## Skills Disponíveis\n"
                 "Use `skills_list()` para detalhes ou `/<skill-name>` para ativar.\n"]
        for s in skills:
            cmd = f"  `/{s.name}`" if s.slash_command else ""
            lines.append(f"- **{s.name}**{cmd}: {s.description}")
        return "\n".join(lines)

    def _get_behavior_instructions(self, state: AgentState) -> str:
        user = state.user_profile
        return f"""
## Comportamento

Idioma: {user.preferred_language}
Estilo: {user.response_style.value} | Formalidade: {user.formality.value}
Canal: {state.channel.value}

Regras de memória:
- Use `memory(action="add", target="memory")` para persistir fatos do ambiente
- Use `memory(action="add", target="user")` para persistir preferências do usuário
- Salve PROATIVAMENTE — não espere ser pedido
- Quando memória estiver cheia, consolide entradas antigas antes de adicionar novas

Regras de skills:
- Carregue skills completas (L1) apenas quando necessário para a tarefa atual
- Após tarefas complexas bem-sucedidas (>5 steps), considere criar uma nova skill
""".strip()
```

### 8.2 Context Files

```python
class ContextFileLoader:
    """
    Carrega arquivos de contexto de projeto (AGENTS.md, .lux.md).
    Inspirado no context_files do Hermes.
    
    Hierarquia de busca:
    1. Diretório de trabalho atual: ./.lux.md, ./AGENTS.md
    2. Diretório pai: ../.lux.md
    3. Home: ~/.lux/global-context.md
    
    Permite configuração de comportamento por projeto sem alterar o agente.
    """

    CONTEXT_FILENAMES = [".lux.md", "AGENTS.md", ".hermes.md"]

    def load_for_workspace(self, workspace: str) -> dict[str, str]:
        """
        Busca e carrega context files para o workspace atual.
        Limita a 2048 tokens por arquivo para não estourar o contexto.
        """
        path = Path(workspace)
        loaded = {}
        while path != path.parent:
            for filename in self.CONTEXT_FILENAMES:
                f = path / filename
                if f.exists() and f.is_file():
                    content = f.read_text()[:8192]  # 8KB max por arquivo
                    loaded[str(f)] = content
                    break  # um arquivo por diretório
            path = path.parent
            if str(path) == str(Path.home()):
                break
        return loaded
```

---

## 9. Compressão de Contexto e Session Lineage

### 9.1 ContextCompressor

```python
class ContextCompressor:
    """
    Compressão lossy do histórico de conversa quando contexto excede thresholds.
    Preserva últimas N mensagens intactas.
    Garante que pares tool_call/tool_result nunca sejam separados.
    
    Thresholds:
      CLI:     50% do ctx_size → compressão preflight
      Gateway: 85% → compressão entre turns (mais agressivo)
    """

    PROTECT_LAST_N = 20    # preserva últimas 20 mensagens

    async def compress(self, state: AgentState,
                        threshold_pct: float = 0.50) -> bool:
        """
        Retorna True se compressão foi necessária.
        """
        ctx_size = self._estimate_context_tokens(state)
        model_ctx = self._get_model_ctx_size(state)

        if ctx_size / model_ctx < threshold_pct:
            return False

        # Flush de memória ANTES de comprimir (nunca perde dados)
        await self._flush_pending_memory(state)

        # Separa: mensagens a comprimir + mensagens a preservar
        history = state.conversation_history
        to_compress = history[:-self.PROTECT_LAST_N]
        to_keep = history[-self.PROTECT_LAST_N:]

        # Garante que to_compress não termina no meio de um par tool_call/result
        to_compress, rescued = self._rescue_tool_pairs(to_compress, to_keep)

        # Sumariza com o modelo auxiliar (1.7B, rápido)
        summary = await self.aux_llm.generate(
            COMPRESSION_PROMPT.format(
                conversation=self._format_for_compression(to_compress),
                user_display_name=state.user_profile.display_name,
            ),
            model=Task.SUMMARIZE_SHORT,
            max_tokens=1024,
        )

        # Cria nova sessão "filha" com lineage tracking
        new_session_id = await self.session_db.create_child_session(
            parent_session_id=state.session_id,
            compression_summary=summary,
            messages_compressed=len(to_compress),
        )
        state.session_lineage_id = new_session_id
        state.compression_count += 1

        # Substitui histórico: mensagem de resumo + mensagens preservadas
        summary_msg = Message(
            role=Role.SYSTEM,
            content=f"[RESUMO DA CONVERSA ANTERIOR]\n{summary}",
        )
        state.conversation_history = [summary_msg] + rescued + to_keep
        return True

    def _rescue_tool_pairs(
        self,
        to_compress: list[Message],
        to_keep: list[Message],
    ) -> tuple[list[Message], list[Message]]:
        """
        Garante que nenhum tool_call fique sem seu tool_result.
        Se o split separaria um par, move o tool_result para to_keep.
        """
        rescued = []
        # Encontra tool_calls sem result no to_compress
        tool_call_ids_in_compress = {
            tc.id
            for msg in to_compress
            if msg.tool_calls
            for tc in msg.tool_calls
        }
        tool_result_ids_in_compress = {
            msg.tool_call_id
            for msg in to_compress
            if msg.role == Role.TOOL
        }
        orphaned_calls = tool_call_ids_in_compress - tool_result_ids_in_compress

        if orphaned_calls:
            # Move os pares órfãos do to_compress para rescued
            i = len(to_compress) - 1
            while i >= 0 and orphaned_calls:
                msg = to_compress[i]
                if msg.role == Role.ASSISTANT and any(
                    tc.id in orphaned_calls for tc in (msg.tool_calls or [])
                ):
                    rescued.insert(0, to_compress.pop(i))
                    orphaned_calls -= {tc.id for tc in msg.tool_calls}
                i -= 1

        return to_compress, rescued
```

### 9.2 Session Lineage

```
TRACKING DE LINHAGEM:

session_001 (original, 50 mensagens)
    │ compression → session_002
    │
    └── session_002 (resumo + últimas 20 msgs)
            │ compression → session_003
            │
            └── session_003 (resumo do resumo + últimas 20 msgs)

Cada sessão filha tem:
  - parent_session_id → referência à mãe
  - compression_summary → o que foi perdido
  - messages_before_compression → count para auditoria

O session_search consegue buscar em TODA a árvore de linhagem,
não apenas na sessão atual.
```

---

## 10. Sistema de Ferramentas e Toolsets

### 10.1 Toolsets — Agrupamento

```python
TOOLSETS = {
    "terminal": Toolset(
        name="terminal",
        description="Execução de comandos shell e operações de filesystem",
        tools=["shell_run", "file_read", "file_write", "file_append",
               "file_delete", "directory_list", "directory_create",
               "search_files", "patch_file"],
        requires_approval=True,         # comandos podem ser perigosos
        min_role=UserRole.ADMIN,
    ),
    "web": Toolset(
        name="web",
        description="Busca web e extração de conteúdo de URLs",
        tools=["web_search", "web_fetch", "web_summarize"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "email": Toolset(
        name="email",
        description="Leitura e envio de e-mails via IMAP/SMTP",
        tools=["email_list", "email_read", "email_compose",
               "email_send", "email_reply", "email_search"],
        requires_approval=True,         # envio requer confirmação
        min_role=UserRole.USER,
    ),
    "calendar": Toolset(
        name="calendar",
        description="Calendário e lembretes",
        tools=["calendar_read", "calendar_create", "reminder_set",
               "reminder_list", "reminder_cancel"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "tasks": Toolset(
        name="tasks",
        description="Gestão de tarefas em markdown local",
        tools=["task_create", "task_list", "task_complete", "task_update"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "memory_tools": Toolset(
        name="memory_tools",
        description="Gestão explícita de memória (raramente chamada diretamente)",
        tools=["memory", "session_search", "semantic_recall"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "skills": Toolset(
        name="skills",
        description="Gerenciamento de skills",
        tools=["skills_list", "skill_view", "skill_create", "skill_update"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "git": Toolset(
        name="git",
        description="Operações Git",
        tools=["git_status", "git_diff", "git_commit", "git_push",
               "git_pull", "git_log", "git_branch"],
        requires_approval=True,
        min_role=UserRole.USER,
    ),
    "system": Toolset(
        name="system",
        description="Status do sistema Lux",
        tools=["status_check", "vram_status", "session_info",
               "profile_switch", "settings_update"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "subagent": Toolset(
        name="subagent",
        description="Delegação de tarefas para subagentes paralelos",
        tools=["delegate_task", "todo"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
}
```

### 10.2 ToolRegistry

```python
class ToolRegistry:
    """
    Registry central. Ferramentas se registram no import time.
    Gerencia discovery, schema, dispatch e error wrapping.
    """

    _registry: dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool):
        """Decorator para registro automático."""
        cls._registry[tool.name] = tool

    def get_active_schemas(self, user: UserProfile,
                            toolsets: list[str]) -> list[dict]:
        """
        Retorna schemas de todas as ferramentas nos toolsets ativos
        que o usuário tem permissão de usar.
        Formato OpenAI tool calling.
        """
        active = []
        for toolset_name in toolsets:
            toolset = TOOLSETS.get(toolset_name)
            if not toolset:
                continue
            if not self._user_can_use_toolset(user, toolset):
                continue
            for tool_name in toolset.tools:
                tool = self._registry.get(tool_name)
                if tool:
                    active.append(tool.to_openai_schema())
        return active

    def execute(self, name: str, args: dict,
                state: AgentState) -> ToolResult:
        """Dispatch com error wrapping e timeout."""
        tool = self._registry.get(name)
        if not tool:
            return ToolResult.error(f"Ferramenta '{name}' não encontrada.")
        try:
            with timeout(tool.timeout_seconds):
                return tool.execute(args, state)
        except TimeoutError:
            return ToolResult.error(f"Timeout após {tool.timeout_seconds}s.")
        except Exception as e:
            logger.error(f"Tool {name} falhou: {e}", exc_info=True)
            return ToolResult.error(str(e))
```

---

## 11. Subagente e Delegação Paralela

### 11.1 DelegateTaskTool

```python
class DelegateTaskTool(Tool):
    """
    Cria subagentes isolados para tarefas paralelas.
    Inspirado no delegate_tool.py do Hermes.
    
    Casos de uso:
    - "Pesquise X enquanto eu processo Y"
    - Tarefa complexa que pode ser dividida em subtarefas independentes
    - Operações longas que não precisam do contexto completo da sessão mãe
    """
    name = "delegate_task"

    class Input(BaseModel):
        task: str                        # descrição da tarefa para o subagente
        context: Optional[str] = None    # contexto relevante (não passa histórico completo)
        toolsets: list[str] = []         # toolsets que o subagente pode usar
        max_iterations: int = 20         # budget máximo (menor que o pai)

    async def execute(self, params: Input,
                      state: AgentState) -> ToolResult:
        # Subagentes têm budget isolado e capped
        sub_max = min(params.max_iterations,
                      state.max_iterations - state.iteration)
        if sub_max <= 0:
            return ToolResult.error("Budget esgotado — não é possível delegar.")

        subagent = AIAgent(
            user_id=state.user_id,
            session_id=f"{state.session_id}_sub_{uuid4().hex[:8]}",
            is_subagent=True,
            parent_task_id=state.task_id,
            max_iterations=sub_max,
            enabled_toolsets=params.toolsets or state.user_profile.enabled_toolsets,
        )

        # Subagente não recebe histórico completo — apenas contexto fornecido
        initial_context = params.context or ""
        result = await subagent.run_conversation(
            user_message=params.task,
            system_message=initial_context,
        )
        return ToolResult(
            success=True,
            output=result["final_response"],
            data={"iterations_used": result["iterations_used"]},
            side_effects=[f"Subagente executou {result['iterations_used']} iterações"],
        )
```

### 11.2 TodoTool — Estado Local do Agente

```python
class TodoTool(Tool):
    """
    Lista de tarefas local do agente — não do usuário.
    Usada pelo agente para rastrear seu próprio progresso em tarefas longas.
    
    Hermes usa isso em run_agent.py para que o agente não perca
    o fio da meada em tarefas multi-step.
    """
    name = "todo"

    class Input(BaseModel):
        action: Literal["add", "complete", "list", "clear"]
        item: Optional[str] = None
        item_id: Optional[int] = None

    def execute(self, params: Input, state: AgentState) -> ToolResult:
        # Estado de todo é agent-local, não persiste entre sessões
        todos = state.agent_todos  # list[TodoItem]
        match params.action:
            case "add":
                item = TodoItem(id=len(todos)+1, text=params.item,
                                done=False, created_at=datetime.now())
                todos.append(item)
                return ToolResult.ok(f"[{item.id}] {item.text} adicionado.")
            case "complete":
                item = next((t for t in todos if t.id == params.item_id), None)
                if not item:
                    return ToolResult.error(f"Item {params.item_id} não encontrado.")
                item.done = True
                return ToolResult.ok(f"[{item.id}] Marcado como concluído.")
            case "list":
                if not todos:
                    return ToolResult.ok("Lista vazia.")
                lines = [f"{'✓' if t.done else '○'} [{t.id}] {t.text}"
                         for t in todos]
                return ToolResult.ok("\n".join(lines))
            case "clear":
                todos.clear()
                return ToolResult.ok("Lista limpa.")
```

---

## 12. Sistema de Aprovação de Comandos

### 12.1 ApprovalSystem

```python
class ApprovalSystem:
    """
    Detecta comandos perigosos e gerencia aprovação do usuário.
    Inspirado no approval.py do Hermes.
    
    Mais granular que o AutonomyLevel global do Lux v1.0:
    padrões específicos de comando em vez de categorias amplas.
    """

    # Padrões SEMPRE perigosos — bloqueados ou exigem aprovação explícita
    ALWAYS_DANGEROUS = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+~",
        r"dd\s+if=",
        r"mkfs\.",
        r">\s*/dev/(sd|nvme|hd)",
        r"curl\s+.*\|\s*(sudo\s+)?ba?sh",
        r"wget\s+.*\|\s*(sudo\s+)?ba?sh",
        r"chmod\s+777\s+/",
        r":(){ :|:& };:",          # fork bomb
        r"sudo\s+rm\s+-rf",
    ]

    # Padrões moderados — pedem aprovação mas não bloqueiam
    WARN_PATTERNS = [
        r"\bsudo\b",
        r"\bdrop\s+table\b",
        r"\bdelete\s+from\b",
        r"\btruncate\b",
        r"\bgit\s+push\s+--force\b",
        r"\bgit\s+reset\s+--hard\b",
        r"pkill\s+-9",
        r"kill\s+-9",
    ]

    def requires_approval(self, tool_name: str,
                           args: dict,
                           state: AgentState) -> bool:
        """
        Decide se uma tool call precisa de aprovação humana.
        
        Prioridade:
        1. Padrão de auto-approve do usuário → não pede
        2. Padrão ALWAYS_DANGEROUS → SEMPRE pede (não pode ser desabilitado)
        3. Toolset.requires_approval = True → pede (exceto se no allowlist)
        4. Padrão WARN → pede
        """
        # Extrai o comando do args (se for shell_run)
        command = args.get("command", "") if tool_name == "shell_run" else ""

        # Auto-approve patterns do usuário
        user = state.user_profile
        for pattern in user.approval_patterns:
            if re.search(pattern.regex, command or tool_name):
                return False

        # Always dangerous — sem exceção
        for pattern in self.ALWAYS_DANGEROUS:
            if re.search(pattern, command, re.IGNORECASE):
                return True

        # Toolset requires_approval
        toolset = self._get_toolset_for_tool(tool_name)
        if toolset and toolset.requires_approval:
            # Verifica allowlist do toolset
            for allow in user.approval_patterns:
                if allow.toolset == toolset.name and allow.always_allow:
                    return False
            return True

        # Warn patterns
        for pattern in self.WARN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True

        return False

    def request_approval(self, tool_name: str,
                          args: dict,
                          state: AgentState) -> ApprovalResult:
        """
        Apresenta o comando ao usuário e aguarda aprovação.
        Suporta: [s]im, [n]ão, [a]uto-aprovar sempre, [e]ditar comando
        """
        preview = self._format_command_preview(tool_name, args)
        callback = state.approval_callback

        if callback:
            return callback(preview, tool_name, args)

        # Fallback: input() no terminal
        print(f"\n⚠️  Aprovação necessária:\n{preview}\n")
        choice = input("[s]im / [n]ão / [a]uto-aprovar sempre: ").strip().lower()
        match choice:
            case "s" | "sim" | "y" | "yes":
                return ApprovalResult(approved=True)
            case "a" | "auto":
                # Adiciona ao allowlist do usuário
                self._add_to_allowlist(tool_name, args, state.user_profile)
                return ApprovalResult(approved=True, added_to_allowlist=True)
            case _:
                return ApprovalResult(approved=False)
```

---

## 13. Pipeline de Voz

### 13.1 Arquitetura de Voz Local

```
ENTRADA DE VOZ:
  Microfone
    │
    ▼
  SileroVAD (CPU, ~3ms)         detecta início/fim de fala
    │ segmento de áudio
    ▼
  WakeWordDetector (CPU)         verifica "lux" / "hey lux"
    │ confirmado
    ▼
  Whisper.cpp small (VRAM ~466MB, sob demanda)
    │ texto transcrito
    ▼
  [pipeline normal de texto]

SAÍDA DE VOZ:
  Resposta do LLM (streaming por sentença)
    │
    ▼
  SpeechPreprocessor               remove markdown, expande siglas
    │
    ▼
  Piper TTS pt_BR-faber-medium     CPU-only, ~100-200ms por sentença
    │ áudio gerado
    ▼
  Alto-falante (streaming)

LATÊNCIA PERCEBIDA ESTIMADA:
  VAD detect:      ~50ms
  Wake word:       ~100ms
  Whisper small:   ~500ms (até 10s de fala)
  LLM 1ª sentença: ~800ms (Qwen3-14B Q4_K_M)
  Piper 1ª frase:  ~150ms
  ─────────────────────────
  Total até início da fala: ~1.6s ✓
```

### 13.2 VoicePipeline

```python
class VoicePipeline:
    def __init__(self, vad: SileroVAD, wake_word: WakeWordDetector,
                 stt: WhisperCpp, tts: PiperTTS,
                 vram_guard: VRAMGuard):
        self.vad = vad
        self.wake_word = wake_word
        self.stt = stt
        self.tts = tts
        self.vram_guard = vram_guard
        self.is_speaking = False

    async def listen_once(self) -> Optional[str]:
        """
        Uma rodada completa de escuta:
        1. VAD detecta onset de fala
        2. Grava até silêncio (>1.5s)
        3. Verifica wake word no transcrito
        4. Se confirmado: retorna texto
        5. Descarrega Whisper se VRAM > threshold
        """
        audio_segment = await self.vad.record_until_silence(
            silence_threshold_ms=1500,
            max_duration_s=30,
        )
        if audio_segment is None:
            return None

        # Carrega Whisper apenas se há VRAM disponível
        if not await self.vram_guard.can_load_model("whisper-small", 0.5):
            logger.warning("VRAM insuficiente para Whisper — pulando STT")
            return None

        await self.stt.ensure_loaded()
        transcript = await self.stt.transcribe(audio_segment,
                                                language="pt")

        # Libera Whisper se VRAM > 85%
        if await self.vram_guard.usage_ratio() > 0.85:
            await self.stt.unload()

        return transcript

    async def speak_streaming(self, text_generator: AsyncGenerator[str, None],
                               user: UserProfile):
        """
        Streaming de TTS: começa a falar antes do LLM terminar.
        1. Acumula tokens até fim de sentença (., !, ?, newline)
        2. Envia sentença para Piper
        3. Reproduz enquanto LLM continua gerando
        """
        self.is_speaking = True
        buffer = ""
        sentence_enders = {'.', '!', '?', '\n'}

        async for token in text_generator:
            buffer += token
            if any(buffer.rstrip().endswith(e) for e in sentence_enders):
                clean = self._prepare_for_speech(buffer.strip())
                if clean:
                    audio = await self.tts.synthesize(
                        text=clean,
                        voice=user.preferred_voice,
                    )
                    await self._play_audio(audio)
                buffer = ""

        # Flush do buffer restante
        if buffer.strip():
            clean = self._prepare_for_speech(buffer.strip())
            if clean:
                audio = await self.tts.synthesize(clean, user.preferred_voice)
                await self._play_audio(audio)

        self.is_speaking = False

    def _prepare_for_speech(self, text: str) -> str:
        """
        Pré-processamento para síntese de voz:
        - Remove markdown (**bold**, *italic*, `code`, # headers, etc.)
        - Expande siglas: API→"á-pi-í", URL→"u-r-l", etc.
        - Remove URLs completas
        - Converte listas para linguagem natural ("primeiro... segundo...")
        - Normaliza pontuação para prosódia natural
        """
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)      # bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)           # italic
        text = re.sub(r'`[^`]+`', '', text)                # inline code
        text = re.sub(r'```[\s\S]+?```', '', text)         # code block
        text = re.sub(r'#{1,6}\s+', '', text)              # headers
        text = re.sub(r'https?://\S+', 'link', text)       # URLs
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links MD
        for acronym, spoken in ACRONYM_MAP.items():
            text = text.replace(acronym, spoken)
        return text.strip()
```

---

## 14. Gerenciador de Modelos e VRAM

### 14.1 VRAMGuard

```python
class VRAMGuard:
    """
    Circuit breaker de VRAM para AMD ROCm (rocm-smi) e NVIDIA (nvidia-smi).
    Monitora em background e toma ações preventivas antes de OOM.
    """

    def __init__(self, budget_gb: float):
        self.budget = budget_gb
        self.thresholds = {
            "nominal":  budget_gb * 0.75,   # 12.0GB — operação normal
            "warning":  budget_gb * 0.82,   # 13.1GB — log warning
            "critical": budget_gb * 0.88,   # 14.1GB — pausa Whisper
            "oom":      budget_gb * 0.94,   # 15.0GB — ação imediata
        }
        self.model_vram = {
            "qwen3-14b-q4":    9.5,
            "qwen3-1.7b-q4":   1.2,
            "whisper-small":   0.5,
            "bge-reranker":    0.7,
            "all-minilm":      0.1,
        }

    async def get_usage(self) -> float:
        """Retorna VRAM usada em GB via rocm-smi ou nvidia-smi."""
        try:
            if shutil.which("rocm-smi"):
                out = await asyncio.create_subprocess_exec(
                    "rocm-smi", "--showmeminfo", "vram", "--json",
                    stdout=asyncio.subprocess.PIPE
                )
                stdout, _ = await out.communicate()
                data = json.loads(stdout)
                # Parse output do ROCm SMI
                used_bytes = int(data["card0"]["VRAM Total Used Memory (B)"])
                return used_bytes / (1024**3)
            elif shutil.which("nvidia-smi"):
                out = await asyncio.create_subprocess_exec(
                    "nvidia-smi", "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                    stdout=asyncio.subprocess.PIPE
                )
                stdout, _ = await out.communicate()
                used_mb = float(stdout.decode().strip())
                return used_mb / 1024
        except Exception:
            return 0.0  # fallback seguro

    async def can_load_model(self, model_name: str,
                              vram_gb: Optional[float] = None) -> bool:
        """Verifica se há VRAM disponível para carregar um modelo."""
        cost = vram_gb or self.model_vram.get(model_name, 1.0)
        current = await self.get_usage()
        return (current + cost) < self.thresholds["critical"]

    async def monitor_loop(self, agent: "AIAgent"):
        """Loop de monitoramento contínuo em background."""
        while True:
            usage = await self.get_usage()
            ratio = usage / self.budget

            if usage >= self.thresholds["oom"]:
                logger.critical(f"VRAM OOM: {usage:.1f}GB/{self.budget}GB")
                await self._handle_oom(agent)

            elif usage >= self.thresholds["critical"]:
                logger.error(f"VRAM crítica: {usage:.1f}GB/{self.budget}GB")
                await self._handle_critical(agent)

            elif usage >= self.thresholds["warning"]:
                logger.warning(f"VRAM alta: {usage:.1f}GB/{self.budget}GB")

            await asyncio.sleep(3)  # polling a cada 3s

    async def _handle_oom(self, agent):
        """
        Ação de emergência OOM:
        1. Descarrega Whisper (libera ~0.5GB)
        2. Descarrega bge-reranker (libera ~0.7GB)
        3. Força GC do PyTorch/ROCm
        4. Reduz ctx_size do 14B via API de gerenciamento
        5. Notifica usuário no canal ativo
        """
```

---

## 15. Gateway Multi-Plataforma

### 15.1 GatewayRunner

```python
class GatewayRunner:
    """
    Processo de longa duração que recebe mensagens de múltiplas plataformas
    e despacha para AIAgent. Inspirado no gateway/run.py do Hermes.
    
    Plataformas suportadas:
      Fase 1: Telegram, Discord, CLI
      Fase 2: Slack, E-mail, WhatsApp
      Fase 3: Matrix, Webhook, API Server
    """

    async def handle_message(self, event: MessageEvent):
        """
        Fluxo de processamento de mensagem via gateway:
        1. Autoriza usuário (pairing / whitelist)
        2. Resolve sessão (por user_id + channel)
        3. Carrega histórico da sessão do SQLite
        4. Cria AIAgent com contexto da sessão
        5. Executa run_conversation()
        6. Entrega resposta de volta pela plataforma
        7. Salva sessão atualizada
        """
        user = await self._authorize(event)
        if not user:
            await event.reply("Não autorizado.")
            return

        session = await self.session_store.get_or_create(
            user_id=user.user_id,
            channel=event.channel,
        )
        history = await self.session_store.load_history(session.id, limit=50)

        # Gateway usa compressão mais agressiva (85% vs 50% do CLI)
        agent = AIAgent(
            user_id=user.user_id,
            session_id=session.id,
            compression_threshold=0.85,
            max_iterations=30,   # gateway tem budget menor que CLI
        )

        # Streaming para plataformas que suportam (Telegram, Discord)
        if event.channel.supports_streaming:
            async for chunk in agent.run_streaming(event.content, history):
                await event.update_partial(chunk)
        else:
            result = await agent.run_conversation(
                event.content,
                conversation_history=history
            )
            await event.reply(result["final_response"])

        await self.session_store.save(session.id, agent.state)
```

### 15.2 Adapters

```python
class PlatformAdapter(ABC):
    """Interface base para todos os adapters de plataforma."""

    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def on_message(self, raw_event: Any) -> MessageEvent: ...

    @abstractmethod
    async def send_message(self, user_id: str, content: str,
                           reply_to: Optional[str] = None): ...

    @abstractmethod
    async def send_partial(self, user_id: str, content: str,
                           message_id: str): ...

    @property
    @abstractmethod
    def supports_streaming(self) -> bool: ...

# Implementações:
class TelegramAdapter(PlatformAdapter):
    """Suporte completo: texto, voz (voice memo → STT), documentos."""
    supports_streaming = True  # edita mensagem progressivamente

class DiscordAdapter(PlatformAdapter):
    """Suporte: texto, embeds, thread por conversa, slash commands."""
    supports_streaming = True

class SlackAdapter(PlatformAdapter):
    """Suporte: texto, blocks, thread replies."""
    supports_streaming = False

class EmailAdapter(PlatformAdapter):
    """Leitura IMAP, resposta SMTP."""
    supports_streaming = False

class WhatsAppAdapter(PlatformAdapter):
    """Via whatsapp-web.js ou API oficial."""
    supports_streaming = False
```

---

## 16. Scheduler e Proatividade

### 16.1 CronScheduler

```python
class CronScheduler:
    """
    Scheduler de tarefas agendadas em linguagem natural.
    Jobs armazenados em ~/.lux/cron/jobs.json.
    Inspirado no cron/ do Hermes.
    """

    async def run_due_jobs(self):
        """
        Verifica e executa jobs cujo next_run <= now().
        Cria AIAgent fresco para cada job (sem histórico de sessão).
        Skills do job são injetadas como context.
        Entrega resposta na plataforma configurada.
        """
        due_jobs = await self.jobs_store.get_due()
        for job in due_jobs:
            await self._execute_job(job)

    async def _execute_job(self, job: CronJob):
        agent = AIAgent(
            user_id=job.user_id,
            session_id=f"cron_{job.id}_{int(time.time())}",
            max_iterations=20,           # budget conservador para cron
            enabled_toolsets=job.toolsets,
        )
        # Injeta skills do job como context_files
        skill_context = "\n\n".join(
            self.skill_manager.get_skill_content_l1(s)
            for s in job.skills
        )

        result = await agent.run_conversation(
            user_message=job.prompt,
            system_message=skill_context or None,
        )
        await self._deliver(result["final_response"], job)
        await self.jobs_store.update_next_run(job)

@dataclass
class CronJob:
    id: str
    user_id: str
    name: str
    prompt: str                  # ex: "Resuma os e-mails não lidos de hoje"
    schedule: str                # cron expression: "0 9 * * 1-5"
    skills: list[str]            # skills a injetar no contexto
    toolsets: list[str]          # ferramentas disponíveis
    delivery_channel: Channel    # onde entregar o resultado
    delivery_target: str         # user_id, chat_id, etc.
    is_active: bool
    last_run: Optional[datetime]
    next_run: datetime
    run_count: int
```

### 16.2 Proactive Triggers

```python
class ProactiveTriggerEngine:
    """
    Triggers condicionais que disparam sem schedule fixo.
    Avalia condições periodicamente e age quando satisfeitas.
    """

    BUILT_IN_TRIGGERS = [
        ProactiveTrigger(
            id="vram_high",
            condition="VRAM > 90% por 5+ minutos",
            action="Alertar usuário sobre uso elevado de VRAM e sugerir ações",
            autonomy=AutonomyLevel.NOTIFY,
            cooldown_minutes=30,
        ),
        ProactiveTrigger(
            id="long_session",
            condition="Sessão com >60 messages sem salvar memória relevante",
            action="Fazer backup de memória da sessão",
            autonomy=AutonomyLevel.SILENT,
            cooldown_minutes=0,  # sem cooldown
        ),
    ]

    async def evaluate_all(self, state: AgentState):
        """Avalia todos os triggers ativos para o usuário."""
        user_triggers = await self.triggers_db.get_active(state.user_id)
        all_triggers = self.BUILT_IN_TRIGGERS + user_triggers

        for trigger in all_triggers:
            if await self._should_fire(trigger, state):
                await self._fire(trigger, state)
```

---

## 17. Sistema de Plugins e Hooks

### 17.1 PluginManager

```python
class PluginManager:
    """
    Sistema de plugins com hooks para extensão do comportamento do agente.
    Inspirado no plugins.py do Hermes.
    
    Tipos de hook:
      pre_tool_call   → antes de executar uma ferramenta
      post_tool_call  → após executar uma ferramenta
      pre_llm_call    → antes de chamar o LLM
      post_llm_call   → após receber resposta do LLM
      on_session_start → ao iniciar uma sessão
      on_session_end   → ao encerrar uma sessão
      on_memory_write  → ao persistir uma memória
    """

    def __init__(self, plugins_dir: Path):
        self.plugins: list[Plugin] = []
        self._discover_and_load(plugins_dir)

    def _discover_and_load(self, plugins_dir: Path):
        """Auto-descobre plugins em ~/.lux/plugins/."""
        for plugin_path in plugins_dir.glob("*/plugin.py"):
            try:
                spec = importlib.util.spec_from_file_location(
                    plugin_path.parent.name, plugin_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "LuxPlugin"):
                    plugin = module.LuxPlugin()
                    self.plugins.append(plugin)
                    logger.info(f"Plugin carregado: {plugin.name}")
            except Exception as e:
                logger.error(f"Falha ao carregar plugin {plugin_path}: {e}")

    def fire_pre_tool(self, tool_name: str, args: dict,
                       state: AgentState) -> Optional[ToolResult]:
        """
        Chama todos os hooks pre_tool_call.
        Se algum plugin retornar ToolResult, a ferramenta real é cancelada.
        (Permite interceptar e substituir ferramentas)
        """
        for plugin in self.plugins:
            if hasattr(plugin, "pre_tool_call"):
                result = plugin.pre_tool_call(tool_name, args, state)
                if result is not None:
                    return result  # interceptado pelo plugin
        return None

    def fire_post_tool(self, tool_name: str, args: dict,
                        result: ToolResult, state: AgentState):
        for plugin in self.plugins:
            if hasattr(plugin, "post_tool_call"):
                plugin.post_tool_call(tool_name, args, result, state)
```

### 17.2 Exemplo de Plugin

```python
# ~/.lux/plugins/audit_logger/plugin.py

class LuxPlugin:
    """Plugin de auditoria — loga todas as tool calls em arquivo."""
    name = "audit_logger"
    version = "1.0.0"

    def __init__(self):
        self.log_path = Path("~/.lux/audit.log").expanduser()

    def pre_tool_call(self, tool_name: str, args: dict,
                       state) -> None:
        # Não intercepta — apenas loga
        return None

    def post_tool_call(self, tool_name: str, args: dict,
                        result, state):
        entry = {
            "ts": datetime.now().isoformat(),
            "user": state.user_id,
            "tool": tool_name,
            "success": result.success,
            "side_effects": result.side_effects,
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
```

---

## 18. Session Storage com FTS5

### 18.1 SessionDB — SQLite com FTS5

```python
class SessionDB:
    """
    Armazenamento de sessões com full-text search.
    Inspirado no hermes_state.py do Hermes.
    
    SQLite com FTS5 para busca textual exata em sessões passadas.
    Suporta: lineage tracking, compressão, busca cross-session.
    """

    def __init__(self, db_path: str = "~/.lux/sessions.db"):
        self.db_path = Path(db_path).expanduser()
        self._init_schema()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id           TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL,
                channel      TEXT NOT NULL,
                parent_id    TEXT,                    -- linhagem de compressão
                lineage_root TEXT,                    -- raiz da linhagem
                started_at   TEXT NOT NULL,
                ended_at     TEXT,
                message_count INT DEFAULT 0,
                tokens_used  INT DEFAULT 0,
                compressed   BOOLEAN DEFAULT FALSE,
                summary      TEXT                     -- resumo de compressão
            );

            CREATE TABLE IF NOT EXISTS messages (
                id           TEXT PRIMARY KEY,
                session_id   TEXT NOT NULL REFERENCES sessions(id),
                user_id      TEXT NOT NULL,
                role         TEXT NOT NULL,
                content      TEXT NOT NULL,
                thinking     TEXT,
                tool_calls   TEXT,                    -- JSON
                tool_call_id TEXT,
                model_used   TEXT,
                tokens_used  INT,
                timestamp    TEXT NOT NULL,
                iteration    INT
            );

            -- FTS5 virtual table para busca textual
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
            USING fts5(
                content,
                thinking,
                content='messages',
                content_rowid='rowid',
                tokenize='porter unicode61'    -- stemming em pt e en
            );

            -- Trigger para manter FTS5 sincronizado
            CREATE TRIGGER IF NOT EXISTS messages_ai
            AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content, thinking)
                VALUES (new.rowid, new.content, new.thinking);
            END;
            """)

    async def fts_search(self, query: str, user_id: str,
                          limit: int = 5) -> list[SessionSearchResult]:
        """
        Busca FTS5 em todas as sessões do usuário.
        Retorna snippets relevantes com contexto.
        
        Suporta: booleans (AND, OR, NOT), frases entre aspas, prefixos (termo*)
        Exemplo: "rate limiting" AND rust → busca exata + keyword
        """
        sql = """
        SELECT
            m.id,
            m.session_id,
            m.timestamp,
            m.role,
            snippet(messages_fts, 0, '<b>', '</b>', '...', 15) AS snippet,
            bm25(messages_fts) AS score
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH ?
          AND s.user_id = ?
          AND m.role IN ('user', 'assistant')
        ORDER BY score
        LIMIT ?
        """
        rows = await self._aexecute(sql, (query, user_id, limit))
        return [SessionSearchResult.from_row(r) for r in rows]

    async def create_child_session(self, parent_session_id: str,
                                    compression_summary: str,
                                    messages_compressed: int) -> str:
        """
        Cria sessão filha após compressão.
        Preserva lineage_root para busca across lineage.
        """
        parent = await self.get_session(parent_session_id)
        child_id = str(uuid4())
        lineage_root = parent.lineage_root or parent_session_id

        await self._aexecute("""
            INSERT INTO sessions (id, user_id, channel, parent_id, lineage_root,
                                   started_at, compressed, summary)
            VALUES (?, ?, ?, ?, ?, ?, TRUE, ?)
        """, (child_id, parent.user_id, parent.channel, parent_session_id,
              lineage_root, datetime.now().isoformat(), compression_summary))

        await self._aexecute("""
            UPDATE sessions SET ended_at = ?, compressed = TRUE WHERE id = ?
        """, (datetime.now().isoformat(), parent_session_id))

        return child_id
```

---

## 19. Personalidade — SOUL.md e Context Files

### 19.1 SOUL.md

```markdown
# ~/.lux/SOUL.md
# Personalidade do Lux — editável pelo usuário

Você é o **Lux**, assistente pessoal de {user.display_name}.

## Caráter
- Direto e objetivo — não enrola, responde o que foi pedido
- Tecnicamente profundo quando a situação pede, simples quando não
- Levemente informal no dia a dia, profissional em contextos de trabalho
- Não usa "Com certeza!", "Absolutamente!" ou outros enchimentos
- Prefere "Entendido.", "Feito.", "Pronto." para confirmações

## Comportamento Padrão
- Respostas concisas a menos que detalhes sejam pedidos
- Usa markdown apenas em respostas de texto (nunca em voz)
- Faz uma pergunta por vez quando precisar clarificar
- Salva memória proativamente — não espera ser pedido

## Idioma
- Responde em português brasileiro por padrão
- Troca para inglês se o usuário escrever em inglês
- Nunca mistura idiomas na mesma resposta

## Linha de base de personalidade
{user.persona_traits}
```

### 19.2 Context Files Hierárquicos

```
Hierarquia de busca de context files:

~/.lux/global-context.md          → sempre carregado (contexto global)
{workspace}/.lux.md               → contexto do projeto atual
{workspace}/AGENTS.md             → contexto para agentes (compatível Hermes)
{workspace}/..lux.md              → sobe na hierarquia até home

Exemplo de .lux.md em um projeto:
═══════════════════════════════════
# Projeto: API de Rate Limiting

## Stack
- Rust 1.82 com axum 0.7
- PostgreSQL 16 via sqlx
- Redis 7 para cache

## Convenções
- Errors: usar thiserror, sem unwrap() sem comentário
- Commits: conventional commits (feat:, fix:, chore:)
- Testes: cargo test antes de qualquer commit
- Formatação: rustfmt obrigatório

## Contexto atual
- PR #47 em revisão: adiciona rate limiting por IP
- Próximo: implementar burst allowance

## Não fazer
- Não usar tokio::spawn sem joinhandle
- Não commitar Cargo.lock em bibliotecas (apenas binários)
═══════════════════════════════════
```

---

## 20. ACP Adapter — Integração com IDEs

### 20.1 ACPServer

```python
class ACPServer:
    """
    Servidor ACP (Agent Communication Protocol) para integração com IDEs.
    Permite VS Code, Zed e JetBrains se comunicarem com o Lux.
    Inspirado no acp_adapter/ do Hermes.
    
    Expõe: conversação, tool calls, status em tempo real.
    IDE envia: arquivo aberto, seleção, diagnostics LSP, contexto do workspace.
    """

    async def handle_request(self, request: ACPRequest) -> ACPResponse:
        """
        Processa request vindo do IDE.
        Injeta contexto do IDE (arquivo aberto, seleção) no system prompt.
        """
        ide_context = self._build_ide_context(request)

        agent = AIAgent(
            user_id=request.user_id,
            session_id=request.session_id,
            channel=Channel.ACP,
        )
        # Injeta contexto do IDE como context_file virtual
        agent.state.context_files["[IDE Context]"] = ide_context

        result = await agent.run_conversation(request.message)
        return ACPResponse(
            message=result["final_response"],
            tool_calls=result["tool_calls"],
            status=result["status"],
        )

    def _build_ide_context(self, req: ACPRequest) -> str:
        parts = []
        if req.open_file:
            parts.append(f"Arquivo aberto: {req.open_file.path}")
            if req.open_file.selection:
                parts.append(f"Seleção:\n```\n{req.open_file.selection}\n```")
        if req.diagnostics:
            parts.append(f"Diagnostics LSP:\n" + "\n".join(
                f"  [{d.severity}] {d.message} (linha {d.line})"
                for d in req.diagnostics
            ))
        if req.workspace_path:
            parts.append(f"Workspace: {req.workspace_path}")
        return "\n\n".join(parts)
```

---

## 21. Interfaces e CLI

### 21.1 CLI Principal

```
Baseada em Textual (TUI completo) com Rich para formatting.
Inspirada no tui_gateway + hermes_cli do Hermes.

╔═══════════════════════════════════════════════════════════════════════╗
║  LUX  ░ Rafael  ░ 09:14  ░  VRAM 11.4/16GB  ░  skill: deploy-docker ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  [09:12] Você: /deploy-docker                                         ║
║                                                                       ║
║  [09:12] Lux: [carregando skill deploy-docker...]                     ║
║               Skill carregada. Qual imagem e ambiente você quer       ║
║               fazer deploy?                                           ║
║                                                                       ║
║  [09:13] Você: minha-api:latest para o servidor de staging            ║
║                                                                       ║
║  [09:13] Lux: ⟳ Executando: docker build -t minha-api:latest .       ║
║               ⟳ Executando: docker push registry/minha-api:latest    ║
║               ⟳ SSH staging: docker pull + restart                   ║
║               ✓ Deploy concluído. Container rodando em staging:3000   ║
║                                                                       ║
║  [09:14] Você: _                                                      ║
║                                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║  > _                                          [Ctrl+C] interromper   ║
║                                                                       ║
║  [Tab] skill autocomplete  [↑↓] histórico  [F2] voz  [F3] memória   ║
╚═══════════════════════════════════════════════════════════════════════╝

Slash commands:
  /new, /reset         → nova conversa
  /model               → trocar modelo
  /retry, /undo        → última mensagem
  /compress, /usage    → gerenciar contexto
  /skills              → listar e gerenciar skills
  /<skill-name>        → ativar skill
  /memory              → ver memória atual (MEMORY.md + USER.md)
  /search <query>      → busca FTS5 em sessões passadas
  /status              → VRAM, modelos, uptime
  /personality         → editar SOUL.md
  /profile [user]      → trocar perfil
  /resume [session_id] → retomar sessão anterior
  /export              → exportar histórico da sessão
  /stop                → interromper execução atual
  /checkpoint          → salvar checkpoint do estado
  /insights [--days N] → estatísticas de uso
  /platforms           → status de plataformas do gateway
  /gateway [start|stop]→ controlar gateway
  /cron [list|add|rm]  → gerenciar cron jobs
  /doctor              → diagnóstico do sistema
  /update              → atualizar Lux

Comandos hermes:
  lux                  → inicia CLI
  lux model            → escolher modelo
  lux tools            → configurar ferramentas por toolset
  lux gateway          → gerenciar gateway
  lux setup            → wizard de configuração
  lux doctor           → diagnóstico
  lux update           → atualizar
```

---

## 22. Segurança e Privacidade Local

### 22.1 Modelo de Ameaças

```
AMEAÇA 1 — Exfiltração de dados
  Controles:
  → llama-server em 127.0.0.1 (nunca 0.0.0.0)
  → SearXNG local para buscas web (não expõe queries)
  → Nenhuma chamada de rede externa em runtime
  → Todos os volumes Docker mapeados para localhost

AMEAÇA 2 — Prompt injection via conteúdo externo
  Controles:
  → e-mails e conteúdo web delimitados com [EXTERNAL CONTENT: START/END]
  → Qwen3-1.7B pré-filtra conteúdo antes de passar ao 14B
  → Tool results nunca interpretados como instruções do sistema

AMEAÇA 3 — Execução de código arbitrário
  Controles:
  → ShellRunTool com ALWAYS_DANGEROUS patterns bloqueados
  → Approval gate para comandos suspeitos
  → Execução em diretório configurado (não raiz)
  → Variáveis de ambiente sensíveis filtradas do sandbox

AMEAÇA 4 — Acesso não autorizado ao gateway
  Controles:
  → DM pairing: usuário deve iniciar contato primeiro
  → Whitelist de user_ids por plataforma
  → JWT para API server
  → Rate limiting por user_id

AMEAÇA 5 — Escuta não autorizada
  Controles:
  → Listening mode = OFF por padrão
  → Wake word ativa apenas gravação — sem streaming contínuo
  → Áudio deletado imediatamente após transcrição
  → Log de ativações de microfone disponível ao usuário
```

---

## 23. Estrutura de Arquivos

```
lux/
├── pyproject.toml
├── README.md
├── Makefile
├── .env.example
├── docker-compose.yml
│
├── lux/                             # pacote principal
│   ├── __init__.py
│   ├── main.py                      # entry point, DI
│   ├── config.py                    # pydantic-settings
│   ├── constants.py                 # LUX_HOME, paths
│   │
│   ├── agent/                       # core do agente
│   │   ├── agent.py                 # AIAgent — loop principal (~2000 linhas)
│   │   ├── state.py                 # AgentState e todos os dataclasses
│   │   ├── model_router.py          # ModelRouter — roteamento de tarefas
│   │   ├── budget.py                # IterationBudget
│   │   ├── trajectory.py            # TrajectorySaver — para fine-tuning
│   │   └── auxiliary_client.py      # AuxiliaryLLMClient (1.7B)
│   │
│   ├── prompt/                      # sistema de prompt
│   │   ├── assembler.py             # PromptAssembler
│   │   ├── context_files.py         # ContextFileLoader
│   │   ├── soul.py                  # SOUL.md loader
│   │   └── formatting.py           # helpers de formatação
│   │
│   ├── memory/                      # sistema de memória
│   │   ├── manager.py               # MemoryManager
│   │   ├── nudge.py                 # MemoryNudgeSystem
│   │   ├── session_db.py            # SessionDB com FTS5
│   │   └── semantic.py              # Qdrant wrapper
│   │
│   ├── skills/                      # sistema de skills
│   │   ├── manager.py               # SkillManager
│   │   ├── loader.py                # parser de SKILL.md
│   │   └── creator.py               # criação autônoma de skills
│   │
│   ├── compression/                 # compressão de contexto
│   │   ├── compressor.py            # ContextCompressor
│   │   └── lineage.py               # session lineage helpers
│   │
│   ├── tools/                       # ferramentas
│   │   ├── registry.py              # ToolRegistry
│   │   ├── toolsets.py              # definições de Toolset
│   │   ├── base.py                  # Tool ABC
│   │   ├── approval.py              # ApprovalSystem
│   │   └── implementations/
│   │       ├── terminal.py
│   │       ├── filesystem.py
│   │       ├── web.py
│   │       ├── email.py
│   │       ├── calendar.py
│   │       ├── tasks.py
│   │       ├── git.py
│   │       ├── memory_tools.py
│   │       ├── skills_tools.py
│   │       ├── system.py
│   │       └── subagent.py          # delegate_task, todo
│   │
│   ├── voice/                       # pipeline de voz
│   │   ├── pipeline.py
│   │   ├── vad.py
│   │   ├── stt.py
│   │   ├── tts.py
│   │   └── wake_word.py
│   │
│   ├── models/                      # gerenciamento de modelos
│   │   ├── manager.py               # ModelManager
│   │   ├── vram_guard.py            # VRAMGuard
│   │   ├── llama_client.py          # HTTP client llama-server
│   │   └── embedder.py
│   │
│   ├── gateway/                     # gateway multi-plataforma
│   │   ├── runner.py                # GatewayRunner
│   │   ├── session_store.py         # SessionStore para gateway
│   │   ├── delivery.py
│   │   ├── pairing.py               # DM pairing / autorização
│   │   └── platforms/
│   │       ├── telegram.py
│   │       ├── discord.py
│   │       ├── slack.py
│   │       ├── email.py
│   │       └── webhook.py
│   │
│   ├── cron/                        # scheduler
│   │   ├── scheduler.py             # CronScheduler (APScheduler)
│   │   ├── jobs.py                  # CronJob, jobs.json store
│   │   └── triggers.py              # ProactiveTriggerEngine
│   │
│   ├── plugins/                     # sistema de plugins
│   │   ├── manager.py               # PluginManager
│   │   └── base.py                  # Plugin ABC com hooks
│   │
│   ├── acp/                         # IDE integration
│   │   ├── server.py                # ACPServer (WebSocket)
│   │   └── protocol.py              # ACPRequest/Response
│   │
│   └── interfaces/                  # interfaces de usuário
│       ├── cli.py                   # CLI principal (Textual)
│       ├── gradio_ui.py             # WebUI opcional
│       └── hermes_cli/              # subcomandos `lux ...`
│           ├── main.py
│           ├── commands.py
│           ├── setup.py
│           └── auth.py
│
├── skills/                          # skills bundled (do repositório)
│   ├── plan.md
│   ├── deploy-docker.md
│   └── ...
│
├── optional-skills/                 # skills oficiais opcionais
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│       ├── test_agent_loop.py
│       ├── test_memory_persistence.py
│       ├── test_skill_progressive_disclosure.py
│       ├── test_context_compression.py
│       └── test_voice_pipeline.py
│
└── scripts/
    ├── setup-lux.sh                 # instalação completa
    ├── setup_models.sh              # download de modelos
    ├── setup_services.sh            # docker-compose up
    └── create_admin.py
```

---

## 24. Esquema de Banco de Dados

```sql
-- Sessions (com lineage tracking)
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    channel         TEXT NOT NULL,
    parent_id       TEXT REFERENCES sessions(id),    -- compressão
    lineage_root    TEXT,                            -- raiz da linhagem
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    message_count   INT DEFAULT 0,
    tokens_used     INT DEFAULT 0,
    iterations_used INT DEFAULT 0,
    compressed      BOOLEAN DEFAULT FALSE,
    compression_count INT DEFAULT 0,
    summary         TEXT
);

-- Messages
CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    thinking        TEXT,                            -- Qwen3 <think> content
    tool_calls      TEXT,                            -- JSON
    tool_call_id    TEXT,
    model_used      TEXT,
    tokens_prompt   INT,
    tokens_completion INT,
    latency_ms      INT,
    timestamp       TEXT NOT NULL,
    iteration       INT,
    task_id         TEXT
);

-- FTS5 para busca textual
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content, thinking,
    content='messages', content_rowid='rowid',
    tokenize='porter unicode61'
);
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, thinking)
    VALUES (new.rowid, new.content, new.thinking);
END;

-- User profiles
CREATE TABLE user_profiles (
    user_id          TEXT PRIMARY KEY,
    username         TEXT NOT NULL UNIQUE,
    display_name     TEXT NOT NULL,
    role             TEXT NOT NULL DEFAULT 'user',
    preferred_lang   TEXT NOT NULL DEFAULT 'pt-BR',
    response_style   TEXT NOT NULL DEFAULT 'balanced',
    formality        TEXT NOT NULL DEFAULT 'casual',
    voice_enabled    BOOLEAN NOT NULL DEFAULT 0,
    listening_mode   TEXT NOT NULL DEFAULT 'push_to_talk',
    preferred_voice  TEXT DEFAULT 'pt_BR-faber-medium',
    preferred_channel TEXT NOT NULL DEFAULT 'cli',
    enabled_toolsets TEXT NOT NULL DEFAULT '["web","tasks","calendar","memory_tools","skills","system"]',
    approval_patterns TEXT NOT NULL DEFAULT '[]',  -- JSON
    disabled_skills  TEXT NOT NULL DEFAULT '[]',   -- JSON
    work_hours_start TEXT,
    work_hours_end   TEXT,
    timezone         TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    total_sessions   INT NOT NULL DEFAULT 0,
    total_tokens     INT NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    last_seen        TEXT
);

-- Cron jobs
CREATE TABLE cron_jobs (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    name             TEXT NOT NULL,
    prompt           TEXT NOT NULL,
    schedule         TEXT NOT NULL,       -- cron expression
    skills           TEXT NOT NULL DEFAULT '[]',    -- JSON
    toolsets         TEXT NOT NULL DEFAULT '[]',    -- JSON
    delivery_channel TEXT NOT NULL,
    delivery_target  TEXT NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT 1,
    last_run         TEXT,
    next_run         TEXT NOT NULL,
    run_count        INT NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

-- Reminders
CREATE TABLE reminders (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    content          TEXT NOT NULL,
    fire_at          TEXT NOT NULL,
    channel          TEXT NOT NULL,
    fired            BOOLEAN NOT NULL DEFAULT 0,
    fired_at         TEXT,
    snoozed_count    INT NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

-- Trajectories (para fine-tuning futuro)
CREATE TABLE trajectories (
    id               TEXT PRIMARY KEY,
    task_id          TEXT NOT NULL,
    session_id       TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    steps            TEXT NOT NULL,       -- JSON array de TrajectoryStep
    final_response   TEXT,
    quality_score    REAL,
    iterations_used  INT,
    tokens_used      INT,
    created_at       TEXT NOT NULL
);

-- Índices
CREATE INDEX idx_messages_session  ON messages(session_id, timestamp DESC);
CREATE INDEX idx_messages_user     ON messages(user_id, timestamp DESC);
CREATE INDEX idx_sessions_user     ON sessions(user_id, started_at DESC);
CREATE INDEX idx_sessions_lineage  ON sessions(lineage_root);
CREATE INDEX idx_reminders_fire    ON reminders(fire_at) WHERE fired = 0;
CREATE INDEX idx_cron_next         ON cron_jobs(next_run) WHERE is_active = 1;
```

---

## 25. Cenários de Uso Completos

### Cenário 1: Skill Criada Autonomamente

**Contexto:** Após o usuário pedir para configurar nginx com SSL pela segunda vez, o Lux decide criar uma skill.

```
Lux (interno, após completar a tarefa):
  [SkillCreator] Tarefa teve 8 tool calls bem-sucedidos.
  [SkillCreator] Não existe skill similar (max similarity: 0.61).
  [SkillCreator] Gerando skill nginx-ssl com Qwen3-14B (thinking=True)...

Lux para o usuário:
  ✓ Configuração concluída. nginx rodando com SSL em *.exemplo.com

  💡 Criei uma skill baseada neste processo:
     `/nginx-ssl` — Configuração de nginx com certbot/Let's Encrypt
     Salva em ~/.lux/skills/nginx-ssl.md

  Na próxima vez que precisar deste processo, use `/nginx-ssl`.
```

### Cenário 2: Busca Cross-Session com FTS5

**Entrada:**
```
Aquele artigo sobre o ownership do Rust que discutimos, qual era o link?
```

**Fluxo:**
```
CLASSIFY (1.7B, ~0.3s):
  intent: RECALL, entities: {topic: "Rust ownership", type: "artigo"}

RETRIEVE:
  1. FTS5: session_search("Rust ownership artigo link")
     → hit em session_001 (8 dias atrás, similarity fts: 0.91):
       "https://fasterthanlime.com/articles/..."
  2. Semântica Qdrant: embedding("artigo Rust ownership") → top-3

RESPOND (14B, usando resultados):
```

**Saída:**
```
Encontrei na sessão de 8 dias atrás:

📄 "Making Hard Things Easy in Rust" — fasterthanlime.com
   Link: https://fasterthanlime.com/articles/making-hard-things-easy
   Discutimos especificamente a seção sobre lifetimes e Rc<RefCell<T>>.

Quer que eu abra, resuma ou relacione com algo atual?
```

### Cenário 3: Subagente Paralelo

**Entrada:**
```
Enquanto você verifica se tem algum e-mail urgente não lido,
me dá um resumo do status do meu projeto rate-limiter.
```

**Fluxo:**
```
ACTION_PLAN (14B, thinking=True):
  Plano: executar 2 subtarefas em paralelo via subagentes.

TOOL: delegate_task
  subagente_1: "Listar e-mails não lidos e identificar urgentes"
               toolsets: ["email"]
               max_iterations: 10

TOOL: delegate_task
  subagente_2: "Status do projeto em ~/projetos/rate-limiter"
               toolsets: ["terminal", "git"]
               max_iterations: 10

[subagentes executam em paralelo via asyncio.gather]

Subagente 1 → 3 e-mails, 1 urgente (Daniel sobre reunião amanhã)
Subagente 2 → git log + cargo check + testes → tudo verde, 2 PRs abertos
```

**Saída:**
```
Executei as duas verificações em paralelo:

📬 E-mails (3 não lidos):
  ⚠️  Daniel Souza (há 2h) — "Reunião amanhã confirmada?" → requer resposta
  • CI/CD — Build passou no PR #48
  • Newsletter — This Week in Rust #521

📦 rate-limiter (~/projetos/rate-limiter):
  Branch: feat/burst-allowance | 3 commits à frente de main
  ✓ cargo check → sem erros
  ✓ cargo test → 47/47 passando
  PRs abertos: #47 (em review), #48 (CI passando)

Respondo para o Daniel confirmando a reunião?
```

### Cenário 4: Interrupção Mid-Execution

**Entrada:** Usuário pede um deploy demorado.

```
Lux: ⟳ Fazendo build da imagem Docker (pode levar 2-3 min)...
     ⟳ [thread HTTP em background, loop monitora interrupt_event]
```

**Usuário interrompe** enviando nova mensagem: `espera, precisa ser na branch staging`

```
[interrupt_event setado]
[thread HTTP abandonada — sem partial response no histórico]

Lux: Tudo bem, cancelei. Qual é a branch staging? Já vi um 
     `feat/staging` e um `staging-v2` no git log.
```

### Cenário 5: Budget Warning com Thinking Mode

**Tarefa longa com planejamento complexo:**

```
[iteração 40/50]
Lux (interno): injetando budget warning...

Sistema→LLM: "[BUDGET] 10 iterações restantes de 50. Priorize as ações mais importantes."

[iteração 48/50]
Sistema→LLM: "[BUDGET CRÍTICO] 2 iterações restantes. Conclua IMEDIATAMENTE."

Lux para usuário:
  ✓ Setup principal concluído. Estou com o budget de iterações esgotando,
  então vou pausar aqui.
  
  O que ficou pendente:
  - [ ] Configurar monitoramento (Prometheus + Grafana)
  - [ ] Adicionar testes de carga
  
  Continue com `/resume` ou inicie uma nova conversa para essas tarefas.
```

---

## 26. Plano de Implementação

### Fase 1 — Core Foundation (Semanas 1-4)
- [ ] `agent/state.py` — todos os dataclasses, testes 100%
- [ ] `agent/agent.py` — AIAgent loop básico (sem tools, sem compressão)
- [ ] `models/llama_client.py` — HTTP client para llama-server (14B + 1.7B)
- [ ] `models/vram_guard.py` — VRAMGuard básico com ROCm/CUDA
- [ ] `memory/session_db.py` — SQLite + FTS5 com lineage
- [ ] `memory/manager.py` — MEMORY.md + USER.md + frozen snapshot
- [ ] `prompt/assembler.py` — PromptAssembler completo
- [ ] `prompt/soul.py` — SOUL.md loader
- [ ] `config.py` + `.env.example`
- [ ] `docker-compose.yml` (Qdrant, Redis mínimo)
- [ ] E2E: conversa básica com memória MEMORY.md + USER.md

### Fase 2 — Tools, Skills, Compressão (Semanas 5-8)
- [ ] `tools/registry.py` + `tools/toolsets.py` + ferramentas base
- [ ] `tools/approval.py` — ApprovalSystem com ALWAYS_DANGEROUS
- [ ] `skills/manager.py` — progressive disclosure L0/L1/L2
- [ ] `compression/compressor.py` — com tool pair rescue + lineage
- [ ] `agent/budget.py` — IterationBudget com warnings
- [ ] `agent/trajectory.py` — TrajectorySaver
- [ ] `memory/nudge.py` — MemoryNudgeSystem
- [ ] E2E: criar arquivo via tool + aprovação + skill load

### Fase 3 — Subagentes, Plugins, Scheduler (Semanas 9-11)
- [ ] `tools/implementations/subagent.py` — delegate_task + todo
- [ ] `plugins/manager.py` — descoberta + hooks pre/post tool
- [ ] `cron/scheduler.py` + `cron/jobs.py` — APScheduler
- [ ] `cron/triggers.py` — ProactiveTriggerEngine
- [ ] `memory/semantic.py` — Qdrant para recall semântico
- [ ] `skills/creator.py` — criação autônoma de skills
- [ ] E2E: subagente paralelo + skill criada autonomamente

### Fase 4 — Voz e Gateway (Semanas 12-14)
- [ ] `voice/` — VAD + Whisper + Piper + wake word + streaming
- [ ] `gateway/runner.py` + `gateway/platforms/telegram.py`
- [ ] `gateway/platforms/discord.py` + `gateway/pairing.py`
- [ ] `prompt/context_files.py` — hierarquia de .lux.md
- [ ] `agent/auxiliary_client.py` — AuxiliaryLLMClient
- [ ] E2E: conversa completa por voz + cron job via Telegram

### Fase 5 — IDE, Interfaces e Polimento (Semanas 15-18)
- [ ] `acp/server.py` — integração VS Code/Zed/JetBrains
- [ ] `interfaces/cli.py` — TUI Textual completo com todos os slash commands
- [ ] `interfaces/gradio_ui.py` — WebUI opcional
- [ ] `interfaces/hermes_cli/` — subcomandos `lux model`, `lux tools`, etc.
- [ ] Todos os adapters restantes: Slack, E-mail, WhatsApp, Webhook
- [ ] Suite de benchmarks (latência, recall de memória, skill trigger accuracy)
- [ ] Testes E2E completos dos 5 cenários documentados
- [ ] `scripts/setup-lux.sh` — instalação one-liner
- [ ] Documentação completa + README
- [ ] Release v1.0 (MIT)

---

## Apêndice A — Variáveis de Ambiente

```bash
# .env.example

# Hardware
LUX_VRAM_BUDGET_GB=14.5          # margem de segurança (real: 16GB)
LUX_GPU_BACKEND=rocm             # rocm | cuda | cpu

# Modelos
LUX_MAIN_MODEL_PATH=/models/Qwen3-14B-Instruct-Q4_K_M.gguf
LUX_AUX_MODEL_PATH=/models/Qwen3-1.7B-Instruct-Q4_K_M.gguf
LUX_WHISPER_MODEL=small          # tiny | base | small | medium
LUX_PIPER_VOICE=pt_BR-faber-medium
LUX_LLAMA_MAIN_URL=http://127.0.0.1:8080
LUX_LLAMA_AUX_URL=http://127.0.0.1:8081

# Serviços
LUX_QDRANT_URL=http://localhost:6333
LUX_REDIS_URL=redis://localhost:6379   # opcional, para gateway

# Sessão e Contexto
LUX_CTX_SIZE=8192
LUX_PARALLEL_SLOTS_MAIN=2
LUX_PARALLEL_SLOTS_AUX=4
LUX_MAX_ITERATIONS=50
LUX_COMPRESSION_THRESHOLD=0.50        # CLI (gateway usa 0.85)
LUX_PROTECT_LAST_N=20

# Memória
LUX_MEMORY_MD_LIMIT=2200
LUX_USER_MD_LIMIT=1375

# Skills
LUX_SKILLS_DIR=~/.lux/skills/
LUX_AUTO_CREATE_SKILLS=true
LUX_SKILL_CREATION_THRESHOLD=5        # tool calls mínimos para sugerir skill

# Voz
LUX_VOICE_DEFAULT=false
LUX_LISTENING_MODE=push_to_talk
LUX_WAKE_WORD=lux
LUX_STT_LANGUAGE=pt

# Proatividade
LUX_PROACTIVITY_ENABLED=true
LUX_PROACTIVITY_POLL_INTERVAL=30

# Segurança
LUX_JWT_SECRET=                        # openssl rand -hex 32
LUX_SESSION_EXPIRE_HOURS=24
LUX_ENABLE_DANGEROUS_TOOLS=false       # true apenas para admin confirmado

# Interfaces
LUX_GRADIO_ENABLED=false
LUX_GRADIO_PORT=7860
LUX_ACP_ENABLED=false
LUX_ACP_PORT=3284

# Gateway (opcional)
LUX_TELEGRAM_TOKEN=
LUX_DISCORD_TOKEN=
LUX_DISCORD_CHANNEL_IDS=
LUX_SLACK_BOT_TOKEN=
LUX_SLACK_APP_TOKEN=
LUX_EMAIL_IMAP_HOST=
LUX_EMAIL_SMTP_HOST=
LUX_EMAIL_ADDRESS=
LUX_EMAIL_PASSWORD=
LUX_SEARXNG_URL=http://localhost:8888
```

## Apêndice B — Comparação Hermes vs Lux v2.0

| Feature | Hermes Agent | Lux v2.0 | Diferença |
|---|---|---|---|
| **Modelo** | Qualquer (OpenRouter, etc.) | Qwen3-14B local (ROCm) | Local-first, zero cloud |
| **Memória** | MEMORY.md + USER.md + FTS5 | Mesmo + Qdrant semântico | Lux adiciona busca semântica |
| **Skills** | Progressive disclosure L0/L1/L2 | Idêntico + criação autônoma | Lux cria skills após tarefas |
| **Sessão** | SQLite + FTS5 + lineage | Idêntico | Portado diretamente |
| **Compressão** | Lossy + protect_last_N | Idêntico + tool pair rescue | Lux garante pairs intactos |
| **Gateway** | 20+ plataformas | 5 plataformas (fase 1) | Hermes mais amplo |
| **Voz** | ElevenLabs (cloud) | Whisper + Piper (local) | Lux: 100% local |
| **VRAM** | Sem gestão (roda em cloud) | VRAMGuard + circuit breaker | Lux: hardware fixo |
| **IDE** | ACP (VS Code, Zed, JetBrains) | Idêntico | Portado diretamente |
| **Plugins** | Hooks pre/post tool | Idêntico | Portado diretamente |
| **Cron** | Scheduler em linguagem natural | Idêntico + triggers condicionais | Lux adiciona triggers |
| **Subagentes** | delegate_task + budget isolado | Idêntico | Portado diretamente |
| **Aprovação** | approval.py com patterns | Idêntico + ALWAYS_DANGEROUS list | Lux tem blocked list explícita |
| **Privacidade** | Dados vão para provedores | Zero exfiltração | Diferença fundamental |
