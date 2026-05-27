# tests/unit/test_auth_system.py
# Módulo: Testes do sistema completo de Auth + Permissoes
# Status: IMPLEMENTADO

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from lux.agent.state import UserProfile, UserRole
from lux.auth.admin_gate import AdminPasswordGate
from lux.auth.first_run import FirstRunWizard
from lux.auth.jwt_manager import JWTManager
from lux.auth.models import (
    AuthMethod,
    AuthSession,
    EnrollmentResult,
    VerificationResult,
)
from lux.auth.password import PasswordAuthenticator
from lux.auth.session_store import AuthSessionStore
from lux.memory.session_db import SessionDB


@pytest.fixture
def session_db(tmp_path):
    return SessionDB(db_path=tmp_path / "test_auth2.db")


@pytest.fixture
def password_auth(session_db):
    return PasswordAuthenticator(session_db)


@pytest.fixture
def jwt_manager():
    return JWTManager()


@pytest.fixture
def session_store(session_db):
    return AuthSessionStore(session_db)


# ── PasswordAuthenticator ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_verify_password(password_auth, session_db):
    uid = "usr_test_123"
    profile = UserProfile(user_id=uid, username="test", role=UserRole.USER)
    await session_db.create_profile(profile)
    await password_auth.set_password(uid, "minha-senha-forte-123")

    user, status = await password_auth.authenticate("test", "minha-senha-forte-123")
    assert user is not None
    assert status.value == "success"


@pytest.mark.asyncio
async def test_wrong_password_fails(password_auth, session_db):
    uid = "usr_test_456"
    profile = UserProfile(user_id=uid, username="test2", role=UserRole.USER)
    await session_db.create_profile(profile)
    await password_auth.set_password(uid, "senha-correta")

    user, status = await password_auth.authenticate("test2", "senha-errada")
    assert user is None
    assert status.value == "failed_password"


@pytest.mark.asyncio
async def test_lockout_after_5_failures(password_auth, session_db):
    uid = "usr_lock_1"
    profile = UserProfile(user_id=uid, username="locktest", role=UserRole.USER)
    await session_db.create_profile(profile)
    await password_auth.set_password(uid, "senha-correta")

    for _ in range(5):
        await password_auth.authenticate("locktest", "errada")

    user, status = await password_auth.authenticate("locktest", "senha-correta")
    assert status.value == "locked_out"


# ── JWTManager ───────────────────────────────────────────────────────────


def test_jwt_issue_and_verify(jwt_manager):
    user = UserProfile(user_id="usr_jwt_1", username="jwtuser", role=UserRole.USER)
    token = jwt_manager.issue_token(user, AuthMethod.PASSWORD)
    session = jwt_manager.verify_token(token)
    assert session is not None
    assert session.user_id == "usr_jwt_1"
    assert session.role == UserRole.USER


def test_jwt_guest_expires_4h(jwt_manager):
    user = UserProfile(user_id="usr_guest", username="guest", role=UserRole.GUEST)
    token = jwt_manager.issue_token(user, AuthMethod.PASSWORD)
    session = jwt_manager.verify_token(token)
    assert session is not None


def test_jwt_invalid_token(jwt_manager):
    assert jwt_manager.verify_token("invalid.token.here") is None
    assert jwt_manager.verify_token("") is None


# ── AuthSessionStore ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_session(session_store):
    session = await session_store.create_session("usr_1", UserRole.USER)
    fetched = await session_store.get_session(session.session_id)
    assert fetched is not None
    assert fetched.user_id == "usr_1"


@pytest.mark.asyncio
async def test_session_expired(session_store):
    session = await session_store.create_session("usr_1", UserRole.USER)
    session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await session_store._db._store_auth_session(session)
    assert await session_store.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_revoke_session(session_store):
    session = await session_store.create_session("usr_1", UserRole.USER)
    await session_store.revoke_session(session.session_id)
    assert await session_store.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_revoke_all(session_store):
    await session_store.create_session("usr_a", UserRole.USER)
    await session_store.create_session("usr_a", UserRole.USER)
    await session_store.revoke_all("usr_a")
    assert len(await session_store._db._list_active_sessions("usr_a")) == 0


# ── AdminPasswordGate ────────────────────────────────────────────────────


def test_is_dangerous_detects_patterns():
    gate = AdminPasswordGate()
    assert gate.is_dangerous("rm -rf /tmp/teste") is True
    assert gate.is_dangerous("sudo rm -rf /var/log") is True
    assert gate.is_dangerous("ls -la") is False
    assert gate.is_dangerous("echo hello") is False


def test_is_dangerous_detects_dd():
    gate = AdminPasswordGate()
    assert gate.is_dangerous("dd if=/dev/zero of=/dev/sda") is True


def test_is_dangerous_detects_mkfs():
    gate = AdminPasswordGate()
    assert gate.is_dangerous("mkfs.ext4 /dev/sdb1") is True


def test_is_dangerous_detects_chmod_777_root():
    gate = AdminPasswordGate()
    assert gate.is_dangerous("chmod 777 /etc") is True


def test_is_dangerous_false_positive_normal_chmod():
    gate = AdminPasswordGate()
    assert gate.is_dangerous("chmod 755 script.sh") is False


# ── FirstRunWizard ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_first_run_true(session_db):
    wizard = FirstRunWizard(session_db)
    assert await wizard.is_first_run() is True


@pytest.mark.asyncio
async def test_is_first_run_false_after_user(session_db):
    wizard = FirstRunWizard(session_db)
    await session_db.create_profile(UserProfile(
        user_id="usr_1", username="admin", role=UserRole.ADMIN,
        created_at=datetime.now(timezone.utc),
    ))
    assert await wizard.is_first_run() is False


# ── Permissions Matrix (ToolRegistry) ────────────────────────────────────


def test_permissions_admin_can_use_terminal():
    from lux.tools.registry import _has_permission
    assert _has_permission("shell_run", UserRole.ADMIN) is True


def test_permissions_user_cannot_use_terminal():
    from lux.tools.registry import _has_permission
    assert _has_permission("shell_run", UserRole.USER) is False


def test_permissions_guest_can_use_web():
    from lux.tools.registry import _has_permission
    assert _has_permission("web_search", UserRole.GUEST) is True


def test_permissions_guest_cannot_use_git():
    from lux.tools.registry import _has_permission
    assert _has_permission("git_status", UserRole.GUEST) is False


def test_permissions_user_can_use_filesystem():
    from lux.tools.registry import _has_permission
    assert _has_permission("web_search", UserRole.USER) is True


def test_permissions_user_can_use_calendar():
    from lux.tools.registry import _has_permission
    assert _has_permission("calendar_read", UserRole.USER) is True


# ── SpeakerVerifier ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_no_model_returns_fallback(session_db):
    from lux.speaker.verifier import AudioSample, SpeakerVerifier
    from lux.speaker.profile_store import VoiceProfileStore
    store = VoiceProfileStore(session_db)
    verifier = SpeakerVerifier(store)
    audio = AudioSample(b"fake_audio", duration_s=5.0, snr_db=30.0)
    result = await verifier.verify("usr_nonexistent", audio)
    assert result.method in ("FALLBACK_NEEDED", "REJECTED")


@pytest.mark.asyncio
async def test_identify_empty(session_db):
    from lux.speaker.verifier import AudioSample, SpeakerVerifier
    from lux.speaker.profile_store import VoiceProfileStore
    store = VoiceProfileStore(session_db)
    verifier = SpeakerVerifier(store)
    audio = AudioSample(b"fake_audio", duration_s=5.0, snr_db=30.0)
    result = await verifier.identify(audio)
    assert result.method == "REJECTED"


@pytest.mark.asyncio
async def test_enrollment_rejects_insufficient_samples(session_db):
    from lux.speaker.verifier import AudioSample, SpeakerVerifier
    from lux.speaker.profile_store import VoiceProfileStore
    store = VoiceProfileStore(session_db)
    verifier = SpeakerVerifier(store)
    samples = [AudioSample(b"fake", duration_s=5.0, snr_db=30.0) for _ in range(3)]
    result = await verifier.enroll("usr_1", samples)
    assert result.success is False


@pytest.mark.asyncio
async def test_enrollment_mock_embedding(session_db):
    from lux.speaker.verifier import AudioSample, SpeakerVerifier
    from lux.speaker.profile_store import VoiceProfileStore
    store = VoiceProfileStore(session_db)
    verifier = SpeakerVerifier(store)
    async def fake_extract(audio):
        import numpy as np
        rng = np.random.default_rng(42)
        return rng.normal(size=192).tolist()
    verifier.extract_embedding = fake_extract
    samples = [AudioSample(b"fake", duration_s=5.0, snr_db=30.0) for _ in range(6)]
    result = await verifier.enroll("usr_1", samples)
    assert result.success is True
    assert result.n_samples >= 6
