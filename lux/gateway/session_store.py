# lux/gateway/session_store.py
# Módulo: Gateway
# Dependências: memory/session_db.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
from uuid import uuid4

from lux.agent.state import Channel
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)


class SessionStore:
    """Gerencia sessoes do gateway com persistencia em SQLite."""

    def __init__(self, session_db: SessionDB | None = None):
        self._db = session_db or SessionDB()

    async def get_or_create(
        self, user_id: str, channel: Channel
    ) -> str:
        session_id = uuid4().hex
        await self._db.create_session(session_id, user_id, channel)
        return session_id
