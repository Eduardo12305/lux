# lux/tools/implementations/tasks.py
from pathlib import Path
from datetime import datetime
from lux.agent.state import AgentState, ToolResult
from lux.constants import LUX_HOME
from lux.tools.base import Tool

TASKS_DIR = LUX_HOME / "tasks"
TASKS_FILE = TASKS_DIR / "TODO.md"


def _ensure_tasks_dir():
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    if not TASKS_FILE.exists():
        TASKS_FILE.write_text("# Tarefas\n\n## Pendentes\n\n## Concluidas\n")


def _read_tasks() -> list[str]:
    _ensure_tasks_dir()
    return TASKS_FILE.read_text().split("\n")


def _write_tasks(lines: list[str]):
    TASKS_FILE.write_text("\n".join(lines))


def _next_id(lines: list[str]) -> int:
    max_id = 0
    for line in lines:
        if "[#" in line and "]" in line:
            try:
                num = int(line.split("[#")[1].split("]")[0])
                max_id = max(max_id, num)
            except (ValueError, IndexError):
                pass
    return max_id + 1


class TaskCreateTool(Tool):
    name = "task_create"
    description = "Cria uma nova tarefa no TODO.md local"
    parameters_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Descricao da tarefa"},
        },
        "required": ["content"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        content = args.get("content", "").strip()
        if not content:
            return ToolResult.failure("Conteudo da tarefa vazio.")

        lines = _read_tasks()
        tid = _next_id(lines)
        task_line = f"- [ ] [#{tid}] {content}"

        inserted = False
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if not inserted and line.strip() == "## Pendentes":
                new_lines.append(task_line)
                inserted = True
        if not inserted:
            new_lines.append(task_line)
        _write_tasks(new_lines)
        return ToolResult.ok(f"[#{tid}] {content}")


class TaskListTool(Tool):
    name = "task_list"
    description = "Lista todas as tarefas"
    parameters_schema = {
        "type": "object",
        "properties": {
            "filter": {"type": "string", "description": "pending|completed|all", "default": "all"},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        filt = args.get("filter", "all")
        lines = _read_tasks()
        result = []
        in_section = False
        for line in lines:
            if line.startswith("## "):
                in_section = True
                result.append(line)
                continue
            if line.startswith("- [x]") and filt in ("completed", "all"):
                result.append(line)
            elif line.startswith("- [ ]") and filt in ("pending", "all"):
                result.append(line)
        return ToolResult.ok("\n".join(result) if len(result) > 2 else "Nenhuma tarefa.")


class TaskCompleteTool(Tool):
    name = "task_complete"
    description = "Marca uma tarefa como concluida"
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "ID da tarefa"},
        },
        "required": ["task_id"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        tid = args.get("task_id", 0)
        lines = _read_tasks()
        found = False
        new_lines = []
        for line in lines:
            if f"[#{tid}]" in line and line.strip().startswith("- [ ]"):
                new_lines.append(line.replace("- [ ]", "- [x]", 1))
                found = True
            else:
                new_lines.append(line)
        if not found:
            return ToolResult.failure(f"Tarefa [#{tid}] nao encontrada ou ja concluida.")
        _write_tasks(new_lines)
        return ToolResult.ok(f"[#{tid}] Marcada como concluida.")


class TaskUpdateTool(Tool):
    name = "task_update"
    description = "Atualiza a descricao de uma tarefa"
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "description": "ID da tarefa"},
            "content": {"type": "string", "description": "Nova descricao"},
        },
        "required": ["task_id", "content"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        tid = args.get("task_id", 0)
        content = args.get("content", "")
        lines = _read_tasks()
        found = False
        new_lines = []
        for line in lines:
            if f"[#{tid}]" in line:
                prefix = line.split(f"[#{tid}]")[0]
                new_lines.append(f"{prefix}[#{tid}] {content}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            return ToolResult.failure(f"Tarefa [#{tid}] nao encontrada.")
        _write_tasks(new_lines)
        return ToolResult.ok(f"[#{tid}] Atualizada.")
