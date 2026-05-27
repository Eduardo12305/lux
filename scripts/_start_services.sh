#!/bin/bash
# scripts/_start_services.sh — Sobe apenas os serviços em background
# (Qdrant + Redis + llama-server main + llama-server aux)
# Chamado pelo wrapper `lux` quando os serviços ainda não estão rodando.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$HOME/.lux/pids"
LOG_DIR="$HOME/.lux/logs"
ENV_FILE="$PROJECT_DIR/.env"

mkdir -p "$PID_DIR" "$LOG_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
fail() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

set -a; source "$ENV_FILE"; set +a

MAIN_MODEL="${LUX_MAIN_MODEL_PATH}"
AUX_MODEL="${LUX_AUX_MODEL_PATH}"
CTX_SIZE="${LUX_CTX_SIZE:-8192}"
SLOTS_MAIN="${LUX_PARALLEL_SLOTS_MAIN:-2}"
SLOTS_AUX="${LUX_PARALLEL_SLOTS_AUX:-4}"
LLAMA_BIN="${LUX_LLAMA_SERVER_BIN:-llama-server}"

[ -f "$MAIN_MODEL" ] || fail "Modelo principal não encontrado: $MAIN_MODEL"
[ -f "$AUX_MODEL"  ] || fail "Modelo auxiliar não encontrado: $AUX_MODEL"

# Docker
info "Iniciando Docker (Qdrant + Redis)..."
cd "$PROJECT_DIR"
docker compose up -d qdrant redis 2>&1 | grep -E "(Started|Running|✔)" || true
until curl -sf http://localhost:6333/healthz &>/dev/null; do sleep 1; done
ok "Qdrant online"

# llama-server main
info "Iniciando llama-server main [$(basename "$MAIN_MODEL")]..."
"$LLAMA_BIN" \
    --model "$MAIN_MODEL" --ctx-size "$CTX_SIZE" \
    --parallel "$SLOTS_MAIN" --flash-attn on -ngl 99 \
    --port 8080 --host 127.0.0.1 --log-disable \
    > "$LOG_DIR/llama_main.log" 2>&1 &
echo $! > "$PID_DIR/llama_main.pid"
until curl -sf http://127.0.0.1:8080/health &>/dev/null; do
    kill -0 "$(cat "$PID_DIR/llama_main.pid")" 2>/dev/null || fail "llama-server main falhou. Log: $LOG_DIR/llama_main.log"
    sleep 2; echo -n "."
done; echo ""
ok "llama-server main pronto"

# llama-server aux
info "Iniciando llama-server aux [$(basename "$AUX_MODEL")]..."
"$LLAMA_BIN" \
    --model "$AUX_MODEL" --ctx-size 4096 \
    --parallel "$SLOTS_AUX" --flash-attn on -ngl 99 \
    --port 8081 --host 127.0.0.1 --log-disable \
    > "$LOG_DIR/llama_aux.log" 2>&1 &
echo $! > "$PID_DIR/llama_aux.pid"
until curl -sf http://127.0.0.1:8081/health &>/dev/null; do
    kill -0 "$(cat "$PID_DIR/llama_aux.pid")" 2>/dev/null || fail "llama-server aux falhou. Log: $LOG_DIR/llama_aux.log"
    sleep 2; echo -n "."
done; echo ""
ok "llama-server aux pronto"
