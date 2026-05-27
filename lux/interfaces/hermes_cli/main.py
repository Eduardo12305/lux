# lux/interfaces/hermes_cli/main.py
# Módulo: Interfaces
# Dependências: agent/agent.py, interfaces/cli.py
# Status: IMPLEMENTADO
# Notas: Entry point para CLI — Textual TUI se disponivel, fallback para input().

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

from lux.agent.agent import AIAgent
from lux.agent.state import Channel, UserProfile
from lux.config import get_config
from lux.gateway.auth import AuthManager
from lux.interfaces.hermes_cli.auth import AuthCommands
from lux.memory.manager import MemoryManager
from lux.models.llama_client import LlamaClient
from lux.models.manager import ModelManager
from lux.prompt.assembler import PromptAssembler
from lux.prompt.soul import SoulLoader
from lux.skills.manager import SkillManager
from lux.tools.approval import ApprovalSystem
from lux.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


async def run_tui(
    agent: AIAgent,
    user_profile: UserProfile,
    work_context: Optional[str] = None,
):
    """Inicia a TUI Textual."""
    from lux.interfaces.cli import LuxTUI
    app = LuxTUI(
        agent=agent,
        user_name=user_profile.display_name or user_profile.username,
        user_profile=user_profile,
        work_context=work_context,
    )
    await app.run_async()


def has_textual() -> bool:
    try:
        import textual
        return True
    except ImportError:
        return False
