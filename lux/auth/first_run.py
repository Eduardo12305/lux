# lux/auth/first_run.py
# Módulo: Auth
# Dependências: auth/password.py, auth/jwt_manager.py, memory/session_db.py
# Status: IMPLEMENTADO

from __future__ import annotations

import asyncio
import getpass
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

from lux.agent.state import UserProfile, UserRole
from lux.auth.jwt_manager import JWTManager
from lux.auth.password import PasswordAuthenticator
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)

ENV_PATH = Path(".env").resolve()


def _write_env_var(key: str, value: str):
    """Escreve/atualiza uma variavel no .env sem perder outras."""
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text().split("\n")
    else:
        lines = []

    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=")[0].strip()
            if k == key:
                new_lines.append(f"{key}={value}")
                updated = True
                continue
        new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n")


class FirstRunWizard:
    """Wizard de configuracao inicial — admin + palavra de ativacao."""

    def __init__(self, session_db: SessionDB | None = None):
        self._db = session_db or SessionDB()
        self._password_auth = PasswordAuthenticator(self._db)

    async def is_first_run(self) -> bool:
        users = await self._db.list_profiles()
        return len(users) == 0

    async def run_wizard(self) -> UserProfile | None:
        print("╔══════════════════════════════════════════╗")
        print("║   Lux — Configuracao Inicial            ║")
        print("╚══════════════════════════════════════════╝")
        print()
        print("Bem-vindo ao Lux. Nenhum usuario configurado.")
        print("Voce sera registrado como administrador.")
        print()

        print("[1/4] Identificacao")
        display = input("  Nome de exibicao: ").strip()
        username = input("  Username [admin]: ").strip() or "admin"

        while True:
            pw = getpass.getpass("  Senha (min 12 caracteres): ")
            if len(pw) < 12:
                print("  Senha muito curta — minimo 12 caracteres.")
                continue
            confirm = getpass.getpass("  Confirmar senha: ")
            if pw != confirm:
                print("  Senhas nao conferem. Tente novamente.")
                continue
            break

        print(f"  ✅ Usuario '{username}' configurado")
        print()

        print("[2/4] Criando perfil...", end=" ", flush=True)
        profile = UserProfile(
            user_id=f"usr_{secrets.token_hex(12)}",
            username=username,
            display_name=display or username,
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        await self._db.create_profile(profile)
        await self._password_auth.set_password(profile.user_id, pw)
        print("✅")
        print()

        print("[3/4] Inicializando seguranca...", end=" ", flush=True)
        JWTManager()
        await self._db.add_to_whitelist("cli", profile.user_id, "admin")
        logger.info("Admin criado via first-run wizard: %s", username)
        print("✅")
        print()

        print()
        print("=" * 44)
        print("  Admin criado. Lux esta pronto.")
        print("=" * 44)
        print(f"  Username: {username}")
        print(f"  Role:     admin")
        print()

        return profile

