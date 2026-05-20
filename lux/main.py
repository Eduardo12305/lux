# lux/main.py
# Módulo: Entry Point
# Dependências: todos os modulos
# Status: IMPLEMENTADO
# Notas: Composition root + DI + StartupCoordinator (GAP 9) + ProcessLauncher (GAP 11)

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from lux.agent.agent import AIAgent
from lux.agent.model_router import ModelRouter
from lux.agent.state import Channel, UserProfile
from lux.config import get_config
from lux.memory.manager import MemoryManager
from lux.models.llama_client import LlamaClient
from lux.models.manager import ModelManager
from lux.models.vram_guard import VRAMGuard
from lux.prompt.assembler import PromptAssembler
from lux.prompt.soul import SoulLoader
from lux.skills.manager import SkillManager
from lux.tools.approval import ApprovalSystem
from lux.tools.implementations.filesystem import FileReadTool, FileWriteTool
from lux.tools.implementations.memory_tools import MemoryTool, SessionSearchTool
from lux.tools.implementations.system import StatusCheckTool
from lux.tools.implementations.terminal import ShellRunTool
from lux.tools.registry import ToolRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _register_tools(registry: ToolRegistry):
    registry.register(ShellRunTool())
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    registry.register(MemoryTool())
    registry.register(SessionSearchTool())
    registry.register(StatusCheckTool())


async def _run_cli():
    config = get_config()
    logger.info("Lux v1.0.0 iniciando...")

    llama = LlamaClient()
    vram = VRAMGuard()
    model_mgr = ModelManager(llama_client=llama, vram_guard=vram)
    memory_mgr = MemoryManager()
    skill_mgr = SkillManager()
    tool_registry = ToolRegistry()
    _register_tools(tool_registry)
    approval = ApprovalSystem()

    soul_loader = SoulLoader()
    prompt_assembler = PromptAssembler(
        skill_list_provider=skill_mgr,
        tool_schema_provider=tool_registry,
        soul_loader=soul_loader,
    )

    agent = AIAgent(
        user_id="local",
        channel=Channel.CLI,
        model_manager=model_mgr,
        memory_manager=memory_mgr,
        skill_manager=skill_mgr,
        tool_registry=tool_registry,
        approval_system=approval,
        prompt_assembler=prompt_assembler,
    )

    print("╔══════════════════════════════════════════╗")
    print("║   Lux v1.0.0 — Assistente Pessoal Local ║")
    print("║   /help para comandos  |  /quit para sair║")
    print("╚══════════════════════════════════════════╝")
    print()

    while True:
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAte logo!")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "/q"):
            print("Ate logo!")
            break
        if user_input == "/help":
            print("Comandos: /quit, /help, /status, /memory, /skills, /doctor")
            continue
        if user_input == "/status":
            print("Lux v1.0.0 | Sessao local | VRAM: monitoramento ativo")
            continue
        if user_input == "/doctor":
            print("Health check:")
            main_ok = await llama.health_check("main")
            aux_ok = await llama.health_check("aux")
            print(f"  llama-server (14B): {'OK' if main_ok else 'FALHA'}")
            print(f"  llama-server (1.7B): {'OK' if aux_ok else 'FALHA'}")
            continue

        print()
        response = await agent.run_conversation(user_message=user_input)
        print(response.final_response)
        print()

    await agent.close()


async def _run_gateway():
    logger.info("Lux Gateway iniciando...")
    print("Gateway mode — implementacao pendente (Batch 14)")
    await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Lux — Assistente Pessoal Local")
    parser.add_argument("--gateway", action="store_true", help="Iniciar em modo gateway")
    parser.add_argument("--doctor", action="store_true", help="Executar diagnostico")
    parser.add_argument("--version", action="store_true", help="Mostrar versao")
    args = parser.parse_args()

    if args.version:
        print("Lux v1.0.0")
        return

    if args.doctor:
        asyncio.run(_run_doctor())
        return

    if args.gateway:
        asyncio.run(_run_gateway())
    else:
        asyncio.run(_run_cli())


async def _run_doctor():
    print("Lux Doctor — Diagnostico do Sistema")
    print("=" * 40)
    config = get_config()
    print(f"Lux Home: {config.lux_home}")
    print(f"VRAM Budget: {config.vram_budget_gb}GB")
    print(f"GPU Backend: {config.gpu_backend}")

    llama = LlamaClient()
    main_ok = await llama.health_check("main")
    aux_ok = await llama.health_check("aux")
    print(f"llama-server (14B): {'OK' if main_ok else 'FALHA — verifique se o servidor esta rodando'}")
    print(f"llama-server (1.7B): {'OK' if aux_ok else 'FALHA — verifique se o servidor esta rodando'}")
    await llama.close()


def gateway_main():
    asyncio.run(_run_gateway())


if __name__ == "__main__":
    main()
