# lux/tools/implementations/memory_tools.py
import asyncio
from lux.agent.state import (
    AgentState, MemoryAction, MemoryTarget, ToolResult,
)
from lux.tools.base import Tool


class MemoryTool(Tool):
    name = "memory"
    description = "Gerencia memoria persistente (add/replace/remove entradas)"
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "replace", "remove"]},
            "target": {"type": "string", "enum": ["memory", "user"]},
            "content": {"type": "string", "description": "Conteudo para add/replace"},
            "old_text": {"type": "string", "description": "Texto antigo para replace/remove"},
        },
        "required": ["action", "target"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return ToolResult.ok("Use o gerenciador de memoria do agente")


class SessionSearchTool(Tool):
    name = "session_search"
    description = "Busca em sessoes passadas via FTS5"
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Termo de busca"},
            "limit": {"type": "integer", "description": "Max resultados", "default": 5},
        },
        "required": ["query"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return ToolResult.ok("Use o gerenciador de sessao do agente")
