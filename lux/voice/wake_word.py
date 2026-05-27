# lux/voice/wake_word.py
# Módulo: Voice
# Dependências: onnxruntime, openwakeword.utils (AudioFeatures), numpy
# Status: IMPLEMENTADO
# Notas: Detector de wake word com modelo ONNX treinado via openWakeWord.
#   Pipeline de features: AudioFeatures.embed_clips() (Google Speech Embedding, 16×96)
#   — mesmo pipeline usado no treinamento, 100% offline.
#   Suporta até 2 palavras simultâneas: "arkana" (sempre) + customizada via .env.

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.environ.get(
    "LUX_WAKEWORD_MODEL_DIR",
    str(Path("~/.lux/models/wakeword").expanduser()),
)).expanduser()

DEFAULT_WAKE_WORD = "arkana"
RESERVED_WAKE_WORD = "arkana"
MAX_WAKE_WORDS = 2
DEFAULT_THRESHOLD = 0.5
COOLDOWN_SECONDS = 2.0
SAMPLE_RATE = 16000

# ── Tamanho da janela de áudio ────────────────────────────────────────────────
# Deve ser igual ao CLIP_LEN usado no treinamento (32000 = 2 s a 16 kHz).
# AudioFeatures.embed_clips() sobre 32000 amostras → shape (1, 16, 96).
WINDOW_SAMPLES = 32000  # 2 segundos — compatível com o treino


def _resolve_model_path(word: str) -> Path:
    return MODEL_DIR / f"{word}.onnx"


def _detect_configured_word() -> str:
    return os.environ.get("LUX_WAKE_WORD", DEFAULT_WAKE_WORD).strip().lower()


def _list_available_models() -> list[str]:
    if not MODEL_DIR.exists():
        return []
    return sorted(
        [p.stem for p in MODEL_DIR.glob("*.onnx")],
        key=lambda n: n != RESERVED_WAKE_WORD,
    )


class WakeWordDetector:
    """Detector de wake word com modelo ONNX.

    Pipeline de features idêntico ao treinamento:
      áudio int16 @16 kHz → AudioFeatures.embed_clips() → (16, 96) embeddings
      → ONNX DNN → score [0, 1]

    100% offline: usa apenas openwakeword instalado localmente.
    """

    _instance: Optional[WakeWordDetector] = None

    def __init__(
        self,
        threshold: Optional[float] = None,
        model_dir: Optional[Path] = None,
    ):
        self._model_dir = Path(model_dir or MODEL_DIR).expanduser()
        self._sessions: dict[str, object] = {}
        self._thresholds: dict[str, float] = {}
        self._available = False
        self._configured_word = _detect_configured_word()

        base_threshold = threshold if threshold is not None else float(
            os.environ.get("LUX_WAKEWORD_THRESHOLD", str(DEFAULT_THRESHOLD))
        )
        self._cooldown = float(
            os.environ.get("LUX_WAKEWORD_COOLDOWN_S", str(COOLDOWN_SECONDS))
        )
        self._last_detection = 0.0
        self._detected_word: Optional[str] = None
        self._base_threshold = base_threshold

        from lux.config import get_config
        config = get_config()
        self._min_rms = float(
            os.environ.get("LUX_WAKEWORD_MIN_RMS", str(getattr(config, "wakeword_min_rms", 0.002)))
        )

        # Buffer de áudio rolante — acumula WINDOW_SAMPLES amostras float32
        self._audio_buffer = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
        self._buffer_filled = False
        self._samples_since_fill = 0

        # AudioFeatures (openwakeword pip) — inicializado lazy em load()
        self._af = None

    @classmethod
    def get_instance(cls) -> WakeWordDetector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def load(self) -> bool:
        if self._available:
            return True

        # ── Verificar onnxruntime ─────────────────────────────────────────────
        try:
            import onnxruntime as ort  # noqa: F401
        except ImportError:
            logger.warning("onnxruntime nao instalado — wake word desabilitada")
            return False

        # ── Inicializar AudioFeatures (pipeline offline) ──────────────────────
        try:
            from openwakeword.utils import AudioFeatures
            self._af = AudioFeatures(ncpu=1)
            logger.info("AudioFeatures (openwakeword) inicializado com sucesso")
        except Exception as e:
            logger.warning("Falha ao inicializar AudioFeatures: %s — wake word desabilitada", e)
            return False

        self._model_dir.mkdir(parents=True, exist_ok=True)

        available = _list_available_models()
        words_to_load: list[str] = []

        if RESERVED_WAKE_WORD in available:
            words_to_load.append(RESERVED_WAKE_WORD)
        elif self._configured_word == RESERVED_WAKE_WORD:
            logger.warning(
                "Modelo '%s.onnx' nao encontrado em %s. "
                "Execute: ./scripts/train_wakeword.sh",
                RESERVED_WAKE_WORD, self._model_dir,
            )

        if self._configured_word != RESERVED_WAKE_WORD:
            if self._configured_word in available:
                if len(words_to_load) < MAX_WAKE_WORDS:
                    words_to_load.append(self._configured_word)
            else:
                logger.warning(
                    "Modelo '%s.onnx' nao encontrado em %s. "
                    "Execute: ./scripts/train_wakeword.sh %s",
                    self._configured_word, self._model_dir, self._configured_word,
                )

        if not words_to_load:
            if available:
                words_to_load = available[:MAX_WAKE_WORDS]
                logger.info("Usando modelos disponiveis: %s", words_to_load)
            else:
                logger.warning(
                    "Nenhum modelo .onnx em %s. Execute: ./scripts/train_wakeword.sh",
                    self._model_dir,
                )
                return False

        import onnxruntime as ort

        loaded = 0
        for word in words_to_load:
            path = _resolve_model_path(word)
            if not path.exists():
                continue
            try:
                session = ort.InferenceSession(
                    str(path),
                    providers=["CPUExecutionProvider"],
                )
                self._sessions[word] = session

                if word == RESERVED_WAKE_WORD:
                    self._thresholds[word] = min(self._base_threshold, 0.95)
                else:
                    self._thresholds[word] = self._base_threshold

                # Verificar input shape do modelo
                inp = session.get_inputs()[0]
                logger.info(
                    "Wake word carregada: %s | input='%s' shape=%s threshold=%.2f",
                    word, inp.name, inp.shape, self._thresholds[word],
                )
                loaded += 1
            except Exception as e:
                logger.warning("Falha ao carregar %s: %s", path, e)

        if loaded == 0:
            return False

        self._available = True
        logger.info("WakeWordDetector: %d modelo(s) carregado(s)", loaded)
        return True

    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """Processa um chunk de áudio float32 @16 kHz.

        Alimenta o buffer rolante. Quando o buffer tiver WINDOW_SAMPLES,
        extrai features com AudioFeatures e roda o modelo ONNX.
        """
        if not self._available or self._af is None:
            return False

        now = time.monotonic()
        if now - self._last_detection < self._cooldown:
            return False

        # ── Atualizar buffer rolante ──────────────────────────────────────────
        chunk_len = len(audio_chunk)
        if chunk_len >= WINDOW_SAMPLES:
            self._audio_buffer = audio_chunk[-WINDOW_SAMPLES:].astype(np.float32)
            self._buffer_filled = True
        else:
            self._audio_buffer = np.roll(self._audio_buffer, -chunk_len)
            self._audio_buffer[-chunk_len:] = audio_chunk.astype(np.float32)
            self._samples_since_fill += chunk_len
            if self._samples_since_fill >= WINDOW_SAMPLES:
                self._buffer_filled = True

        if not self._buffer_filled:
            return False

        # ── Filtro de Energia (RMS) ───────────────────────────────────────────
        # Evita falsos positivos em silêncio absoluto ou ruído de fundo muito baixo
        rms = np.sqrt(np.mean(self._audio_buffer ** 2))
        if rms < self._min_rms:
            return False

        # ── Extrair features: float32 → int16 → embed_clips → (1, 16, 96) ────
        try:
            # AudioFeatures.embed_clips espera int16, shape (N, samples)
            audio_int16 = (self._audio_buffer * 32767).astype(np.int16)
            audio_batch = audio_int16[np.newaxis, :]  # (1, 32000)
            features = self._af.embed_clips(audio_batch, batch_size=1)
            # features: (1, 16, 96)
            feat_input = features.astype(np.float32)  # (1, 16, 96)
        except Exception as e:
            logger.debug("Erro ao extrair features: %s", e)
            return False

        # ── Inferência ONNX ───────────────────────────────────────────────────
        for word, session in self._sessions.items():
            threshold = self._thresholds.get(word, self._base_threshold)
            try:
                input_name = session.get_inputs()[0].name
                result = session.run(None, {input_name: feat_input})
                # result[0]: (1, 1) ou (1,)
                r = result[0]
                score = float(r.flat[0])

                if score >= threshold:
                    self._last_detection = now
                    self._detected_word = word
                    logger.info(
                        "Wake word '%s' detectada: score=%.3f (threshold=%.3f)",
                        word, score, threshold,
                    )
                    return True

            except Exception as e:
                logger.debug("Erro na inferencia ONNX (%s): %s", word, e)
                continue

        return False

    def detect(self, audio_bytes: bytes) -> bool:
        """Processa bytes de áudio int16 @16 kHz (formato direto do microfone)."""
        if not self._available:
            return False
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return self.process_chunk(audio_np)

    def set_threshold(self, value: float, word: Optional[str] = None):
        if not 0.0 < value < 1.0:
            raise ValueError(f"Threshold deve estar entre 0 e 1: {value}")
        if word:
            self._thresholds[word] = value
        else:
            self._base_threshold = value
            for w in list(self._thresholds.keys()):
                if w != RESERVED_WAKE_WORD:
                    self._thresholds[w] = value
        logger.info("Threshold ajustado: %s -> %.2f", word or "todas", value)

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def threshold(self) -> float:
        return self._base_threshold

    @property
    def activation_word(self) -> str:
        return self._detected_word or self._configured_word or DEFAULT_WAKE_WORD

    @property
    def configured_words(self) -> list[str]:
        return list(self._sessions.keys())

    @property
    def model_dir(self) -> str:
        return str(self._model_dir)

    def unload(self):
        self._sessions.clear()
        self._thresholds.clear()
        self._available = False
        self._af = None
        self._audio_buffer = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
        self._buffer_filled = False
        self._samples_since_fill = 0
