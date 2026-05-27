# lux/voice/lifecycle.py
# Módulo: Voice
# Dependências: models/vram_guard.py, voice/stt.py
# Status: IMPLEMENTADO
# Notas: Ciclo de vida do STT com refcount atômico e timeout de inatividade.

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from lux.models.vram_guard import VRAMGuard
from lux.voice.stt import STTEngine

logger = logging.getLogger(__name__)

INACTIVITY_TIMEOUT = 60.0


class WhisperLifecycleManager:
    """
    Gerencia carga/descarga do faster-whisper.
    Atômico: refcount só incrementa após carga bem-sucedida.
    """

    _refcount: int = 0
    _last_used: float = 0.0
    _lock: asyncio.Lock | None = None
    _unload_task: Optional[asyncio.Task] = None

    def __init__(self, stt: STTEngine, vram_guard: Optional[VRAMGuard] = None):
        self._stt = stt
        self._vram = vram_guard
        if WhisperLifecycleManager._lock is None:
            WhisperLifecycleManager._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with WhisperLifecycleManager._lock:
            if WhisperLifecycleManager._refcount == 0:
                if self._vram and not await self._vram.can_load_model(
                    "whisper-small", self._stt.vram_usage_gb
                ):
                    logger.warning("VRAM insuficiente para STT")
                    return False
                if not await self._stt.ensure_loaded():
                    return False
            WhisperLifecycleManager._refcount += 1
            WhisperLifecycleManager._last_used = time.monotonic()
            if WhisperLifecycleManager._unload_task and not WhisperLifecycleManager._unload_task.done():
                WhisperLifecycleManager._unload_task.cancel()
                WhisperLifecycleManager._unload_task = None
            return True

    async def release(self):
        async with WhisperLifecycleManager._lock:
            WhisperLifecycleManager._refcount = max(0, WhisperLifecycleManager._refcount - 1)
            WhisperLifecycleManager._last_used = time.monotonic()
            if WhisperLifecycleManager._refcount == 0:
                WhisperLifecycleManager._unload_task = asyncio.create_task(
                    self._auto_unload_after_timeout()
                )

    async def _auto_unload_after_timeout(self, timeout: float = INACTIVITY_TIMEOUT):
        await asyncio.sleep(timeout)
        async with WhisperLifecycleManager._lock:
            if WhisperLifecycleManager._refcount == 0:
                await self._stt.unload()
                logger.info("STT descarregado apos %.0fs de inatividade", timeout)

    async def force_unload(self):
        async with WhisperLifecycleManager._lock:
            WhisperLifecycleManager._refcount = 0
            if WhisperLifecycleManager._unload_task and not WhisperLifecycleManager._unload_task.done():
                WhisperLifecycleManager._unload_task.cancel()
            await self._stt.unload()
