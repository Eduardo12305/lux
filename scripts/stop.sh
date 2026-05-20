#!/bin/bash
# scripts/stop.sh — Encerramento completo do Lux
# Para: Lux → llama-server aux → llama-server main → Docker (Qdrant + Redis)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$HOME/.lux/pids"

# ── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Lux — Encerrando todos os serviços...  ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}\n"

# ── Função auxiliar: matar processo por PID file ─────────────────────────────
kill_pid_file() {
    local label="$1"
    local pid_file="$2"

    if [ ! -f "$pid_file" ]; then
        warn "$label: PID file não encontrado (talvez já esteja parado)"
        return 0
    fi

    local pid
    pid=$(cat "$pid_file")

    if ! kill -0 "$pid" 2>/dev/null; then
        warn "$label: processo $pid não está rodando"
        rm -f "$pid_file"
        return 0
    fi

    info "Encerrando $label (PID $pid)..."
    kill -TERM "$pid" 2>/dev/null

    # Aguarda até 10s para encerrar graciosamente
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        warn "  Forçando encerramento (SIGKILL)..."
        kill -KILL "$pid" 2>/dev/null
        sleep 1
    fi

    rm -f "$pid_file"
    ok "$label encerrado"
}

# ── Matar por nome de processo (fallback) ────────────────────────────────────
kill_by_name() {
    local pattern="$1"
    local label="$2"
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        info "Encerrando $label (pkill)..."
        pkill -TERM -f "$pattern" 2>/dev/null || true
        sleep 2
        pkill -KILL -f "$pattern" 2>/dev/null || true
        ok "$label encerrado"
    fi
}

# ── 1. llama-server aux ──────────────────────────────────────────────────────
kill_pid_file "llama-server aux" "$PID_DIR/llama_aux.pid"

# ── 2. llama-server main ─────────────────────────────────────────────────────
kill_pid_file "llama-server main" "$PID_DIR/llama_main.pid"

# Fallback: matar quaisquer llama-server restantes
kill_by_name "llama-server.*8080" "llama-server main (fallback)"
kill_by_name "llama-server.*8081" "llama-server aux (fallback)"

# ── 3. Docker (Qdrant + Redis) ───────────────────────────────────────────────
if command -v docker &>/dev/null; then
    info "Parando containers Docker (Qdrant + Redis)..."
    cd "$PROJECT_DIR"
    docker compose stop qdrant redis 2>/dev/null && ok "Docker containers parados" || warn "Erro ao parar Docker containers"
else
    warn "docker não encontrado — pulando etapa Docker"
fi

# ── Resumo ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Lux encerrado com sucesso.             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}\n"
