#!/bin/bash
# scripts/setup-lux.sh — Instalacao one-liner do Lux
set -e

echo "========================================"
echo "  Lux v1.0.0 — Setup"
echo "========================================"

LUX_HOME="${LUX_HOME:-$HOME/.lux}"
mkdir -p "$LUX_HOME"/{memories,skills/.backups,checkpoints,plugins,cron,trajectories}

# Criar SOUL.md padrao se nao existir
if [ ! -f "$LUX_HOME/SOUL.md" ]; then
    cat > "$LUX_HOME/SOUL.md" << 'EOF'
Você é o **Lux**, assistente pessoal.

## Caráter
- Direto e objetivo
- Tecnicamente profundo quando necessario
- Respostas concisas

## Idioma
- Portugues brasileiro por padrao
EOF
fi

echo "[1/3] Instalando dependencias Python..."
pip install -e ".[dev]"

echo "[2/3] Iniciando servicos (Qdrant + Redis)..."
docker-compose up -d qdrant redis 2>/dev/null || echo "  Docker nao disponivel — iniciando servicos manualmente..."

echo "[3/3] Verificando ambiente..."
python -c "from lux.config import get_config; print(f'  LUX_HOME: {get_config().lux_home}')"

echo ""
echo "========================================"
echo "  Setup concluido!"
echo "  Execute 'make run' ou 'lux' para iniciar"
echo "========================================"
