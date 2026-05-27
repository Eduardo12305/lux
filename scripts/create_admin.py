#!/usr/bin/env python3
# scripts/create_admin.py
# Cria usuario admin inicial no banco de dados do Lux.

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lux.agent.state import UserRole
from lux.gateway.auth import AuthManager


async def main():
    print("╔══════════════════════════════════════╗")
    print("║   Lux — Criacao de Admin Inicial    ║")
    print("╚══════════════════════════════════════╝")
    print()

    auth = AuthManager()

    username = input("Username [admin]: ").strip() or "admin"
    display = input("Display name [Administrador]: ").strip() or "Administrador"

    while True:
        password = getpass.getpass("Senha: ").strip()
        if len(password) < 8:
            print("Senha deve ter ao menos 8 caracteres.")
            continue
        confirm = getpass.getpass("Confirmar senha: ").strip()
        if password != confirm:
            print("Senhas nao conferem. Tente novamente.")
            continue
        break

    existing = await auth._db.get_profile_by_username(username)
    if existing:
        print(f"\nUsuario '{username}' ja existe.")
        print(f"  ID: {existing.user_id}")
        print(f"  Role: {existing.role.value}")
        overwrite = input("Sobrescrever? [s/N]: ").strip().lower()
        if overwrite != "s":
            print("Cancelado.")
            return
        await auth.delete_user(existing.user_id)

    profile = await auth.register_user(
        username=username,
        password=password,
        display_name=display,
        role=UserRole.ADMIN,
    )

    if profile:
        print(f"\nAdmin criado com sucesso:")
        print(f"  ID: {profile.user_id}")
        print(f"  Username: {profile.username}")
        print(f"  Role: {profile.role.value}")

        token = auth.create_token(profile.user_id, "admin")
        print(f"  Token JWT: {token[:60]}...")

        await auth.add_to_whitelist("cli", profile.user_id, "admin")
        print(f"\nAdicionado a whitelist CLI automaticamente.")
    else:
        print("Erro ao criar admin.")

    await auth.close()


if __name__ == "__main__":
    asyncio.run(main())
