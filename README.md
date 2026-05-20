# Lux — Assistente Pessoal Local

**100% local · MIT · 16GB VRAM · ROCm/CUDA**

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/lux-project/lux && cd lux

# 2. Setup
chmod +x scripts/setup-lux.sh && ./scripts/setup-lux.sh

# 3. Baixar modelos
./scripts/setup_models.sh

# 4. Iniciar llama-server (terminal 1)
llama-server --model /models/Qwen3-14B-Instruct-Q4_K_M.gguf \
  --ctx-size 8192 --parallel 2 --flash-attn --port 8080 --host 127.0.0.1

llama-server --model /models/Qwen3-1.7B-Instruct-Q4_K_M.gguf \
  --ctx-size 4096 --parallel 4 --port 8081 --host 127.0.0.1

# 5. Iniciar Lux (terminal 2)
make run
```

## Requisitos

- **GPU**: AMD ROCm ou NVIDIA CUDA, 16GB+ VRAM
- **Python**: 3.11+
- **Serviços**: Qdrant (via Docker), Redis (via Docker, opcional)
- **Modelos**: Qwen3-14B Q4_K_M (~9.5GB), Qwen3-1.7B Q4_K_M (~1.2GB)

## Comandos CLI

| Comando | Descrição |
|---------|-----------|
| `/help` | Lista comandos |
| `/quit` | Sair |
| `/status` | Status do sistema |
| `/doctor` | Diagnóstico |
| `/memory` | Ver memória |
| `/skills` | Listar skills |
| `/<skill>` | Ativar skill |

## Estrutura

```
lux/            # Código fonte
  agent/        # Agent loop, estado, orquestração
  models/       # llama_client, VRAM guard, embeddings
  memory/       # MEMORY.md, FTS5, Qdrant
  skills/       # Progressive disclosure L0/L1/L2
  tools/        # Ferramentas, aprovação, registry
  prompt/       # System prompt assembly
  compression/  # Contexto lossy + lineage
  voice/        # STT/TTS pipeline
  gateway/      # Multi-plataforma (Telegram, Discord)
  cron/         # Scheduler + triggers proativos
  plugins/      # Sistema de plugins/hooks
  acp/          # IDE integration (VS Code, Zed)

~/.lux/         # Dados do usuário
  MEMORY.md     # Notas do agente (2200 chars)
  USER.md       # Perfil do usuário (1375 chars)
  SOUL.md       # Personalidade editável
  skills/       # Skills criadas autonomamente
  sessions.db   # SQLite + FTS5
```

## Filosofia

1. **O agente cresce com você** — Skills criadas autonomamente, memória curada pelo agente
2. **Progressive disclosure** — Contexto carregado sob demanda (L0/L1/L2)
3. **Agent loop auditável** — Toda iteração serializável, trajetórias salvas
4. **Ferramenta > prompt** — Ações executadas via tools, nunca texto livre
5. **Local-first** — Zero dependência de cloud
6. **Privacidade soberana** — Nenhum dado sai da máquina

## Licença

MIT — veja [LICENSE](LICENSE)
