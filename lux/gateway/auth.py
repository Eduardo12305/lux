# lux/gateway/auth.py
# Módulo: Auth
# Dependências: memory/session_db.py, config.py, agent/state.py
# Status: IMPLEMENTADO
# Notas: Gestão centralizada de autenticação (JWT, pairing, whitelist, rate limiting).

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from lux.agent.state import UserProfile, UserRole
from lux.config import get_config
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)


class AuthManager:
    """
    Gestao centralizada de autenticacao.
    Suporta: JWT, DM pairing, whitelist por plataforma, rate limiting.
    """

    def __init__(self, session_db: SessionDB | None = None):
        config = get_config()
        self._db = session_db or SessionDB()
        self._jwt_secret = config.jwt_secret.encode() if config.jwt_secret else b""
        self._session_expire_hours = config.session_expire_hours
        self._pairing_ttl_minutes = 10
        self._rate_limits: dict[str, dict[str, tuple[int, float]]] = {}
        self._max_requests_per_minute = 30

    # ── User Registration ──────────────────────────────────────────────

    async def register_user(
        self,
        username: str,
        password: str,
        display_name: str = "",
        role: UserRole = UserRole.USER,
    ) -> UserProfile | None:
        existing = await self._db.get_profile_by_username(username)
        if existing:
            logger.warning("Tentativa de registro duplicado: %s", username)
            return None

        user_id = _generate_user_id()
        password_hash = _hash_password(password, user_id)

        profile = UserProfile(
            user_id=user_id,
            username=username,
            display_name=display_name or username,
            role=role,
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )

        profile._password_hash = password_hash

        await self._db.create_profile(profile)
        await self._store_password_hash(user_id, password_hash)
        logger.info("Usuario registrado: %s (role=%s)", username, role.value)
        return profile

    async def authenticate_user(
        self, username: str, password: str
    ) -> UserProfile | None:
        profile = await self._db.get_profile_by_username(username)
        if not profile:
            return None

        stored_hash = await self._db._get_password_hash(profile.user_id)
        if not stored_hash:
            return None

        if not _verify_password(password, profile.user_id, stored_hash):
            return None

        profile.last_seen = datetime.now(timezone.utc)
        await self._db.update_profile(profile)
        return profile

    async def get_profile(self, user_id: str) -> UserProfile | None:
        profile = await self._db.get_profile(user_id)
        if profile:
            profile._password_hash = await self._db._get_password_hash(user_id)
        return profile

    async def update_profile(self, profile: UserProfile) -> None:
        await self._db.update_profile(profile)

    async def delete_user(self, user_id: str) -> None:
        await self._db.delete_profile(user_id)
        await self._db._delete_password_hash(user_id)

    async def list_users(self) -> list[UserProfile]:
        return await self._db.list_profiles()

    async def _store_password_hash(self, user_id: str, password_hash: str) -> None:
        await self._db._store_password_hash(user_id, password_hash)

    # ── JWT ────────────────────────────────────────────────────────────

    def create_token(self, user_id: str, role: str = "user") -> str:
        header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}))
        now = int(time.time())
        exp = now + self._session_expire_hours * 3600
        payload = _b64url_encode(
            json.dumps({"sub": user_id, "role": role, "iat": now, "exp": exp})
        )
        signature = _hmac_sha256(f"{header}.{payload}", self._jwt_secret)
        return f"{header}.{payload}.{signature}"

    def verify_token(self, token: str) -> dict | None:
        try:
            header_b64, payload_b64, signature = token.split(".")
        except ValueError:
            return None

        expected = _hmac_sha256(f"{header_b64}.{payload_b64}", self._jwt_secret)
        if not hmac.compare_digest(signature, expected):
            return None

        try:
            payload = json.loads(_b64url_decode(payload_b64))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        if payload.get("exp", 0) < time.time():
            return None

        return payload

    # ── DM Pairing ─────────────────────────────────────────────────────

    async def create_pairing_code(
        self, user_id: str, platform: str
    ) -> str:
        code = secrets.token_hex(3)
        expires = datetime.now(timezone.utc) + timedelta(minutes=self._pairing_ttl_minutes)
        await self._db.save_pairing_code(code, user_id, platform, expires.isoformat())
        logger.info("Codigo pairing criado: %s para user=%s plataforma=%s", code, user_id, platform)
        return code

    async def verify_pairing_code(self, code: str) -> str | None:
        pairing = await self._db.get_pairing_code(code)
        if not pairing:
            return None

        expires = datetime.fromisoformat(pairing["expires_at"])
        if datetime.now(timezone.utc) > expires.replace(tzinfo=timezone.utc):
            await self._db.delete_pairing_code(code)
            return None

        await self._db.delete_pairing_code(code)
        return pairing["user_id"]

    async def cleanup_pairing_codes(self) -> int:
        return await self._db.cleanup_expired_pairing_codes()

    # ── Whitelist ──────────────────────────────────────────────────────

    async def add_to_whitelist(self, platform: str, user_id: str, label: str = "") -> None:
        await self._db.add_to_whitelist(platform, user_id, label)

    async def remove_from_whitelist(self, platform: str, user_id: str) -> None:
        await self._db.remove_from_whitelist(platform, user_id)

    async def is_whitelisted(self, platform: str, user_id: str) -> bool:
        return await self._db.is_whitelisted(platform, user_id)

    # ── Authorization Gate ─────────────────────────────────────────────

    async def authorize(
        self,
        platform: str,
        platform_user_id: str,
        token: str | None = None,
    ) -> UserProfile | None:
        if platform == "cli":
            return await self._authorize_cli(platform_user_id)

        linked_user_id = await self._db._get_platform_link(platform, platform_user_id)
        if linked_user_id:
            profile = await self._db.get_profile(linked_user_id)
            if profile:
                profile.last_seen = datetime.now(timezone.utc)
                await self._db.update_profile(profile)
                return profile

        if token:
            payload = self.verify_token(token)
            if payload:
                return await self._db.get_profile(payload["sub"])

        if await self._db.is_whitelisted(platform, platform_user_id):
            profile = await self._db.get_profile(platform_user_id)
            if not profile:
                display_name = f"{platform}:{platform_user_id}"
                profile = UserProfile(
                    user_id=platform_user_id,
                    username=f"{platform}_{platform_user_id}",
                    display_name=display_name,
                    role=UserRole.USER,
                    created_at=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                )
                await self._db.create_profile(profile)
            return profile

        logger.info("Acesso negado: platform=%s user=%s", platform, platform_user_id)
        return None

    async def link_platform(
        self, platform: str, platform_user_id: str, lux_user_id: str
    ) -> None:
        await self._db._link_platform(platform, platform_user_id, lux_user_id)
        logger.info("Plataforma linkada: %s:%s -> %s", platform, platform_user_id, lux_user_id)

    async def _authorize_cli(self, user_id: str) -> UserProfile:
        profile = await self._db.get_profile(user_id)
        if profile:
            return profile

        users = await self._db.list_profiles()
        if users:
            admin = next((u for u in users if u.role == UserRole.ADMIN), None)
            if admin:
                return admin

        profile = UserProfile(
            user_id=user_id,
            username=user_id,
            display_name=user_id,
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        await self._db.create_profile(profile)
        logger.info("Perfil local criado: %s (admin)", user_id)
        return profile

    # ── Rate Limiting ──────────────────────────────────────────────────

    def check_rate_limit(self, user_id: str, endpoint: str = "default") -> bool:
        now = time.monotonic()
        window = int(now // 60)

        if user_id not in self._rate_limits:
            self._rate_limits[user_id] = {}

        user_limits = self._rate_limits[user_id]
        key = f"{endpoint}:{window}"

        if key not in user_limits:
            user_limits[key] = (1, now)
            return True

        count, _ = user_limits[key]
        if count < self._max_requests_per_minute:
            user_limits[key] = (count + 1, now)
            return True

        return False

    async def close(self):
        await self._db.close()


# ── Crypto Helpers ────────────────────────────────────────────────────────


def _generate_user_id() -> str:
    return f"usr_{secrets.token_hex(12)}"


def _hash_password(password: str, user_id: str) -> str:
    salt = hashlib.sha256(user_id.encode()).digest()[:16]
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, 600_000, dklen=32
    ).hex()


def _verify_password(password: str, user_id: str, stored_hash: str) -> bool:
    expected = _hash_password(password, user_id)
    return hmac.compare_digest(expected, stored_hash)


def _b64url_encode(data: str) -> str:
    import base64
    return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()


def _b64url_decode(data: str) -> str:
    import base64
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data).decode()


def _hmac_sha256(message: str, secret: bytes) -> str:
    return hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()
