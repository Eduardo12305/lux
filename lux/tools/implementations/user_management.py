# lux/tools/implementations/user_management.py
# Módulo: Tools
# Dependências: auth/password.py, memory/session_db.py, agent/state.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from lux.agent.state import AgentState, ToolResult, UserRole
from lux.auth.password import PasswordAuthenticator
from lux.memory.session_db import SessionDB
from lux.tools.base import Tool

logger = logging.getLogger(__name__)


class UserManagementTool(Tool):
    name = "user_management"
    description = "Gerencia usuarios do sistema (apenas ADMIN)"
    timeout_seconds = 30
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "create", "delete", "promote", "demote",
                         "set_guest", "reset_password", "revoke_voice", "lock", "unlock"],
            },
            "target_username": {"type": "string"},
            "new_password": {"type": "string"},
        },
        "required": ["action"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        import asyncio
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._execute_async(args, state))

    async def _execute_async(self, args: dict, state: AgentState) -> ToolResult:
        action = args.get("action", "list")
        target = args.get("target_username", "")

        match action:
            case "list":
                return await self._list_users(state)
            case "create":
                return await self._create_user(target, args, state)
            case "delete":
                return await self._delete_user(target, state)
            case "promote":
                return await self._change_role(target, UserRole.ADMIN, state)
            case "demote":
                return await self._change_role(target, UserRole.USER, state)
            case "set_guest":
                return await self._change_role(target, UserRole.GUEST, state)
            case "reset_password":
                return await self._reset_password(target, args, state)
            case "revoke_voice":
                return await self._revoke_voice(target, state)
            case "lock":
                return await self._lock_user(target, state)
            case "unlock":
                return await self._unlock_user(target, state)
            case _:
                return ToolResult.failure(f"Acao desconhecida: {action}")

    async def _list_users(self, state: AgentState) -> ToolResult:
        db = SessionDB()
        users = await db.list_profiles()
        lines = [f"Usuarios ({len(users)}):"]
        for u in users:
            lines.append(f"  {u.username:20s} | {u.role.value:6s} | {u.display_name}")
        return ToolResult.ok("\n".join(lines))

    async def _create_user(self, username: str, args: dict, state: AgentState) -> ToolResult:
        if not username:
            return ToolResult.failure("target_username obrigatorio para create")
        db = SessionDB()
        existing = await db.get_profile_by_username(username)
        if existing:
            return ToolResult.failure(f"Usuario '{username}' ja existe")

        from lux.agent.state import UserProfile
        password = args.get("new_password", "") or secrets.token_urlsafe(12)
        pw_auth = PasswordAuthenticator(db)

        user_id = f"usr_{secrets.token_hex(12)}"
        profile = UserProfile(
            user_id=user_id,
            username=username,
            display_name=username,
            role=UserRole.USER,
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        await db.create_profile(profile)
        await pw_auth.set_password(user_id, password)

        return ToolResult.ok(
            f"Usuario criado: {username}\n"
            f"  Credenciais: username={username} senha={password}\n"
            f"  (o usuario deve trocar a senha no primeiro acesso)"
        )

    async def _delete_user(self, username: str, state: AgentState) -> ToolResult:
        db = SessionDB()
        profile = await db.get_profile_by_username(username)
        if not profile:
            return ToolResult.failure(f"Usuario '{username}' nao encontrado")
        if profile.user_id == state.user_id:
            return ToolResult.failure("Admin nao pode se deletar (anti-lockout)")
        await db.delete_profile(profile.user_id)
        await db._delete_password_hash(profile.user_id)
        await db._delete_voice_profile(profile.user_id)
        return ToolResult.ok(f"Usuario '{username}' removido")

    async def _change_role(self, username: str, new_role: UserRole, state: AgentState) -> ToolResult:
        db = SessionDB()
        profile = await db.get_profile_by_username(username)
        if not profile:
            return ToolResult.failure(f"Usuario '{username}' nao encontrado")
        if new_role != UserRole.ADMIN and profile.user_id == state.user_id:
            return ToolResult.failure("Admin nao pode se rebaixar (anti-lockout)")
        if new_role != UserRole.ADMIN and profile.role == UserRole.ADMIN:
            admins = [u for u in await db.list_profiles() if u.role == UserRole.ADMIN]
            if len(admins) <= 1:
                return ToolResult.failure("Deve existir ao menos 1 admin (anti-lockout)")
        profile.role = new_role
        await db.update_profile(profile)
        return ToolResult.ok(f"Role de '{username}' alterado para {new_role.value}")

    async def _reset_password(self, username: str, args: dict, state: AgentState) -> ToolResult:
        db = SessionDB()
        profile = await db.get_profile_by_username(username)
        if not profile:
            return ToolResult.failure(f"Usuario '{username}' nao encontrado")
        new_pw = args.get("new_password", "") or secrets.token_urlsafe(12)
        pw_auth = PasswordAuthenticator(db)
        await pw_auth.set_password(profile.user_id, new_pw)
        return ToolResult.ok(f"Senha de '{username}' resetada. Nova senha: {new_pw}")

    async def _revoke_voice(self, username: str, state: AgentState) -> ToolResult:
        db = SessionDB()
        profile = await db.get_profile_by_username(username)
        if not profile:
            return ToolResult.failure(f"Usuario '{username}' nao encontrado")
        await db._delete_voice_profile(profile.user_id)
        return ToolResult.ok(f"Enrollment de voz de '{username}' removido")

    async def _lock_user(self, username: str, state: AgentState) -> ToolResult:
        db = SessionDB()
        profile = await db.get_profile_by_username(username)
        if not profile:
            return ToolResult.failure(f"Usuario '{username}' nao encontrado")
        await db._set_locked_until(profile.user_id, datetime(2099, 1, 1))
        return ToolResult.ok(f"Usuario '{username}' bloqueado")

    async def _unlock_user(self, username: str, state: AgentState) -> ToolResult:
        db = SessionDB()
        profile = await db.get_profile_by_username(username)
        if not profile:
            return ToolResult.failure(f"Usuario '{username}' nao encontrado")
        await db._reset_failed_attempts(profile.user_id)
        return ToolResult.ok(f"Usuario '{username}' desbloqueado")
