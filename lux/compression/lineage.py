# lux/compression/lineage.py
# Módulo: Compression
# Dependências: memory/session_db.py
# Status: IMPLEMENTADO

from __future__ import annotations

from lux.memory.session_db import SessionDB


class SessionLineage:
    """Helpers para tracking de linhagem de sessoes."""

    def __init__(self, session_db: SessionDB):
        self._db = session_db

    async def create_child(
        self,
        parent_session_id: str,
        summary: str,
        messages_compressed: int,
    ) -> str:
        return await self._db.create_child_session(
            parent_session_id, summary, messages_compressed
        )
