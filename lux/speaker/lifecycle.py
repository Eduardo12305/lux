# lux/speaker/lifecycle.py
from __future__ import annotations
import asyncio
import logging
from lux.models.vram_guard import VRAMGuard
from lux.speaker.verifier import SpeakerVerifier

logger = logging.getLogger(__name__)


class ECAPALifecycleManager:
    _refcount: int = 0
    _lock: asyncio.Lock | None = None

    def __init__(self, verifier: SpeakerVerifier, vram_guard: VRAMGuard | None = None):
        self._verifier = verifier
        self._vram = vram_guard
        if ECAPALifecycleManager._lock is None:
            ECAPALifecycleManager._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with ECAPALifecycleManager._lock:
            if ECAPALifecycleManager._refcount == 0:
                if self._vram and not await self._vram.can_load_model("ecapa-tdnn", 0.2):
                    return False
                if not await self._verifier.ensure_loaded():
                    return False
            ECAPALifecycleManager._refcount += 1
            return True

    async def release(self) -> None:
        async with ECAPALifecycleManager._lock:
            ECAPALifecycleManager._refcount = max(0, ECAPALifecycleManager._refcount - 1)
            if ECAPALifecycleManager._refcount == 0:
                await self._verifier.unload()
