# lux/tools/implementations/filesystem.py
from pathlib import Path
from lux.agent.state import AgentState, ToolResult
from lux.tools.base import Tool


class FileReadTool(Tool):
    name = "file_read"
    description = "Le o conteudo de um arquivo"
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho do arquivo"},
        },
        "required": ["path"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        path = Path(args["path"]).expanduser()
        try:
            return ToolResult.ok(path.read_text())
        except Exception as e:
            return ToolResult.failure(str(e))


class FileWriteTool(Tool):
    name = "file_write"
    description = "Escreve conteudo em um arquivo (sobrescreve)"
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho do arquivo"},
            "content": {"type": "string", "description": "Conteudo a escrever"},
        },
        "required": ["path", "content"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        path = Path(args["path"]).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"])
            return ToolResult.ok(f"Arquivo salvo: {path}")
        except Exception as e:
            return ToolResult.failure(str(e))
