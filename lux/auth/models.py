# lux/auth/models.py
# Módulo: Auth
# Dependências: agent/state.py
# Status: IMPLEMENTADO

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from lux.agent.state import Channel, UserRole


class AuthMethod(str, Enum):
    PASSWORD = "password"
    VOICE = "voice"
    VOICE_FALLBACK = "voice_fallback"
    PIN = "pin"


class AuthStatus(str, Enum):
    SUCCESS = "success"
    FAILED_PASSWORD = "failed_password"
    FAILED_VOICE = "failed_voice"
    LOCKED_OUT = "locked_out"
    FALLBACK_NEEDED = "fallback_needed"
    NOT_ENROLLED = "not_enrolled"


@dataclass
class AuthSession:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    user_id: str = ""
    role: UserRole = UserRole.USER
    auth_method: AuthMethod = AuthMethod.PASSWORD
    voice_confidence: Optional[float] = None
    channel: Channel = Channel.CLI
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_voice_check: Optional[datetime] = None
    is_active: bool = True

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or datetime.now(timezone.utc)) > self.expires_at


@dataclass
class VerificationResult:
    accepted: bool
    confidence: float
    method: Literal["ACCEPTED", "FALLBACK_NEEDED", "REJECTED"] = "REJECTED"
    user_id: Optional[str] = None


@dataclass
class EnrollmentResult:
    success: bool
    n_samples: int = 0
    estimated_eer: float = 1.0
    quality: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    warnings: list[str] = field(default_factory=list)


@dataclass
class AdminConfirmResult:
    approved: bool
    method: Literal["PASSWORD", "CANCELLED", "BLOCKED_NOT_ADMIN"] = "CANCELLED"
    attempts: int = 0


@dataclass
class ContinuityResult:
    same_speaker: bool
    confidence: float
    action: Literal["CONTINUE", "WARN", "REAUTH", "INVALIDATE"] = "CONTINUE"


class SessionExpiredError(Exception):
    pass


class SessionRevokedError(Exception):
    pass


class AuthLockedError(Exception):
    pass
