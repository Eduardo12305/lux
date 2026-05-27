# lux/voice/stt.py
# Módulo: Voice
# Dependências: faster-whisper (large-v3-turbo, ~150MB VRAM, melhor pt-BR)
# Status: IMPLEMENTADO
# Notas: Cycle de vida gerenciado pelo WhisperLifecycleManager.

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "large-v3-turbo"
MODEL_CACHE_DIR = Path("~/.lux/models/faster-whisper").expanduser()
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class STTEngine:
    """Speech-to-Text via faster-whisper."""

    _instance: Optional[STTEngine] = None

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._loaded = False
        self._lock = asyncio.Lock()

    async def ensure_loaded(self) -> bool:
        if self._loaded:
            return True
        async with self._lock:
            if self._loaded:
                return True
            try:
                loop = asyncio.get_event_loop()
                self._model = await loop.run_in_executor(None, self._load_model)
                self._loaded = True
                logger.info("STT carregado: faster-whisper %s", self._model_name)
                return True
            except Exception as e:
                logger.warning("Falha ao carregar faster-whisper: %s", e)
                return False

    def _load_model(self):
        from faster_whisper import WhisperModel
        return WhisperModel(
            self._model_name,
            device="auto",
            compute_type="auto",
            download_root=str(MODEL_CACHE_DIR),
        )

    async def transcribe(self, audio_bytes: bytes, language: str = "pt") -> str:
        if not await self.ensure_loaded():
            return "[STT indisponivel]"

        try:
            import numpy as np
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            loop = asyncio.get_event_loop()
            segments, info = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(
                    audio_np,
                    language=language,
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=500,
                    ),
                ),
            )
            text = " ".join(seg.text.strip() for seg in segments)
            logger.debug("STT: transcrito (%d chars)", len(text))
            return text if text else "[sem fala detectada]"
        except Exception as e:
            logger.warning("Falha na transcricao: %s", e)
            return "[erro na transcricao]"

    async def unload(self):
        async with self._lock:
            self._model = None
            self._loaded = False
            logger.info("STT descarregado")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def vram_usage_gb(self) -> float:
        if "large-v3-turbo" in self._model_name:
            return 0.15
        return 0.5
