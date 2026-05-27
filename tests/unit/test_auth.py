# tests/unit/test_auth.py
# Módulo: Testes de Auth
# Status: IMPLEMENTADO

from __future__ import annotations

import pytest

from lux.gateway.auth import (
    AuthManager,
    _generate_user_id,
    _hash_password,
    _verify_password,
)


@pytest.fixture
async def auth_manager(tmp_path):
    from lux.memory.session_db import SessionDB
    db = SessionDB(db_path=tmp_path / "test_auth.db")
    auth = AuthManager(session_db=db)
    yield auth
    await auth.close()


@pytest.mark.asyncio
async def test_hash_password_verify(auth_manager):
    pw = "minha-senha-segura"
    uid = _generate_user_id()
    h = _hash_password(pw, uid)
    assert _verify_password(pw, uid, h) is True
    assert _verify_password("senha-errada", uid, h) is False


@pytest.mark.asyncio
async def test_register_user(auth_manager):
    profile = await auth_manager.register_user("testuser", "senha123")
    assert profile is not None
    assert profile.username == "testuser"
    assert profile.user_id.startswith("usr_")


@pytest.mark.asyncio
async def test_register_duplicate_fails(auth_manager):
    await auth_manager.register_user("dup", "senha123")
    profile = await auth_manager.register_user("dup", "senha456")
    assert profile is None


@pytest.mark.asyncio
async def test_authenticate_user(auth_manager):
    await auth_manager.register_user("authuser", "senha123")
    profile = await auth_manager.authenticate_user("authuser", "senha123")
    assert profile is not None
    assert profile.username == "authuser"


@pytest.mark.asyncio
async def test_authenticate_wrong_password(auth_manager):
    await auth_manager.register_user("authuser", "senha123")
    profile = await auth_manager.authenticate_user("authuser", "errada")
    assert profile is None


@pytest.mark.asyncio
async def test_authenticate_nonexistent(auth_manager):
    profile = await auth_manager.authenticate_user("fantasma", "senha")
    assert profile is None


@pytest.mark.asyncio
async def test_create_and_verify_token(auth_manager):
    await auth_manager.register_user("tokenuser", "senha123")
    profile = await auth_manager._db.get_profile_by_username("tokenuser")
    token = auth_manager.create_token(profile.user_id, "user")
    assert token.count(".") == 2
    payload = auth_manager.verify_token(token)
    assert payload is not None
    assert payload["sub"] == profile.user_id
    assert payload["role"] == "user"


@pytest.mark.asyncio
async def test_verify_invalid_token(auth_manager):
    assert auth_manager.verify_token("invalid.token.here") is None
    assert auth_manager.verify_token("") is None


@pytest.mark.asyncio
async def test_verify_expired_token(auth_manager):
    import time
    auth_manager._session_expire_hours = -1
    profile = await auth_manager._authorize_cli("local")
    token = auth_manager.create_token(profile.user_id)
    payload = auth_manager.verify_token(token)
    assert payload is None  # expirou


@pytest.mark.asyncio
async def test_whitelist(auth_manager):
    user_id = "tg_12345"
    await auth_manager.add_to_whitelist("telegram", user_id, "Joao")
    assert await auth_manager.is_whitelisted("telegram", user_id) is True
    assert await auth_manager.is_whitelisted("discord", user_id) is False
    await auth_manager.remove_from_whitelist("telegram", user_id)
    assert await auth_manager.is_whitelisted("telegram", user_id) is False


@pytest.mark.asyncio
async def test_pairing_code_flow(auth_manager):
    user_id = "usr_test_123"
    code = await auth_manager.create_pairing_code(user_id, "telegram")
    assert len(code) == 6
    verified_user = await auth_manager.verify_pairing_code(code)
    assert verified_user == user_id
    verified_again = await auth_manager.verify_pairing_code(code)
    assert verified_again is None  # codigo ja consumido


@pytest.mark.asyncio
async def test_authorize_cli_admin(auth_manager):
    profile = await auth_manager._authorize_cli("local")
    assert profile.role.value == "admin"


@pytest.mark.asyncio
async def test_authorize_cli_new_user(auth_manager):
    profile = await auth_manager._authorize_cli("newuser")
    assert profile.username == "newuser"
    assert profile.role.value == "admin"  # primeiro usuario vira admin


@pytest.mark.asyncio
async def test_authorize_whitelisted_platform(auth_manager):
    user_id = "tg_999"
    await auth_manager.add_to_whitelist("telegram", user_id, "Teste")
    profile = await auth_manager.authorize("telegram", user_id)
    assert profile is not None
    assert profile.user_id == user_id


@pytest.mark.asyncio
async def test_authorize_not_whitelisted_denied(auth_manager):
    profile = await auth_manager.authorize("telegram", "desconhecido_xyz")
    assert profile is None


@pytest.mark.asyncio
async def test_list_users(auth_manager):
    await auth_manager.register_user("user1", "senha1")
    await auth_manager.register_user("user2", "senha2")
    users = await auth_manager.list_users()
    assert len(users) == 2


@pytest.mark.asyncio
async def test_delete_user(auth_manager):
    await auth_manager.register_user("todelete", "senha")
    await auth_manager.delete_user(
        (await auth_manager._db.get_profile_by_username("todelete")).user_id
    )
    assert await auth_manager._db.get_profile_by_username("todelete") is None
