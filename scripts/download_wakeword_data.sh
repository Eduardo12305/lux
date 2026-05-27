#!/bin/bash
# scripts/download_wakeword_data.sh — Geração de datasets de ruído para treino
# Gera ruídos sintéticos (CoordGen) e hard negatives textuais.
# Não requer TTS — apenas numpy + soundfile.
# Após executar, execute ./scripts/train_wakeword.sh para treinar.
set -euo pipefail

DATA_DIR="${HOME}/.lux/wakeword_data"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

echo "╔══════════════════════════════════════════════════════╗"
echo "║   Lux — Geração de Datasets Wake Word               ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Destino: $DATA_DIR"
echo ""

mkdir -p "$DATA_DIR"

# ── Ativar virtualenv ───────────────────────────────────────────────────────
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "Virtualenv nao encontrado em $VENV_DIR"
    echo "Execute 'uv sync' primeiro."
    exit 1
fi

# ── Instalar apenas numpy + soundfile (leves) ───────────────────────────────
echo "[1/3] Instalando numpy + soundfile..."
uv pip install numpy soundfile 2>&1 | tail -1

# ── CoordGen: ruídos sintéticos ─────────────────────────────────────────────
echo ""
echo "[2/3] Gerando ruídos sintéticos (CoordGen)..."
COORDGEN_DIR="$DATA_DIR/coordgen_noise"

if [ ! -d "$COORDGEN_DIR/musan/noise" ]; then
    mkdir -p "$COORDGEN_DIR/musan/noise"
    mkdir -p "$COORDGEN_DIR/musan/music"
    mkdir -p "$COORDGEN_DIR/musan/speech"

    python3 - "$COORDGEN_DIR" << 'PYEOF'
import os, sys
import numpy as np
import soundfile as sf

base = sys.argv[1]
noise_dir = os.path.join(base, "musan", "noise")
music_dir = os.path.join(base, "musan", "music")
speech_dir = os.path.join(base, "musan", "speech")

SR = 16000
DURATION = 10
np.random.seed(42)

for i in range(100):
    s = SR * DURATION
    t = np.random.choice(["white", "pink", "brown", "blue"])
    if t == "white":
        a = np.random.randn(s).astype(np.float32) * 0.12
    elif t == "pink":
        w = np.random.randn(s)
        a = (np.cumsum(w) / np.arange(1, s+1)**0.5).astype(np.float32) * 0.04
    elif t == "brown":
        a = np.cumsum(np.random.randn(s)).astype(np.float32) * 0.015
    else:
        a = np.diff(np.random.randn(s+1)).astype(np.float32) * 0.25
    sf.write(os.path.join(noise_dir, f"noise_{i:04d}.wav"), a, SR)

for i in range(30):
    s = SR * DURATION
    tvec = np.linspace(0, DURATION, s)
    freqs = np.random.uniform(80, 2500, 3)
    a = sum(np.sin(2*np.pi*f*tvec).astype(np.float32)*0.025 for f in freqs)
    sf.write(os.path.join(music_dir, f"music_{i:04d}.wav"), a, SR)

for i in range(30):
    s = SR * DURATION
    a = np.random.randn(s).astype(np.float32) * 0.015
    k = np.ones(120) / 120
    a = np.convolve(a, k, mode='same').astype(np.float32)
    sf.write(os.path.join(speech_dir, f"babble_{i:04d}.wav"), a, SR)

print(f"  CoordGen: {len(os.listdir(noise_dir))} noise + {len(os.listdir(music_dir))} music + {len(os.listdir(speech_dir))} speech")
PYEOF
    echo "  CoordGen gerado."
else
    echo "  CoordGen já existe — reutilizando."
fi

# ── Hard negatives textuais ─────────────────────────────────────────────────
echo ""
echo "[3/3] Criando lista de hard negatives..."

HARD_NEG_DIR="$DATA_DIR/hard_negatives"
mkdir -p "$HARD_NEG_DIR"

cat > "$HARD_NEG_DIR/words.txt" << 'EOF'
# Palavras foneticamente similares a "arkana" e outras wake words
# Estas serão usadas para gerar amostras negativas via TTS durante o treino
# Formato: uma palavra por linha

# Similares a "arkana"
arcano
arcana
arcada
arcado
aryana
arkada
arcanae

# Similares a "oraculo"  
oracular
oraculista
oculo
oraculao

# Similares genéricos (falsos positivos comuns)
acorda
acolá
aranha
arcanjo
EOF

echo "  Hard negatives: $HARD_NEG_DIR/words.txt"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Datasets prontos!                                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Estrutura:"
echo "    $DATA_DIR"
echo "    ├── coordgen_noise/          (ruídos sintéticos)"
echo "    └── hard_negatives/words.txt (palavras similares)"
echo ""
echo "  Próximo passo: ./scripts/train_wakeword.sh arkana"
echo ""
