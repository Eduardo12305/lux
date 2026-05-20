#!/bin/bash
# scripts/setup_models.sh — Download de modelos
set -e

MODELS_DIR="${MODELS_DIR:-/models}"
mkdir -p "$MODELS_DIR"

echo "========================================"
echo "  Lux — Download de Modelos"
echo "========================================"
echo "Destino: $MODELS_DIR"
echo ""

# Qwen3-14B-Instruct Q4_K_M (~9.5GB)
QWEN_14B_URL="https://huggingface.co/bartowski/Qwen3-14B-Instruct-GGUF/resolve/main/Qwen3-14B-Instruct-Q4_K_M.gguf"
QWEN_14B_FILE="$MODELS_DIR/Qwen3-14B-Instruct-Q4_K_M.gguf"

if [ -f "$QWEN_14B_FILE" ]; then
    echo "[✓] Qwen3-14B ja existe: $QWEN_14B_FILE"
else
    echo "[↓] Baixando Qwen3-14B-Instruct Q4_K_M (~9GB)..."
    wget -O "$QWEN_14B_FILE" "$QWEN_14B_URL" || {
        echo "Falha ao baixar Qwen3-14B. Tente manualmente."
    }
fi

# Qwen3-1.7B-Instruct Q4_K_M (~1.2GB)
QWEN_1_7B_URL="https://huggingface.co/bartowski/Qwen3-1.7B-Instruct-GGUF/resolve/main/Qwen3-1.7B-Instruct-Q4_K_M.gguf"
QWEN_1_7B_FILE="$MODELS_DIR/Qwen3-1.7B-Instruct-Q4_K_M.gguf"

if [ -f "$QWEN_1_7B_FILE" ]; then
    echo "[✓] Qwen3-1.7B ja existe: $QWEN_1_7B_FILE"
else
    echo "[↓] Baixando Qwen3-1.7B-Instruct Q4_K_M (~1.2GB)..."
    wget -O "$QWEN_1_7B_FILE" "$QWEN_1_7B_URL" || {
        echo "Falha ao baixar Qwen3-1.7B. Tente manualmente."
    }
fi

echo ""
echo "========================================"
echo "  Download de modelos concluido!"
echo "========================================"
