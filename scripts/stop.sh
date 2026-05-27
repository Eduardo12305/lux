#!/bin/bash
# scripts/stop.sh — Encerramento completo do Lux
# Para: Lux → Omni (MiniCPM-o) → llama-server aux → llama-server main → Docker

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$HOME/.lux/pids"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${CYAN}[→]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Lux — Encerrando todos os serviços...  ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}\n"

kill_pid_file() {
    local label="$1"; local pid_file="$2"
    if [ ! -f "$pid_file" ]; then warn "$label: PID file não encontrado (talvez já esteja parado)"; return 0; fi
    local pid=$(cat "$pid_file")
    if ! kill -0 "$pid" 2>/dev/null; then warn "$label: processo $pid não está rodando"; rm -f "$pid_file"; return 0; fi
    info "Encerrando $label (PID $pid)..."
    kill -TERM "$pid" 2>/dev/null
    for i in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    if kill -0 "$pid" 2>/dev/null; then warn "  Forçando encerramento (SIGKILL)..."; kill -KILL "$pid" 2>/dev/null; sleep 1; fi
    rm -f "$pid_file"
    ok "$label encerrado"
}

kill_by_name() {
    local pattern="$1"; local label="$2"
    local pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        info "Encerrando $label (pkill)..."
        pkill -TERM -f "$pattern" 2>/dev/null || true; sleep 2
        pkill -KILL -f "$pattern" 2>/dev/null || true
        ok "$label encerrado"
    fi
}

# ── 1. Omni (MiniCPM-o) ──────────────────────────────────────────────────
kill_pid_file "Omni Engine (MiniCPM-o)" "$PID_DIR/omni.pid"
kill_by_name "llama-omni-cli" "Omni Engine (fallback)"

# ── 2. llama-server aux ──────────────────────────────────────────────────
kill_pid_file "llama-server aux" "$PID_DIR/llama_aux.pid"
kill_by_name "llama-server.*8081" "llama-server aux (fallback)"

# ── 3. llama-server main ─────────────────────────────────────────────────
kill_pid_file "llama-server main" "$PID_DIR/llama_main.pid"
kill_by_name "llama-server.*8080" "llama-server main (fallback)"

# ── 4. Docker (Qdrant + Redis) ───────────────────────────────────────────
if command -v docker &>/dev/null; then
    info "Parando containers Docker (Qdrant + Redis)..."
    cd "$PROJECT_DIR"
    docker compose stop qdrant redis 2>/dev/null && ok "Docker containers parados" || warn "Erro ao parar Docker containers"
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Lux encerrado com sucesso.             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
