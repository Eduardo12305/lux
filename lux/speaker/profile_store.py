# lux/speaker/profile_store.py
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)


class VoiceProfileStore:
    def __init__(self, session_db: SessionDB | None = None):
        self._db = session_db or SessionDB()
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_centroid(self, user_id: str) -> Optional[list[float]]:
        row = await self._db._get_voice_centroid(user_id)
        if row:
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return None

    async def set_centroid(self, user_id: str, centroid: list[float], n_samples: int,
                            estimated_eer: float, quality: str) -> None:
        await self._db._set_voice_centroid(user_id, json.dumps(centroid),
                                            n_samples, estimated_eer, quality)

    async def update_centroid(self, user_id: str, new_embedding: list[float]) -> None:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        async with self._locks[user_id]:
            current = await self.get_centroid(user_id)
            if not current:
                await self.set_centroid(user_id, new_embedding, 1, 0.5, "LOW")
                return
            n = await self._db._get_voice_sample_count(user_id)
            n += 1
            decay = 0.95
            new_centroid = [_decay_avg(c, e, decay) for c, e in zip(current, new_embedding)]
            await self.set_centroid(user_id, new_centroid, min(n, 20), 0.5, "MEDIUM")

    async def store_sample(self, user_id: str, embedding: list[float], snr_db: float, duration_s: float) -> None:
        await self._db._store_voice_sample(user_id, json.dumps(embedding), snr_db, duration_s)

    async def list_all(self) -> dict[str, list[float]]:
        rows = await self._db._list_voice_profiles()
        result = {}
        for row in rows:
            centroid = json.loads(row["centroid"]) if isinstance(row["centroid"], str) else row["centroid"]
            result[row["user_id"]] = centroid
        return result

    async def delete_profile(self, user_id: str) -> None:
        await self._db._delete_voice_profile(user_id)


def _decay_avg(old: float, new: float, decay: float) -> float:
    return decay * old + (1.0 - decay) * new
