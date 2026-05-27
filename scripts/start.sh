#!/bin/bash
# scripts/start.sh — Inicialização completa do Lux
# Inicia: Docker (Qdrant + Redis) → llama-server main → llama-server aux → Omni (MiniCPM-o) → Lux
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$HOME/.lux/pids"
LOG_DIR="$HOME/.lux/logs"
ENV_FILE="$PROJECT_DIR/.env"

mkdir -p "$PID_DIR" "$LOG_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Lux — Iniciando todos os serviços...   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}\n"

# ── Carregar .env ──────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then fail ".env não encontrado em $PROJECT_DIR. Copie de .env.example e configure."; fi
set -a; source "$ENV_FILE"; set +a

MAIN_MODEL="${LUX_MAIN_MODEL_PATH:-$HOME/models/Qwen3-14B-Instruct-Q4_K_M.gguf}"
AUX_MODEL="${LUX_AUX_MODEL_PATH:-$HOME/models/Qwen3-4B-Instruct-Q4_K_M.gguf}"
MAIN_PORT=8080; AUX_PORT=8081
CTX_SIZE="${LUX_CTX_SIZE:-8192}"; SLOTS_MAIN="${LUX_PARALLEL_SLOTS_MAIN:-2}"; SLOTS_AUX="${LUX_PARALLEL_SLOTS_AUX:-4}"
LLAMA_BIN="${LUX_LLAMA_SERVER_BIN:-llama-server}"
OMNI_BIN="${LUX_OMNI_BINARY_PATH:-$HOME/services/claudio_llm/llama.cpp-omni/build/bin/llama-omni-cli}"
OMNI_MODEL="${LUX_OMNI_MODEL_PATH:-$HOME/.lux/models/minicpm-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf}"
VENV="$PROJECT_DIR/.venv"
ENABLE_OMNI="${LUX_ENABLE_OMNI:-false}"

# ── Pré-verificações ────────────────────────────────────────────────────────
info "Verificando pré-requisitos..."
command -v docker &>/dev/null || warn "docker não encontrado. Qdrant/Redis não serão iniciados."
[ -d "$VENV" ] || fail "Virtualenv não encontrado em $VENV."

if [ -f "$MAIN_MODEL" ]; then ok "Modelo principal encontrado"; else warn "Modelo principal não encontrado: $MAIN_MODEL"; fi
if [ -f "$AUX_MODEL" ];  then ok "Modelo auxiliar encontrado";  else warn "Modelo auxiliar não encontrado: $AUX_MODEL"; fi

if [ "$ENABLE_OMNI" = "true" ]; then
    [ -f "$OMNI_MODEL" ] || fail "Modelo Omni (MiniCPM-o) não encontrado: $OMNI_MODEL"
    [ -f "$OMNI_BIN" ]   || fail "Binário llama-omni-cli não encontrado: $OMNI_BIN"
    ok "Omni (MiniCPM-o) detectado"
fi

ok "Pré-requisitos OK"

# ── Verificar se já está rodando ───────────────────────────────────────────
if [ -f "$PID_DIR/llama_main.pid" ] && kill -0 "$(cat "$PID_DIR/llama_main.pid")" 2>/dev/null; then
    warn "Lux já parece estar rodando. Execute ./scripts/stop.sh primeiro."; exit 0
fi

# ── 1. Docker (Qdrant + Redis) ─────────────────────────────────────────────
if command -v docker &>/dev/null; then
    info "Iniciando serviços Docker (Qdrant + Redis)..."
    cd "$PROJECT_DIR"
    docker compose up -d qdrant redis 2>&1 | grep -E "(Started|Running|✔|Error)" || true

    info "Aguardando Qdrant ficar disponível..."
    for i in $(seq 1 30); do
        curl -sf http://localhost:6333/healthz &>/dev/null && break
        sleep 1
        [ $i -ge 30 ] && warn "Qdrant não respondeu após 30s"
    done
    curl -sf http://localhost:6333/healthz &>/dev/null && ok "Qdrant online (localhost:6333)" || warn "Qdrant offline"
    ok "Redis online (localhost:6379)"
fi

# ── 2. llama-server principal (Qwen3-14B) ─────────────────────────────────
if [ -f "$MAIN_MODEL" ] && command -v "$LLAMA_BIN" &>/dev/null; then
    info "Iniciando llama-server principal [$(basename "$MAIN_MODEL")] na porta $MAIN_PORT..."
    "$LLAMA_BIN" --model "$MAIN_MODEL" --ctx-size "$CTX_SIZE" --parallel "$SLOTS_MAIN" \
        --flash-attn on -ngl "${LUX_MAIN_GPU_LAYERS:-99}" --port "$MAIN_PORT" --host 127.0.0.1 --log-disable \
        > "$LOG_DIR/llama_main.log" 2>&1 &
    echo $! > "$PID_DIR/llama_main.pid"
    info "  PID: $(cat $PID_DIR/llama_main.pid) | Log: $LOG_DIR/llama_main.log"
    info "  Aguardando llama-server main carregar o modelo..."
    for i in $(seq 1 60); do
        curl -sf "http://127.0.0.1:$MAIN_PORT/health" &>/dev/null && break
        sleep 2
        if [ $i -ge 60 ]; then warn "llama-server main não respondeu após 120s"; fi
    done
    curl -sf "http://127.0.0.1:$MAIN_PORT/health" &>/dev/null && ok "llama-server main pronto (127.0.0.1:$MAIN_PORT)" || warn "llama-server main offline"
else
    warn "Pulando llama-server principal (modelo/binário ausente)"
fi

# ── 3. llama-server auxiliar (Qwen3-4B) ──────────────────────────────────
if [ -f "$AUX_MODEL" ] && command -v "$LLAMA_BIN" &>/dev/null; then
    info "Iniciando llama-server auxiliar [$(basename "$AUX_MODEL")] na porta $AUX_PORT..."
    "$LLAMA_BIN" --model "$AUX_MODEL" --ctx-size 4096 --parallel "$SLOTS_AUX" \
        --flash-attn on -ngl "${LUX_AUX_GPU_LAYERS:-99}" --port "$AUX_PORT" --host 127.0.0.1 --log-disable \
        > "$LOG_DIR/llama_aux.log" 2>&1 &
    echo $! > "$PID_DIR/llama_aux.pid"
    info "  PID: $(cat $PID_DIR/llama_aux.pid) | Log: $LOG_DIR/llama_aux.log"
    info "  Aguardando llama-server aux carregar o modelo..."
    for i in $(seq 1 45); do
        curl -sf "http://127.0.0.1:$AUX_PORT/health" &>/dev/null && break
        sleep 2
        if [ $i -ge 45 ]; then warn "llama-server aux não respondeu após 90s"; fi
    done
    curl -sf "http://127.0.0.1:$AUX_PORT/health" &>/dev/null && ok "llama-server aux pronto (127.0.0.1:$AUX_PORT)" || warn "llama-server aux offline"
else
    warn "Pulando llama-server auxiliar (modelo/binário ausente)"
fi

# ── 4. Omni (MiniCPM-o 4.5) ──────────────────────────────────────────────
if [ "$ENABLE_OMNI" = "true" ]; then
    info "Omni Engine (MiniCPM-o 4.5) habilitado (será iniciado dinamicamente pelo processo do Lux)"
fi

# ── 5. Lux ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Todos os serviços prontos — Lux ON!    ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

cd "$PROJECT_DIR"
source "$VENV/bin/activate"
exec python -m lux.main
