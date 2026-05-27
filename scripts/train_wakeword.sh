#!/bin/bash
# scripts/train_wakeword.sh — Pipeline de treinamento de wake word
# Baseado em openWakeWord + TTS Coqui XTTS v2 + ROCm
# Uso: ./scripts/train_wakeword.sh [palavra] [threshold]
#   Se nenhuma palavra informada, usa "arkana"
set -euo pipefail
WORD="${1:-arkana}"
THRESHOLD="${2:-0.85}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$HOME/.lux/wakeword_data"
OUTPUT_DIR="$HOME/.lux/models/wakeword"
VENV_DIR="$PROJECT_DIR/.venv"
OPENWAKEWORD_DIR="$DATA_DIR/openWakeWord"
# ── Validação de ambiente ───────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Lux — Treinamento de Wake Word                    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Palavra:    $WORD"
echo "  Threshold:  $THRESHOLD"
echo "  Data dir:   $DATA_DIR"
echo "  Output:     $OUTPUT_DIR"
echo ""
mkdir -p "$DATA_DIR" "$OUTPUT_DIR"
# ── Verificar dependências de sistema ───────────────────────────────────────
MISSING=""
for cmd in ffmpeg uv python3 git wget; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING="$MISSING $cmd"
    fi
done
if [ -n "$MISSING" ]; then
    echo "Dependencias de sistema ausentes:$MISSING"
    echo ""
    echo "Execute: sudo apt-get install -y ffmpeg libasound2-dev libsndfile1-dev sox git wget python3-dev"
    exit 1
fi
# ── Ativar virtualenv ───────────────────────────────────────────────────────
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    echo "Virtualenv ativado: $VENV_DIR"
else
    echo "Virtualenv nao encontrado em $VENV_DIR"
    echo "Execute 'uv sync' primeiro no diretorio do projeto."
    exit 1
fi
PYTHON_BIN="${VENV_DIR}/bin/python"
# ── Detectar ROCm no sistema ────────────────────────────────────────────────
HAS_ROCM=0
GFX_VERSION=""
if [ -e /dev/kfd ] && [ -e /dev/dri/renderD128 ]; then
    if groups | grep -q render; then
        HAS_ROCM=1
        echo "ROCm detectado no sistema."
    fi
fi
if [ "$HAS_ROCM" = "1" ]; then
    if command -v rocminfo &>/dev/null; then
        ROCM_VERSION=$(rocminfo 2>/dev/null | grep -i "ROCm" | head -1 | grep -oP '[\d.]+' | head -1 || echo "")
        echo "  ROCm version: ${ROCM_VERSION:-desconhecida}"
        GFX_NAME=$(rocminfo 2>/dev/null | grep -i "gfx" | head -1 | grep -oP 'gfx[\d\w]+' || echo "")
        echo "  GPU arch: ${GFX_NAME:-desconhecida}"
        # ── FIX: gfx1200 (RDNA 4) não tem suporte nativo no PyTorch ROCm ──
        # O XTTS v2 falha com HIP error em gfx1200 — forçar CPU para TTS
        if [[ "${GFX_NAME:-}" == "gfx1200" ]] || [[ "${GFX_NAME:-}" == "gfx1201" ]]; then
            echo "  ⚠️  GPU arch ${GFX_NAME} (RDNA 4) nao tem suporte XTTS v2 via ROCm."
            echo "  TTS sera executado em CPU. Treinamento usara GPU normalmente."
            TTS_USE_GPU=0
        else
            TTS_USE_GPU=1
        fi
    fi
else
    TTS_USE_GPU=0
fi
# ── Configurar/Instalar PyTorch ROCm ────────────────────────────────────────
echo ""
echo "[0/6] Configurando PyTorch ROCm..."
if [ "$HAS_ROCM" = "1" ]; then
    if "$PYTHON_BIN" -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
        echo "  PyTorch ROCm ja instalado e funcional."
    else
        PY_VER=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")
        if [ "$PY_VER" -ge 313 ]; then
            echo "  ⚠️  Python $("$PYTHON_BIN" --version) nao tem wheels ROCm. Usando CPU."
            HAS_ROCM=0
            TTS_USE_GPU=0
            uv pip install --reinstall-package torch torchaudio torch \
                --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -3
        else
            echo "  Instalando PyTorch com suporte ROCm..."
            ROCM_INDEX="https://download.pytorch.org/whl/rocm6.2"
            if command -v rocminfo &>/dev/null; then
                ROCM_VER=$(rocminfo 2>/dev/null | grep -oP 'ROCm:\s*\K[\d.]+' | head -1 || echo "")
                if [[ "$ROCM_VER" =~ ^6\.[0-3] ]]; then
                    ROCM_INDEX="https://download.pytorch.org/whl/rocm$ROCM_VER"
                fi
            fi
            echo "  Index: $ROCM_INDEX"
            uv pip install --reinstall-package torch --reinstall-package torchaudio \
                torch torchaudio --index-url "$ROCM_INDEX" 2>&1 | tail -3
            if ! "$PYTHON_BIN" -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
                if [ -z "${HSA_OVERRIDE_GFX_VERSION:-}" ]; then
                    export HSA_OVERRIDE_GFX_VERSION=12.0.1
                    echo "  Definido HSA_OVERRIDE_GFX_VERSION=12.0.1"
                fi
                if ! "$PYTHON_BIN" -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
                    echo "  ⚠️  GPU nao detectada. Usando CPU."
                    HAS_ROCM=0
                    TTS_USE_GPU=0
                    uv pip install --reinstall-package torch torchaudio torch \
                        --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -1
                fi
            fi
        fi
    fi
else
    TTS_USE_GPU=0
    echo "  ROCm nao detectado. Instalando PyTorch CPU..."
    uv pip install --reinstall-package torch torchaudio torch \
        --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -1
    echo "  PyTorch CPU instalado."
fi
if [ "$HAS_ROCM" = "1" ]; then
    "$PYTHON_BIN" -c "import torch; print(f'  GPU: {torch.cuda.get_device_name(0)}'); print(f'  VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB')" 2>/dev/null || true
fi
echo "  TTS_USE_GPU=${TTS_USE_GPU:-0}"
# ── Instalar dependências Python ─────────────────────────────────────────────
echo ""
echo "[1/6] Instalando dependencias Python..."
echo "  Instalando build tools..."
uv pip install setuptools wheel meson-python ninja hatchling Cython 2>&1 | tail -1
echo "  Instalando pacotes base..."
uv pip install numpy soundfile sounddevice librosa scipy pandas scikit-learn matplotlib PyYAML 2>&1 | tail -1
# ── FIX: transformers + tokenizers — versões fixas compatíveis com XTTS v2 ──
echo "  Instalando transformers/tokenizers (versoes fixas para XTTS v2)..."
uv pip install "transformers==4.46.3" "tokenizers==0.20.3" 2>&1 | tail -1
TRANS_CHECK=$("$PYTHON_BIN" -c "
from transformers.pytorch_utils import isin_mps_friendly
print('OK')
" 2>/dev/null || echo "FAIL")
if [ "$TRANS_CHECK" = "FAIL" ]; then
    echo "  ⚠️  transformers incompativel — patch sera aplicado apos instalacao do TTS."
fi
echo "  Instalando onnx + onnxruntime..."
uv pip install onnx onnxruntime 2>&1 | tail -1
echo "  Instalando audiomentations..."
uv pip install audiomentations 2>&1 | tail -1
echo "  Instalando Coqui TTS (pode demorar alguns minutos)..."
uv pip uninstall coqpit coqpit-config coqui-tts-trainer TTS 2>/dev/null || true
# ── FIX: remover namespace package fantasma do sistema ──────────────────────
TRAINER_FILE=$("$PYTHON_BIN" -c "import trainer; print(trainer.__file__)" 2>/dev/null || echo "NOTFOUND")
if [ "$TRAINER_FILE" = "None" ]; then
    echo "  ⚠️  Namespace package fantasma detectado — removendo..."
    sudo rm -rf /usr/lib/python3.12/trainer 2>/dev/null || true
    sudo rm -f /usr/lib/python3.12/trainer*.egg-info 2>/dev/null || true
fi
echo "  Instalando coqpit-config..."
uv pip install coqpit-config 2>&1 | tail -1
# ── FIX: trainer — nome real do pacote é coqui-tts-trainer no PyPI ──────────
echo "  Instalando trainer (coqui-tts-trainer)..."
uv pip install coqui-tts-trainer 2>&1 | tail -1
TRAINER_PATH=$("$PYTHON_BIN" -c "import trainer; print(trainer.__file__)" 2>/dev/null || echo "")
if [ -z "$TRAINER_PATH" ] || [ "$TRAINER_PATH" = "None" ]; then
    echo "  ⚠️  PyPI falhou — tentando via git..."
    uv pip install "coqui-tts-trainer @ git+https://github.com/coqui-ai/Trainer.git" 2>&1 | tail -3
    TRAINER_PATH=$("$PYTHON_BIN" -c "import trainer; print(trainer.__file__)" 2>/dev/null || echo "")
    if [ -z "$TRAINER_PATH" ] || [ "$TRAINER_PATH" = "None" ]; then
        echo "  ❌ Nao foi possivel instalar o trainer. Abortando."
        exit 1
    fi
fi
echo "  trainer OK: $TRAINER_PATH"
echo "  Instalando TTS..."
uv pip install --no-build-isolation git+https://github.com/idiap/coqui-ai-TTS.git 2>&1 | tail -5
TTS_OK=$?
# ── FIX: patch autoregressive.py — isin_mps_friendly removida no transformers 5.x
AUTOREGRESSIVE=$(find "$VENV_DIR" -path "*/TTS/tts/layers/tortoise/autoregressive.py" 2>/dev/null | head -1)
if [ -n "$AUTOREGRESSIVE" ]; then
    if grep -q "isin_mps_friendly" "$AUTOREGRESSIVE"; then
        echo "  ⚠️  Aplicando patch isin_mps_friendly em autoregressive.py..."
        sed -i 's/from transformers.pytorch_utils import isin_mps_friendly as isin/from torch import isin/' "$AUTOREGRESSIVE"
        echo "  Patch aplicado."
    fi
fi
if [ "$TTS_OK" != "0" ]; then
    echo "  ⚠️  Coqui TTS nao foi instalado. Verifique o log acima."
    exit 1
fi
echo "  TTS instalado com sucesso."
echo "  Instalando openwakeword..."
uv pip install openwakeword torchinfo torchmetrics 2>&1 | tail -1
# ── Clonar openWakeWord ─────────────────────────────────────────────────────
echo ""
echo "[2/6] Configurando openWakeWord..."
if [ ! -d "$OPENWAKEWORD_DIR" ]; then
    git clone https://github.com/dscripka/openWakeWord.git "$OPENWAKEWORD_DIR" 2>&1 | tail -3
    echo "  Repositório clonado."
else
    echo "  Repositório já existe — reutilizando."
    (cd "$OPENWAKEWORD_DIR" && git pull 2>/dev/null || true)
fi
# ── Pré-baixar modelo TTS ────────────────────────────────────────────────────
echo ""
echo "[3/6] Pré-carregando modelo TTS XTTS v2 (~2 GB)..."
"$PYTHON_BIN" -c "
from TTS.api import TTS
import torch
# FIX: gfx1200 (RDNA 4) — forcar CPU para XTTS v2
use_gpu = ${TTS_USE_GPU:-0} == 1
print(f'  Carregando XTTS v2 (GPU={use_gpu})...')
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=use_gpu)
print('  Modelo TTS carregado. Speakers disponiveis:', len(tts.speakers))
" 2>&1
# ── Gerar amostras positivas via TTS ─────────────────────────────────────────
echo ""
echo "[4/6] Gerando amostras positivas via TTS..."
"$PYTHON_BIN" - "$WORD" "$DATA_DIR" "${TTS_USE_GPU:-0}" << 'PYEOF'
import os
import sys
import random
import numpy as np
import soundfile as sf

word      = sys.argv[1]
data_dir  = sys.argv[2]
# FIX: recebe flag TTS_USE_GPU do shell — gfx1200 sempre CPU
use_gpu   = sys.argv[3] == "1"

output_dir = os.path.join(data_dir, "positives")
os.makedirs(output_dir, exist_ok=True)

from TTS.api import TTS

print(f"  Carregando XTTS v2 (GPU={use_gpu})...")
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=use_gpu)
print(f"  Modelo carregado. Speakers: {len(tts.speakers)}")

variations = [
    word.capitalize(),
    f"{word.capitalize()}.",
    f"Ei, {word.capitalize()}",
    f"Ok, {word.capitalize()}",
    f"{word.capitalize()}, ouça",
    f"{word.capitalize()}, por favor",
    f"Olá, {word.capitalize()}",
]
speakers = tts.speakers[:15]
language = "pt"
n_amostras_por_speaker = 20
total = 0

for variacao in variations:
    for speaker in speakers:
        for i in range(n_amostras_por_speaker):
            speed = random.uniform(0.85, 1.20)
            safe_name = variacao.replace(" ", "_").replace(",", "").replace(".", "")
            filename = os.path.join(output_dir, f"{safe_name}_{speaker}_{i:04d}.wav")
            if os.path.exists(filename):
                total += 1
                continue
            try:
                wav = tts.tts(text=variacao, speaker=speaker, language=language, speed=speed)
                wav_np = np.array(wav, dtype=np.float32)
                sf.write(filename, wav_np, 22050)
                total += 1
            except Exception as e:
                print(f"  ⚠️ Erro em {speaker}/{variacao}: {str(e)[:100]}")
        if total % 100 == 0 and total > 0:
            print(f"  Geradas {total} amostras...")

print(f"  Total: {total} amostras positivas em {output_dir}")
PYEOF
# ── Augmentação ──────────────────────────────────────────────────────────────
echo ""
echo "[5/6] Augmentando dataset..."
"$PYTHON_BIN" - "$DATA_DIR" << 'PYEOF'
import os
import sys
import numpy as np
import soundfile as sf
from audiomentations import Compose, AddGaussianNoise, TimeStretch, PitchShift, Gain

data_dir   = sys.argv[1]
input_dir  = os.path.join(data_dir, "positives")
output_dir = os.path.join(data_dir, "positives_augmented")
os.makedirs(output_dir, exist_ok=True)

for fname in os.listdir(input_dir):
    if not fname.endswith(".wav"):
        continue
    audio, sr = sf.read(os.path.join(input_dir, fname))
    sf.write(os.path.join(output_dir, fname), audio, sr)

augment = Compose([
    AddGaussianNoise(min_amplitude=0.001, max_amplitude=0.015, p=0.5),
    TimeStretch(min_rate=0.9, max_rate=1.1, p=0.4),
    PitchShift(min_semitones=-2, max_semitones=2, p=0.4),
    Gain(min_gain_db=-6, max_gain_db=6, p=0.5),
])

n_aug = 3
total_aug = 0
for fname in sorted(os.listdir(input_dir)):
    if not fname.endswith(".wav"):
        continue
    audio, sr = sf.read(os.path.join(input_dir, fname))
    for i in range(n_aug):
        try:
            aug_audio = augment(samples=audio.astype(np.float32), sample_rate=sr)
            out_fname = fname.replace(".wav", f"_aug{i}.wav")
            sf.write(os.path.join(output_dir, out_fname), aug_audio, sr)
            total_aug += 1
        except Exception:
            continue

print(f"  Augmentacao concluida: {total_aug} variantes | Total: {len(os.listdir(output_dir))} arquivos")
PYEOF
# ── Treinamento ──────────────────────────────────────────────────────────────
echo ""
echo "[6/6] Treinando modelo '$WORD'..."



# ── FIX: gerar clips negativos sintéticos localmente ────────────────────────
# (Sempre recriamos para garantir ruídos dinâmicos com variabilidade de volume)
NEGATIVE_DIR="$DATA_DIR/negatives"
rm -rf "$NEGATIVE_DIR"
mkdir -p "$NEGATIVE_DIR"
echo "  Gerando clips negativos sintéticos com variabilidade de volume..."
"$PYTHON_BIN" - "$NEGATIVE_DIR" << 'NEGEOF'
import os
import sys
import random
import numpy as np
import soundfile as sf

negative_dir = sys.argv[1]
sr           = 16000
duration     = 1.28   # mesmo clip_duration_ms=1280 do config
n_samples    = int(sr * duration)
n_per_type   = 600    # 600 × 5 tipos = 3000 negativos
total        = 0

# Ruídos que representam "não é a wake word" com volumes variando de silêncio absoluto até som ativo
def white_noise():
    amp = random.uniform(0.0001, 0.08)
    return np.random.normal(0, amp, n_samples).astype(np.float32)

def pink_noise():
    amp = random.uniform(0.0001, 0.05)
    return (np.cumsum(np.random.normal(0, amp, n_samples)) * 0.01).astype(np.float32)

def silence():
    # Ruído térmico de baixíssima amplitude (evita que silêncio seja classificado como positivo)
    amp = random.uniform(1e-6, 1e-4)
    return np.random.normal(0, amp, n_samples).astype(np.float32)

def low_rumble():
    amp = random.uniform(0.001, 0.05)
    freq = random.uniform(30, 150)
    t = np.linspace(0, duration, n_samples)
    return (np.sin(2 * np.pi * freq * t) * amp).astype(np.float32)

def ambient_hiss():
    amp = random.uniform(0.0001, 0.03)
    return np.random.uniform(-amp, amp, n_samples).astype(np.float32)

generators = {
    "white_noise":  white_noise,
    "pink_noise":   pink_noise,
    "silence":      silence,
    "low_rumble":   low_rumble,
    "ambient_hiss": ambient_hiss,
}

for name, gen in generators.items():
    for i in range(n_per_type):
        fname = os.path.join(negative_dir, f"{name}_{i:04d}.wav")
        sf.write(fname, gen(), sr)
        total += 1

print(f"  {total} clips negativos sintéticos prontos em {negative_dir}")
NEGEOF

# ── Treinamento ──────────────────────────────────────────────────────────────
echo ""
echo "[6/6] Treinando modelo '$WORD'..."
echo ""

# (pronouncing não é mais necessário — pipeline reimplementado sem o repo)

set +e
"$PYTHON_BIN" -u - "$WORD" "$THRESHOLD" "$DATA_DIR" "$OUTPUT_DIR" "$OPENWAKEWORD_DIR" "$NEGATIVE_DIR" "${TTS_USE_GPU:-0}" << 'PYEOF'
import os, sys, traceback, copy
import numpy as np
import torch
from torch import nn, optim
from pathlib import Path
import soundfile as sf

sys.stderr = sys.stdout

def log(msg):
    print(f"  {msg}")
    sys.stdout.flush()

try:
    word             = sys.argv[1]
    threshold        = float(sys.argv[2])
    data_dir         = sys.argv[3]
    output_dir       = sys.argv[4]
    openwakeword_dir = sys.argv[5]
    negative_dir     = sys.argv[6]
    # FIX: gfx1200 (RDNA 4) nao tem kernels ROCm compilados para Linear/LayerNorm
    # Mesmo motivo pelo qual TTS_USE_GPU=0. Forcar CPU para o treino DNN.
    use_gpu_training = sys.argv[7] == "1" if len(sys.argv) > 7 else False
    if use_gpu_training and torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    log(f"Dispositivo: {device} — {torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU (gfx1200 sem suporte ROCm para DNN)'}")

    positives_aug_dir = os.path.join(data_dir, "positives_augmented")
    n_positives = len([f for f in os.listdir(positives_aug_dir) if f.endswith(".wav")])
    n_negatives = len([f for f in os.listdir(negative_dir) if f.endswith(".wav")])
    log(f"Positivos (augmentados): {n_positives} | Negativos: {n_negatives}")

    if n_negatives == 0:
        log("❌ Nenhum clip negativo encontrado. Abortando.")
        sys.exit(1)

    feature_save_dir = os.path.join(output_dir, word)
    import shutil
    if os.path.exists(feature_save_dir):
        shutil.rmtree(feature_save_dir)
    os.makedirs(feature_save_dir, exist_ok=True)
    onnx_path = os.path.join(output_dir, f"{word}.onnx")

    # ── Carregar áudio e paddar para int16 @16kHz ────────────────────────────
    TARGET_SR = 16000
    CLIP_LEN  = 32000  # 2 s

    def load_clips(paths):
        clips = []
        for p in paths:
            try:
                audio, sr = sf.read(p, dtype="float32", always_2d=False)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                if sr != TARGET_SR:
                    n = int(len(audio) * TARGET_SR / sr)
                    audio = np.interp(np.linspace(0, len(audio)-1, n),
                                      np.arange(len(audio)), audio).astype(np.float32)
                if len(audio) < CLIP_LEN:
                    audio = np.pad(audio, (0, CLIP_LEN - len(audio)))
                else:
                    audio = audio[:CLIP_LEN]
                clips.append((audio * 32767).astype(np.int16))
            except Exception as e:
                log(f"Aviso ao carregar {Path(p).name}: {e}")
        return np.array(clips)

    # ── Features via AudioFeatures.embed_clips() (pip, sem deps pesadas) ─────
    from openwakeword.utils import AudioFeatures
    AF = AudioFeatures(ncpu=1)

    def make_features(clips_paths, out_path, label, batch_size=64):
        if os.path.exists(out_path):
            log(f"Features '{label}' ja existem — reutilizando.")
            return np.load(out_path)
        log(f"Calculando features '{label}' ({len(clips_paths)} clips)...")
        sys.stdout.flush()
        all_feats = []
        for i in range(0, len(clips_paths), batch_size):
            batch = load_clips(clips_paths[i:i+batch_size])
            if len(batch) == 0:
                continue
            feats = AF.embed_clips(batch, batch_size=batch_size)
            all_feats.append(feats)
            if (i // batch_size) % 5 == 0:
                log(f"  {min(i+batch_size, len(clips_paths))}/{len(clips_paths)}")
        result = np.concatenate(all_feats, axis=0)
        np.save(out_path, result)
        log(f"Features '{label}' salvas: shape={result.shape}")
        return result

    positive_clips = sorted([str(Path(positives_aug_dir)/f)
                             for f in os.listdir(positives_aug_dir) if f.endswith(".wav")])
    negative_clips = sorted([str(Path(negative_dir)/f)
                             for f in os.listdir(negative_dir) if f.endswith(".wav")])

    sp = int(len(positive_clips) * 0.8)
    sn = int(len(negative_clips) * 0.8)

    pos_tr = make_features(positive_clips[:sp], os.path.join(feature_save_dir, "pos_train.npy"), "positivas-treino")
    neg_tr = make_features(negative_clips[:sn], os.path.join(feature_save_dir, "neg_train.npy"), "negativas-treino")
    pos_te = make_features(positive_clips[sp:], os.path.join(feature_save_dir, "pos_test.npy"),  "positivas-teste")
    neg_te = make_features(negative_clips[sn:], os.path.join(feature_save_dir, "neg_test.npy"),  "negativas-teste")

    ishape = pos_tr.shape[1:]  # (frames, embed_dim) ex: (16, 96)
    log(f"Input shape: {ishape}")

    # ── DNN (mesmo estilo openWakeWord com Dropout para evitar overfitting) ─────────────────
    class WakeWordDNN(nn.Module):
        def __init__(self, ishape, layer_dim=64, n_blocks=1):
            super().__init__()
            flat = ishape[0] * ishape[1]
            self.net = nn.Sequential(
                nn.Flatten(),
                nn.Linear(flat, layer_dim),
                nn.LayerNorm(layer_dim),
                nn.ReLU(),
                nn.Dropout(0.4),
                *[nn.Sequential(
                    nn.Linear(layer_dim, layer_dim),
                    nn.LayerNorm(layer_dim),
                    nn.ReLU(),
                    nn.Dropout(0.4)
                  ) for _ in range(n_blocks)],
                nn.Linear(layer_dim, 1),
                nn.Sigmoid(),
            )
        def forward(self, x):
            return self.net(x)

    model = WakeWordDNN(ishape).to(device)
    # L2 regularization (weight_decay=1e-4) para conter overfitting
    optimizer = optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.BCELoss()

    def make_loader(pos, neg, batch_size, shuffle):
        X = torch.from_numpy(np.concatenate([pos, neg]).astype(np.float32))
        y = torch.from_numpy(np.concatenate([np.ones(len(pos)), np.zeros(len(neg))]).astype(np.float32))
        return torch.utils.data.DataLoader(
            torch.utils.data.TensorDataset(X, y), batch_size=batch_size, shuffle=shuffle)

    train_loader = make_loader(pos_tr, neg_tr, 64,  True)
    val_loader   = make_loader(pos_te, neg_te, 256, False)
    n_train = len(pos_tr) + len(neg_tr)
    n_val   = len(pos_te) + len(neg_te)

    EPOCHS, PATIENCE = 30, 5
    best_loss, best_state, patience_cnt = float("inf"), None, 0
    log(f"Treino: {EPOCHS} epocas | batch=64 | device={device}")
    log("")

    for epoch in range(1, EPOCHS+1):
        model.train()
        tl = 0.0
        for Xb, yb in train_loader:
            Xb, yb = Xb.to(device), yb.to(device)
            optimizer.zero_grad()
            loss = criterion(model(Xb).squeeze(1), yb)
            loss.backward()
            optimizer.step()
            tl += loss.item() * len(Xb)

        model.eval()
        vl, ok = 0.0, 0
        with torch.no_grad():
            for Xb, yb in val_loader:
                Xb, yb = Xb.to(device), yb.to(device)
                p = model(Xb).squeeze(1)
                vl += criterion(p, yb).item() * len(Xb)
                ok += ((p >= 0.5) == yb.bool()).sum().item()
        vl /= n_val
        log(f"Epoca {epoch:02d}/{EPOCHS} | train={tl/n_train:.4f} | val={vl:.4f} | acc={ok/n_val*100:.1f}%")

        if vl < best_loss:
            best_loss, best_state, patience_cnt = vl, copy.deepcopy(model.state_dict()), 0
        else:
            patience_cnt += 1
            if patience_cnt >= PATIENCE:
                log(f"Early stopping na epoca {epoch}.")
                break

    model.load_state_dict(best_state)
    log(f"Melhor val_loss: {best_loss:.4f}")

    # ── Exportar ONNX ─────────────────────────────────────────────────────────
    log("Exportando ONNX...")
    model.eval().cpu()
    dummy = torch.randn(1, *ishape)
    torch.onnx.export(
        model, dummy, onnx_path,
        input_names=["features"], output_names=[word],
        dynamic_axes={"features": {0: "batch"}},
        opset_version=13,
    )
    size_kb = os.path.getsize(onnx_path) / 1024
    log(f"✅ Modelo exportado: {onnx_path} ({size_kb:.0f} KB)")
    log(f"   Threshold recomendado: {threshold}")
    log(f"   Input shape: (batch, {ishape[0]}, {ishape[1]})")

except Exception as e:
    log("")
    log(f"❌ ERRO: {type(e).__name__}: {e}")
    log("")
    for line in traceback.format_exc().split("\n"):
        if line.strip():
            log(f"   {line}")
    sys.exit(1)
PYEOF
TRAIN_EXIT=$?
set -e

if [ "$TRAIN_EXIT" != "0" ]; then
    echo ""
    echo "  ❌ Treinamento falhou (exit code: $TRAIN_EXIT)"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Treinamento concluído!                            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
if [ -f "$OUTPUT_DIR/${WORD}.onnx" ]; then
    SIZE=$(du -h "$OUTPUT_DIR/${WORD}.onnx" | cut -f1)
    echo "  ✅ Modelo: $OUTPUT_DIR/${WORD}.onnx ($SIZE)"
    echo ""
    echo "  Configuração no .env:"
    echo "    LUX_WAKE_WORD=${WORD}"
    echo "    LUX_WAKEWORD_THRESHOLD=${THRESHOLD}"
    echo "    LUX_WAKEWORD_COOLDOWN_S=2.0"
else
    echo "  ❌ Modelo .onnx não encontrado em $OUTPUT_DIR/"
    echo "     Verifique o log acima para erros."
fi