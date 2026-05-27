# lux/plugins/base.py
# Módulo: Plugins
# Dependências: agent/state.py
# Status: IMPLEMENTADO
# Notas: Plugin ABC com todos os hooks. Plugins herdam desta classe.

from __future__ import annotations

from abc import ABC
from typing import Optional

from lux.agent.state import AgentState, ToolResult


class LuxPlugin(ABC):
    """Base para plugins do Lux. Sobrescreva os hooks que precisar."""

    name: str = "unnamed"
    version: str = "1.0.0"
    description: str = ""

    # ── Tool Hooks ──────────────────────────────────────────────────────

    def pre_tool_call(
        self, tool_name: str, args: dict, state: AgentState
    ) -> Optional[ToolResult]:
        """
        Executado ANTES de cada tool call.
        Se retornar ToolResult, a tool real é CANCELADA e este resultado é usado.
        Se retornar None, a tool executa normalmente.
        """
        return None

    def post_tool_call(
        self, tool_name: str, args: dict, result: ToolResult, state: AgentState
    ) -> None:
        """Executado APÓS cada tool call (bem-sucedida ou não)."""
        pass

    # ── LLM Hooks ───────────────────────────────────────────────────────

    def pre_llm_call(
        self, messages: list[dict], state: AgentState
    ) -> Optional[list[dict]]:
        """
        Executado ANTES de cada chamada ao LLM.
        Pode modificar ou substituir as mensagens.
        Se retornar None, usa as mensagens originais.
        """
        return None

    def post_llm_call(
        self, response: dict, state: AgentState
    ) -> None:
        """Executado APÓS cada resposta do LLM."""
        pass

    # ── Session Hooks ───────────────────────────────────────────────────

    def on_session_start(self, state: AgentState) -> None:
        """Executado ao iniciar uma sessão."""
        pass

    def on_session_end(self, state: AgentState) -> None:
        """Executado ao encerrar uma sessão."""
        pass

    # ── Memory Hooks ────────────────────────────────────────────────────

    def on_memory_write(
        self, action: str, target: str, content: str, user_id: str
    ) -> None:
        """Executado ao persistir uma memória."""
        pass
