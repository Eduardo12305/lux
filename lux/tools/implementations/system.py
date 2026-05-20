# lux/tools/implementations/system.py
from lux.agent.state import AgentState, ToolResult
from lux.tools.base import Tool


class StatusCheckTool(Tool):
    name = "status_check"
    description = "Verifica status do sistema Lux (VRAM, modelos, uptime)"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        info = [
            f"Sessao: {state.session_id[:8]}...",
        ]
        return ToolResult.ok("\n".join(info))
