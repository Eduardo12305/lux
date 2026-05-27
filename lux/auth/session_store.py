# lux/auth/session_store.py
# Módulo: Auth
# Dependências: auth/models.py, memory/session_db.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import uuid4

from lux.agent.state import UserRole
from lux.auth.models import (
    AuthMethod,
    AuthSession,
    SessionExpiredError,
    SessionRevokedError,
)
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)


class AuthSessionStore:
    """Gerencia sessoes de autenticacao com persistencia e revogacao."""

    def __init__(self, session_db: SessionDB | None = None):
        self._db = session_db or SessionDB()
        self._revoked: set[str] = set()

    async def create_session(
        self,
        user_id: str,
        role: UserRole,
        auth_method: AuthMethod = AuthMethod.PASSWORD,
        voice_confidence: Optional[float] = None,
    ) -> AuthSession:
        hours = 4 if role == UserRole.GUEST else 24
        now = datetime.now(timezone.utc)
        session = AuthSession(
            session_id=uuid4().hex,
            user_id=user_id,
            role=role,
            auth_method=auth_method,
            voice_confidence=voice_confidence,
            created_at=now,
            expires_at=now + timedelta(hours=hours),
            last_activity=now,
        )
        await self._db._store_auth_session(session)
        return session

    async def get_session(self, session_id: str) -> Optional[AuthSession]:
        if session_id in self._revoked:
            return None
        session = await self._db._get_auth_session(session_id)
        if not session:
            return None
        if session.is_expired():
            await self._db._deactivate_auth_session(session_id)
            return None
        return session

    async def update_activity(self, session_id: str) -> None:
        await self._db._update_auth_session_activity(
            session_id, datetime.now(timezone.utc)
        )

    async def is_session_valid(self, session: AuthSession) -> bool:
        if not session.is_active:
            return False
        if session.session_id in self._revoked:
            return False
        if session.is_expired():
            await self._db._deactivate_auth_session(session.session_id)
            return False
        return True

    async def revoke_session(self, session_id: str) -> None:
        self._revoked.add(session_id)
        await self._db._revoke_auth_session(session_id)

    async def revoke_all(self, user_id: str) -> None:
        sessions = await self._db._list_active_sessions(user_id)
        for s in sessions:
            await self.revoke_session(s.session_id)

    async def cleanup_expired(self) -> int:
        return await self._db._cleanup_expired_auth_sessions()
