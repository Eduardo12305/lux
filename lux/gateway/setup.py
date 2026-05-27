# lux/gateway/setup.py
# Módulo: Gateway
# Dependências: config.py
# Status: IMPLEMENTADO
# Notas: Wizards interativos para configurar Telegram e Discord.
#   Salva tokens no .env automaticamente. Unified memory via AuthManager.

from __future__ import annotations

import getpass
import os
import re
from pathlib import Path
from typing import Optional


ENV_PATH = Path(".env").resolve()


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _write_env(env: dict[str, str]):
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text().split("\n")
    else:
        lines = []

    updated: dict[str, bool] = {}
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=")[0].strip()
            if key in env:
                new_lines.append(f"{key}={env[key]}")
                updated[key] = True
                continue
        new_lines.append(line)

    for key, value in env.items():
        if not updated.get(key):
            new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n")


def _mask_token(token: str) -> str:
    if len(token) <= 8:
        return "*" * len(token)
    return token[:4] + "…" + token[-4:]


# ── Telegram Wizard ──────────────────────────────────────────────────────

TELEGRAM_SETUP_GUIDE = """
╔══════════════════════════════════════════════════════╗
║          📱 Configurar Telegram                     ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Passo 1: Abra o Telegram e procure por @BotFather   ║
║  Passo 2: Envie o comando /newbot                    ║
║  Passo 3: Escolha um nome (ex: Lux Assistente)       ║
║  Passo 4: Escolha um username (ex: lux_meu_bot)      ║
║  Passo 5: Copie o token que o BotFather enviar       ║
║  Passo 6: Cole o token abaixo                        ║
║                                                      ║
║  O token tem o formato:                              ║
║  1234567890:ABCdefGHIJklmNOPQRstuvWXYZ-1234567890    ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
"""


def setup_telegram() -> Optional[str]:
    print(TELEGRAM_SETUP_GUIDE)

    env = _read_env()
    current = env.get("LUX_TELEGRAM_TOKEN", "")

    if current:
        print(f"Token atual: {_mask_token(current)}")
        print()
        print("[1] Manter token atual")
        print("[2] Substituir token")
        print("[3] Remover (desconectar Telegram)")
        choice = input("Opcao [1]: ").strip() or "1"

        match choice:
            case "1":
                print("Token mantido.")
                return current
            case "2":
                pass
            case "3":
                env["LUX_TELEGRAM_TOKEN"] = ""
                _write_env(env)
                print("✅ Telegram desconectado. Token removido do .env")
                return None
            case _:
                return current

    print("Cole o token do BotFather (ou Enter para cancelar):")
    token = input("Token: ").strip()

    if not token:
        print("Cancelado.")
        return None

    if not re.match(r"^\d+:[A-Za-z0-9_\-]+$", token):
        print("Formato de token invalido. Deve ser: 123456:ABCdef...")
        return None

    env["LUX_TELEGRAM_TOKEN"] = token
    _write_env(env)
    print("✅ Telegram configurado! Token salvo no .env")
    print("   Para ativar, reinicie o Lux com o gateway:")
    print("   lux --gateway")
    return token


# ── Discord Wizard ────────────────────────────────────────────────────────

DISCORD_SETUP_GUIDE = """
╔══════════════════════════════════════════════════════╗
║          🎮 Configurar Discord                      ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  Passo 1: Acesse https://discord.com/developers      ║
║  Passo 2: Clique em "New Application"                ║
║  Passo 3: De um nome (ex: Lux) e clique Create       ║
║  Passo 4: Va em Bot > Add Bot > Reset Token          ║
║  Passo 5: Copie o token gerado                       ║
║  Passo 6: Em OAuth2 > URL Generator:                 ║
║           - Scopes: bot + applications.commands       ║
║           - Permissions: Send Messages + Read History ║
║           - Abra a URL gerada para convidar o bot     ║
║  Passo 7: Cole o token abaixo                        ║
║                                                      ║
║  IMPORTANTE: Ative Message Content Intent:            ║
║  Bot > Privileged Gateway Intents > Message Content   ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
"""


def setup_discord() -> Optional[str]:
    print(DISCORD_SETUP_GUIDE)

    env = _read_env()
    current = env.get("LUX_DISCORD_TOKEN", "")

    if current:
        print(f"Token atual: {_mask_token(current)}")
        print()
        print("[1] Manter token atual")
        print("[2] Substituir token")
        print("[3] Remover (desconectar Discord)")
        choice = input("Opcao [1]: ").strip() or "1"

        match choice:
            case "1":
                print("Token mantido.")
                return current
            case "2":
                pass
            case "3":
                env["LUX_DISCORD_TOKEN"] = ""
                _write_env(env)
                print("✅ Discord desconectado. Token removido do .env")
                return None
            case _:
                return current

    print("Cole o token do Discord Developer Portal (ou Enter para cancelar):")
    token = input("Token: ").strip()

    if not token:
        print("Cancelado.")
        return None

    if not token.startswith("M") and not token.startswith("O"):
        print("Aviso: tokens do Discord geralmente comecam com 'M' ou 'O'.")
        confirm = input("Continuar mesmo assim? [s/N]: ").strip().lower()
        if confirm != "s":
            return None

    env["LUX_DISCORD_TOKEN"] = token
    _write_env(env)
    print("✅ Discord configurado! Token salvo no .env")
    print("   IMPORTANTE: Ative 'Message Content Intent' no Developer Portal!")
    print("   Bot > Privileged Gateway Intents > Message Content Intent = ON")
    print()
    print("   Para ativar, reinicie o Lux com o gateway:")
    print("   lux --gateway")
    return token


# ── Gateway Status ────────────────────────────────────────────────────────


def gateway_status() -> str:
    env = _read_env()
    lines = ["╔════════════════════════════════════════╗"]
    lines.append("║        📡 Gateway Status               ║")
    lines.append("╠════════════════════════════════════════╣")

    tg = env.get("LUX_TELEGRAM_TOKEN", "")
    dc = env.get("LUX_DISCORD_TOKEN", "")

    if tg:
        lines.append(f"║  📱 Telegram : ✅ {_mask_token(tg):24s} ║")
    else:
        lines.append(f"║  📱 Telegram : ❌ nao configurado       ║")

    if dc:
        lines.append(f"║  🎮 Discord  : ✅ {_mask_token(dc):24s} ║")
    else:
        lines.append(f"║  🎮 Discord  : ❌ nao configurado       ║")

    lines.append("╠════════════════════════════════════════╣")
    lines.append("║  Comandos:                             ║")
    lines.append("║  /gateway setup telegram               ║")
    lines.append("║  /gateway setup discord                ║")
    lines.append("║  /gateway disconnect <plataforma>      ║")
    lines.append("╚════════════════════════════════════════╝")
    return "\n".join(lines)


def gateway_disconnect(platform: str) -> str:
    platform = platform.lower()
    key = {"telegram": "LUX_TELEGRAM_TOKEN", "discord": "LUX_DISCORD_TOKEN"}.get(platform)

    if not key:
        return f"Plataforma desconhecida: {platform}. Use: telegram, discord"

    env = _read_env()
    if not env.get(key):
        return f"{platform} ja esta desconectado."

    env[key] = ""
    _write_env(env)
    return f"✅ {platform} desconectado. Token removido do .env"
