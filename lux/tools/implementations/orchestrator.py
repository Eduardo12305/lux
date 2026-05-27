# lux/tools/implementations/orchestrator.py
# Módulo: Tools
# Dependências: orchestrator/task_manager.py, agent/state.py
# Status: IMPLEMENTADO

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from lux.agent.state import AgentState, ToolResult, UserRole
from lux.orchestrator.models import TaskPriority
from lux.orchestrator.task_manager import TaskOrchestrator
from lux.tools.base import Tool

logger = logging.getLogger(__name__)

_orchestrator: Optional[TaskOrchestrator] = None


def get_orchestrator() -> TaskOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = TaskOrchestrator()
    return _orchestrator


class RunTaskTool(Tool):
    name = "run_task"
    description = "Submete tarefa para execucao paralela com controle de dependencias. Use para rodar multiplas tarefas ao mesmo tempo."
    timeout_seconds = 30
    parameters_schema = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Descricao da tarefa para o subagente"},
            "priority": {"type": "string", "enum": ["urgent", "normal", "background"], "default": "normal"},
            "depends_on": {"type": "array", "items": {"type": "string"}, "description": "IDs de outras run_task que precisam terminar antes"},
            "toolsets": {"type": "array", "items": {"type": "string"}, "description": "Toolsets que o subagente pode usar"},
        },
        "required": ["description"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args, state))

    async def _async_execute(self, args: dict, state: AgentState) -> ToolResult:
        desc = args.get("description", "").strip()
        if not desc:
            return ToolResult.failure("Descricao da tarefa obrigatoria.")

        priority_str = args.get("priority", "normal")
        try:
            priority = TaskPriority(priority_str)
        except ValueError:
            return ToolResult.failure(f"Prioridade invalida: {priority_str}")

        deps = args.get("depends_on", [])
        toolsets = args.get("toolsets", [])

        orch = get_orchestrator()

        try:
            task = await orch.submit(
                description=desc,
                user_id=state.user_id,
                user_profile=state.user_profile,
                priority=priority,
                dependencies=deps,
                toolsets=toolsets,
            )
            return ToolResult(
                success=True,
                output=(
                    f"Tarefa submetida: [{task.id[:8]}] {desc[:120]}\n"
                    f"  Status: {task.status.value}\n"
                    f"  Prioridade: {task.priority.value}\n"
                    f"  {'Aguardando dependencias' if task.dependencies else 'Na fila para execucao'}"
                ),
                data={"task_id": task.id, "status": task.status.value},
            )
        except RuntimeError as e:
            return ToolResult.failure(str(e))


class OrchestratorStatusTool(Tool):
    name = "orchestrator_status"
    description = "Mostra status de todas as tarefas em andamento, fila e concluidas"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        orch = get_orchestrator()
        status = orch.get_status()

        lines = ["╔════════════════════════════════════════╗"]
        lines.append("║        📋 Orquestrador de Tarefas       ║")
        lines.append("╠════════════════════════════════════════╣")

        if status.running:
            lines.append("║  🟢 EM EXECUCAO:")
            for t in status.running:
                lines.append(f"║    [{t.id[:8]}] {t.description[:60]}")
        else:
            lines.append("║  🟢 EM EXECUCAO: (nenhuma)")

        if status.queued:
            lines.append("║  🟡 NA FILA:")
            for t in status.queued:
                lines.append(f"║    [{t.id[:8]}] {t.description[:60]}")
        else:
            lines.append("║  🟡 NA FILA: (nenhuma)")

        if status.waiting:
            lines.append("║  🔵 AGUARDANDO:")
            for t in status.waiting:
                deps = ", ".join(d[:8] for d in t.dependencies)
                lines.append(f"║    [{t.id[:8]}] {t.description[:60]}")
                lines.append(f"║      Depende de: {deps}")
        else:
            lines.append("║  🔵 AGUARDANDO: (nenhuma)")

        lines.append("╠════════════════════════════════════════╣")
        if status.completed_today:
            lines.append(f"║  CONCLUIDAS HOJE: {len(status.completed_today)}")
            for t in status.completed_today[:5]:
                icon = "✅" if t.status.value == "completed" else "❌"
                lines.append(f"║  {icon} [{t.id[:8]}] {t.description[:50]}")
        else:
            lines.append("║  CONCLUIDAS HOJE: (nenhuma)")

        lines.append(f"║  Slots: {status.active_count}/{status.max_concurrent}")
        lines.append("╚════════════════════════════════════════╝")
        return ToolResult.ok("\n".join(lines))


class OrchestratorCancelTool(Tool):
    name = "orchestrator_cancel"
    description = "Cancela uma tarefa submetida por ID"
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID da tarefa (8 primeiros caracteres)"},
        },
        "required": ["task_id"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        task_id = args["task_id"]
        orch = get_orchestrator()

        full_id = None
        for tid in orch._tasks:
            if tid.startswith(task_id):
                full_id = tid
                break

        if not full_id:
            return ToolResult.failure(f"Tarefa '{task_id}' nao encontrada.")

        if await orch.cancel(full_id):
            return ToolResult.ok(f"Tarefa [{task_id}] cancelada.")
        return ToolResult.failure(f"Tarefa [{task_id}] ja estava concluida.")
