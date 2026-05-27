# lux/auth/jwt_manager.py
# Módulo: Auth
# Dependências: auth/models.py, config.py
# Status: IMPLEMENTADO

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lux.agent.state import UserProfile, UserRole
from lux.auth.models import AuthMethod, AuthSession, AuthStatus
from lux.config import get_config

logger = logging.getLogger(__name__)

JWT_SECRET_PATH = Path("~/.lux/jwt_secret").expanduser()


class JWTManager:
    """JWT HS256 local. Secret armazenado em ~/.lux/jwt_secret (chmod 600)."""

    def __init__(self):
        self._secret = self._load_or_create_secret()

    def _load_or_create_secret(self) -> bytes:
        if JWT_SECRET_PATH.exists():
            return JWT_SECRET_PATH.read_bytes()
        config = get_config()
        if config.jwt_secret:
            secret = config.jwt_secret.encode()
        else:
            secret = secrets.token_bytes(32)
        JWT_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
        JWT_SECRET_PATH.write_bytes(secret)
        JWT_SECRET_PATH.chmod(0o600)
        return secret

    def issue_token(
        self,
        user: UserProfile,
        auth_method: AuthMethod = AuthMethod.PASSWORD,
        voice_confidence: Optional[float] = None,
    ) -> str:
        now = int(time.time())
        exp_hours = 4 if user.role == UserRole.GUEST else 24
        exp = now + exp_hours * 3600

        payload = {
            "sub": user.user_id,
            "username": user.username,
            "role": user.role.value,
            "auth_method": auth_method.value,
            "voice_confidence": voice_confidence,
            "iat": now,
            "exp": exp,
        }
        header_b64 = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}))
        payload_b64 = _b64url(json.dumps(payload))
        signature = _hmac_sha256(f"{header_b64}.{payload_b64}", self._secret)
        return f"{header_b64}.{payload_b64}.{signature}"

    def verify_token(self, token: str) -> Optional[AuthSession]:
        try:
            header_b64, payload_b64, signature = token.split(".")
        except ValueError:
            return None

        expected = _hmac_sha256(f"{header_b64}.{payload_b64}", self._secret)
        if not hmac.compare_digest(signature, expected):
            return None

        try:
            payload = json.loads(_b64url_decode(payload_b64))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        if payload.get("exp", 0) < time.time():
            return None

        try:
            role = UserRole(payload.get("role", "user"))
            auth_method = AuthMethod(payload.get("auth_method", "password"))
        except ValueError:
            role = UserRole.USER
            auth_method = AuthMethod.PASSWORD

        return AuthSession(
            session_id=f"jwt_{payload.get('sub', '')[:12]}",
            user_id=payload.get("sub", ""),
            role=role,
            auth_method=auth_method,
            voice_confidence=payload.get("voice_confidence"),
        )


def _b64url(data: str) -> str:
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
