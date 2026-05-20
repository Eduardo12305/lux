# lux/tools/registry.py
# Módulo: Tools
# Dependências: tools/base.py, tools/toolsets.py, agent/state.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
from typing import Optional

from lux.agent.state import AgentState, ToolResult, UserProfile
from lux.tools.base import Tool
from lux.tools.toolsets import TOOLSETS, Toolset

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry central de ferramentas com discovery, schema e dispatch."""

    def __init__(self):
        self._registry: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._registry[tool.name] = tool
        logger.debug("Ferramenta registrada: %s", tool.name)

    def get(self, name: str) -> Optional[Tool]:
        return self._registry.get(name)

    def get_active_schemas(
        self,
        user: UserProfile,
        toolsets: list[str],
    ) -> list[dict]:
        active: list[dict] = []
        for toolset_name in toolsets:
            toolset = TOOLSETS.get(toolset_name)
            if not toolset:
                continue
            if not self._user_can_use_toolset(user, toolset):
                continue
            for tool_name in toolset.tools:
                tool = self._registry.get(tool_name)
                if tool:
                    active.append(tool.to_openai_schema())
        return active

    def execute(self, name: str, args: dict, state: AgentState) -> ToolResult:
        tool = self._registry.get(name)
        if not tool:
            return ToolResult.failure(
                f"Ferramenta '{name}' nao encontrada. "
                f"Disponiveis: {', '.join(self._registry.keys())}"
            )
        try:
            return tool.execute(args, state)
        except TimeoutError:
            return ToolResult.timed_out(name, tool.timeout_seconds)
        except Exception as e:
            logger.error("Tool %s falhou: %s", name, e, exc_info=True)
            return ToolResult.failure(str(e))

    def _user_can_use_toolset(self, user: UserProfile, toolset: Toolset) -> bool:
        user_role_order = {"admin": 3, "user": 2, "guest": 1}
        return user_role_order.get(user.role.value, 0) >= user_role_order.get(
            toolset.min_role.value, 0
        )
