# lux/interfaces/hermes_cli/auth.py
# Módulo: CLI Auth
# Dependências: gateway/auth.py
# Status: IMPLEMENTADO
# Notas: Comandos CLI para gestao de usuarios, whitelist, pairing.

from __future__ import annotations

import getpass
import logging
from typing import Optional

from lux.agent.state import UserRole
from lux.gateway.auth import AuthManager

logger = logging.getLogger(__name__)


class AuthCommands:
    """Comandos de autenticacao e gestao de usuarios para CLI."""

    def __init__(self, auth: AuthManager):
        self._auth = auth

    async def register(
        self,
        username: str,
        password: Optional[str] = None,
        display_name: str = "",
        role: str = "user",
    ) -> str:
        if not password:
            password = getpass.getpass("Senha: ")
            confirm = getpass.getpass("Confirmar senha: ")
            if password != confirm:
                return "Erro: Senhas não conferem."

        try:
            user_role = UserRole(role.lower())
        except ValueError:
            return f"Erro: Role invalida. Use: admin, user, guest."

        profile = await self._auth.register_user(
            username=username,
            password=password,
            display_name=display_name,
            role=user_role,
        )

        if profile:
            return (
                f"Usuario registrado:\n"
                f"  ID: {profile.user_id}\n"
                f"  Username: {profile.username}\n"
                f"  Role: {profile.role.value}\n"
                f"  Display: {profile.display_name}"
            )
        return f"Erro: Username '{username}' ja existe."

    async def login(self, username: str, password: Optional[str] = None) -> str:
        if not password:
            password = getpass.getpass("Senha: ")

        profile = await self._auth.authenticate_user(username, password)
        if not profile:
            return "Erro: Credenciais invalidas."

        token = self._auth.create_token(profile.user_id, profile.role.value)
        return (
            f"Autenticado como: {profile.username} ({profile.role.value})\n"
            f"Token JWT: {token[:40]}..."
        )

    async def whitelist_add(
        self, platform: str, user_id: str, label: str = ""
    ) -> str:
        await self._auth.add_to_whitelist(platform, user_id, label)
        return f"Usuario {user_id} adicionado a whitelist da plataforma {platform}."

    async def whitelist_remove(self, platform: str, user_id: str) -> str:
        await self._auth.remove_from_whitelist(platform, user_id)
        return f"Usuario {user_id} removido da whitelist da plataforma {platform}."

    async def whitelist_show(self, platform: str) -> str:
        users = await self._auth._db.get_whitelist(platform)
        if not users:
            return f"Nenhum usuario na whitelist da plataforma {platform}."
        return f"Whitelist {platform}:\n" + "\n".join(f"  - {u}" for u in users)

    async def list_users(self) -> str:
        users = await self._auth.list_users()
        if not users:
            return "Nenhum usuario registrado."
        lines = [f"Usuarios ({len(users)}):"]
        for u in users:
            lines.append(
                f"  {u.username:20s} | {u.role.value:6s} | "
                f"{u.display_name:30s} | {u.user_id}"
            )
        return "\n".join(lines)

    async def delete_user(self, username: str) -> str:
        profile = await self._auth._db.get_profile_by_username(username)
        if not profile:
            return f"Erro: Usuario '{username}' nao encontrado."
        await self._auth.delete_user(profile.user_id)
        return f"Usuario '{username}' removido."

    async def create_token(self, username: str) -> str:
        profile = await self._auth._db.get_profile_by_username(username)
        if not profile:
            return f"Erro: Usuario '{username}' nao encontrado."
        token = self._auth.create_token(profile.user_id, profile.role.value)
        return f"Token JWT para {username}:\n{token}"

    async def verify_token(self, token: str) -> str:
        payload = self._auth.verify_token(token)
        if not payload:
            return "Token invalido ou expirado."
        return (
            f"Token valido:\n"
            f"  User ID: {payload.get('sub')}\n"
            f"  Role: {payload.get('role')}\n"
            f"  Expira em: {payload.get('exp', 0)}"
        )

    async def setup_pairing(
        self, user_id: str, platform: str
    ) -> str:
        code = await self._auth.create_pairing_code(user_id, platform)
        return (
            f"Codigo de pairing gerado para {platform}:\n"
            f"  Codigo: {code}\n"
            f"  Envie este codigo para o usuario via DM."
        )
