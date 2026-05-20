#!/bin/bash
# scripts/start.sh — Inicialização completa do Lux
# Inicia: Docker (Qdrant + Redis) → llama-server main → llama-server aux → Lux
set -e

# ── Diretórios e configuração ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$HOME/.lux/pids"
LOG_DIR="$HOME/.lux/logs"
ENV_FILE="$PROJECT_DIR/.env"

mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Cores para output ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Lux — Iniciando todos os serviços...   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}\n"

# ── Carregar .env ────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    fail ".env não encontrado em $PROJECT_DIR. Copie de .env.example e configure."
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Valores com fallback
MAIN_MODEL="${LUX_MAIN_MODEL_PATH:-$HOME/models/Qwen3-14B-Instruct-Q4_K_M.gguf}"
AUX_MODEL="${LUX_AUX_MODEL_PATH:-$HOME/models/Qwen3-4B-Instruct-Q4_K_M.gguf}"
MAIN_PORT=8080
AUX_PORT=8081
CTX_SIZE="${LUX_CTX_SIZE:-8192}"
SLOTS_MAIN="${LUX_PARALLEL_SLOTS_MAIN:-2}"
SLOTS_AUX="${LUX_PARALLEL_SLOTS_AUX:-4}"
LLAMA_BIN="${LUX_LLAMA_SERVER_BIN:-llama-server}"
VENV="$PROJECT_DIR/.venv"

# ── Pré-verificações ─────────────────────────────────────────────────────────
info "Verificando pré-requisitos..."

command -v docker &>/dev/null || fail "docker não encontrado. Instale o Docker."
command -v "$LLAMA_BIN" &>/dev/null || fail "'$LLAMA_BIN' não encontrado. Compile o llama.cpp com ROCm e adicione ao PATH."

[ -f "$MAIN_MODEL" ] || fail "Modelo principal não encontrado: $MAIN_MODEL"
[ -f "$AUX_MODEL"  ] || fail "Modelo auxiliar não encontrado: $AUX_MODEL"
[ -d "$VENV"       ] || fail "Virtualenv não encontrado em $VENV. Execute: python -m venv .venv && pip install -e '.[voice]'"

ok "Pré-requisitos OK"

# ── Verificar se já está rodando ─────────────────────────────────────────────
if [ -f "$PID_DIR/llama_main.pid" ] && kill -0 "$(cat "$PID_DIR/llama_main.pid")" 2>/dev/null; then
    warn "Lux já parece estar rodando. Execute ./scripts/stop.sh primeiro."
    exit 0
fi

# ── 1. Docker (Qdrant + Redis) ───────────────────────────────────────────────
info "Iniciando serviços Docker (Qdrant + Redis)..."
cd "$PROJECT_DIR"
docker compose up -d qdrant redis 2>&1 | grep -E "(Started|Running|✔|Error)" || true

# Aguardar Qdrant ficar saudável
info "Aguardando Qdrant ficar disponível..."
QDRANT_TIMEOUT=30
QDRANT_COUNT=0
until curl -sf http://localhost:6333/healthz &>/dev/null; do
    sleep 1
    QDRANT_COUNT=$((QDRANT_COUNT + 1))
    if [ $QDRANT_COUNT -ge $QDRANT_TIMEOUT ]; then
        fail "Qdrant não respondeu após ${QDRANT_TIMEOUT}s. Verifique: docker compose logs qdrant"
    fi
done
ok "Qdrant online (localhost:6333)"

# Aguardar Redis
REDIS_COUNT=0
until docker exec lux-redis-1 redis-cli ping &>/dev/null 2>&1; do
    sleep 1
    REDIS_COUNT=$((REDIS_COUNT + 1))
    if [ $REDIS_COUNT -ge 15 ]; then
        warn "Redis não confirmou ping, continuando mesmo assim..."
        break
    fi
done
ok "Redis online (localhost:6379)"

# ── 2. llama-server principal (Qwen3-14B) ───────────────────────────────────
info "Iniciando llama-server principal [$(basename "$MAIN_MODEL")] na porta $MAIN_PORT..."
"$LLAMA_BIN" \
    --model "$MAIN_MODEL" \
    --ctx-size "$CTX_SIZE" \
    --parallel "$SLOTS_MAIN" \
    --flash-attn on \
    -ngl 99 \
    --port "$MAIN_PORT" \
    --host 127.0.0.1 \
    --log-disable \
    > "$LOG_DIR/llama_main.log" 2>&1 &

LLAMA_MAIN_PID=$!
echo "$LLAMA_MAIN_PID" > "$PID_DIR/llama_main.pid"
info "  PID: $LLAMA_MAIN_PID | Log: $LOG_DIR/llama_main.log"

# Aguardar llama-server main ficar pronto
info "  Aguardando llama-server main carregar o modelo..."
MAIN_TIMEOUT=120
MAIN_COUNT=0
until curl -sf "http://127.0.0.1:$MAIN_PORT/health" &>/dev/null; do
    if ! kill -0 "$LLAMA_MAIN_PID" 2>/dev/null; then
        fail "llama-server main encerrou inesperadamente. Veja: $LOG_DIR/llama_main.log"
    fi
    sleep 2
    MAIN_COUNT=$((MAIN_COUNT + 2))
    if [ $MAIN_COUNT -ge $MAIN_TIMEOUT ]; then
        fail "llama-server main não respondeu após ${MAIN_TIMEOUT}s. Veja: $LOG_DIR/llama_main.log"
    fi
    echo -n "."
done
echo ""
ok "llama-server main pronto (127.0.0.1:$MAIN_PORT)"

# ── 3. llama-server auxiliar (Qwen3-4B) ─────────────────────────────────────
info "Iniciando llama-server auxiliar [$(basename "$AUX_MODEL")] na porta $AUX_PORT..."
"$LLAMA_BIN" \
    --model "$AUX_MODEL" \
    --ctx-size 4096 \
    --parallel "$SLOTS_AUX" \
    --flash-attn on \
    -ngl 99 \
    --port "$AUX_PORT" \
    --host 127.0.0.1 \
    --log-disable \
    > "$LOG_DIR/llama_aux.log" 2>&1 &

LLAMA_AUX_PID=$!
echo "$LLAMA_AUX_PID" > "$PID_DIR/llama_aux.pid"
info "  PID: $LLAMA_AUX_PID | Log: $LOG_DIR/llama_aux.log"

# Aguardar llama-server aux ficar pronto
info "  Aguardando llama-server aux carregar o modelo..."
AUX_TIMEOUT=90
AUX_COUNT=0
until curl -sf "http://127.0.0.1:$AUX_PORT/health" &>/dev/null; do
    if ! kill -0 "$LLAMA_AUX_PID" 2>/dev/null; then
        fail "llama-server aux encerrou inesperadamente. Veja: $LOG_DIR/llama_aux.log"
    fi
    sleep 2
    AUX_COUNT=$((AUX_COUNT + 2))
    if [ $AUX_COUNT -ge $AUX_TIMEOUT ]; then
        fail "llama-server aux não respondeu após ${AUX_TIMEOUT}s. Veja: $LOG_DIR/llama_aux.log"
    fi
    echo -n "."
done
echo ""
ok "llama-server aux pronto (127.0.0.1:$AUX_PORT)"

# ── 4. Lux ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Todos os serviços prontos — Lux ON!    ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# Ativa venv e roda o Lux em foreground (CTRL+C para sair)
cd "$PROJECT_DIR"
# shellcheck disable=SC1090
source "$VENV/bin/activate"
exec python -m lux.main
