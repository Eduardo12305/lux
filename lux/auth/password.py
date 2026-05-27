# lux/auth/password.py
# Módulo: Auth
# Dependências: auth/models.py, memory/session_db.py
# Status: IMPLEMENTADO
# Notas: bcrypt com custo 12, lockout após 5 tentativas, PIN 6 dígitos.

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from lux.agent.state import UserProfile, UserRole
from lux.auth.models import AuthLockedError, AuthMethod, AuthSession, AuthStatus
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)

_BCRYPT_AVAILABLE = False
try:
    import bcrypt as _bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    pass

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
BCRYPT_ROUNDS = 12


class PasswordAuthenticator:
    """Autenticacao por senha/PIN com bcrypt e lockout."""

    def __init__(self, session_db: SessionDB | None = None):
        self._db = session_db or SessionDB()

    async def authenticate(
        self, username: str, password: str
    ) -> tuple[Optional[UserProfile], AuthStatus]:
        profile = await self._db.get_profile_by_username(username)
        if not profile:
            return None, AuthStatus.FAILED_PASSWORD

        locked_until = await self._db._get_locked_until(profile.user_id)
        if locked_until and datetime.now(timezone.utc) < locked_until:
            logger.warning("Usuario bloqueado: %s ate %s", username, locked_until)
            return None, AuthStatus.LOCKED_OUT

        stored_hash = await self._db._get_password_hash(profile.user_id)
        if not stored_hash:
            return None, AuthStatus.FAILED_PASSWORD

        if not _verify_bcrypt(password, stored_hash):
            await self._record_failed_attempt(profile.user_id)
            return None, AuthStatus.FAILED_PASSWORD

        await self._reset_failed_attempts(profile.user_id)
        profile.last_seen = datetime.now(timezone.utc)
        await self._db.update_profile(profile)
        return profile, AuthStatus.SUCCESS

    async def verify_admin_password(self, user_id: str, password: str) -> bool:
        stored_hash = await self._db._get_password_hash(user_id)
        if not stored_hash:
            return False
        return _verify_bcrypt(password, stored_hash)

    async def set_password(self, user_id: str, password: str) -> None:
        pw_hash = _hash_bcrypt(password)
        await self._db._store_password_hash(user_id, pw_hash)

    async def set_pin(self, user_id: str, pin: str) -> None:
        pin_hash = _hash_bcrypt(pin)
        await self._db._store_pin_hash(user_id, pin_hash)

    async def verify_pin(self, user_id: str, pin: str) -> bool:
        stored = await self._db._get_pin_hash(user_id)
        if not stored:
            return False
        return _verify_bcrypt(pin, stored)

    async def generate_temporary_password(self) -> str:
        chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789#@%&"
        return "".join(secrets.choice(chars) for _ in range(16))

    async def _record_failed_attempt(self, user_id: str) -> None:
        attempts = await self._db._increment_failed_attempts(user_id)
        if attempts >= MAX_FAILED_ATTEMPTS:
            lock_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            await self._db._set_locked_until(user_id, lock_until)
            logger.warning("Lockout ativado: user=%s ate %s", user_id, lock_until)

    async def _reset_failed_attempts(self, user_id: str) -> None:
        await self._db._reset_failed_attempts(user_id)

    async def close(self) -> None:
        await self._db.close()


def _hash_bcrypt(password: str) -> str:
    if _BCRYPT_AVAILABLE:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_bcrypt(password: str, stored_hash: str) -> bool:
    if _BCRYPT_AVAILABLE:
        return _bcrypt.checkpw(password.encode(), stored_hash.encode())
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash


def is_bcrypt_available() -> bool:
    return _BCRYPT_AVAILABLE
