# lux/tools/implementations/terminal.py
from lux.agent.state import AgentState, ToolResult
from lux.tools.base import Tool


class ShellRunTool(Tool):
    name = "shell_run"
    description = "Executa um comando shell no terminal"
    timeout_seconds = 60
    parameters_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Comando shell a executar"},
            "working_dir": {"type": "string", "description": "Diretorio de trabalho"},
            "timeout_seconds": {"type": "integer", "description": "Timeout em segundos", "default": 30},
        },
        "required": ["command"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        import subprocess
        cmd = args.get("command", "")
        wd = args.get("working_dir", None)
        timeout = args.get("timeout_seconds", 30)
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                cwd=wd, timeout=timeout,
            )
            output = result.stdout.strip() or result.stderr.strip() or "(sem saida)"
            return ToolResult.ok(output)
        except subprocess.TimeoutExpired:
            return ToolResult.timed_out(self.name, timeout)
        except Exception as e:
            return ToolResult.failure(str(e))
