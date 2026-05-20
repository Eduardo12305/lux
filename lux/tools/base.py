# lux/tools/base.py
# Módulo: Tools
# Dependências: agent/state.py
# Status: IMPLEMENTADO

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from lux.agent.state import AgentState, ToolResult


class Tool(ABC):
    name: str = ""
    description: str = ""
    timeout_seconds: int = 30

    @abstractmethod
    def execute(self, args: dict, state: AgentState) -> ToolResult:
        ...

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": getattr(self, "parameters_schema", {"type": "object", "properties": {}}),
            },
        }
