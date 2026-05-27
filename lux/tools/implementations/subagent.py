# lux/tools/implementations/subagent.py
import asyncio
import logging
from uuid import uuid4

from lux.agent.state import AgentState, SubagentTask, TodoItem, ToolResult
from lux.tools.base import Tool

logger = logging.getLogger(__name__)


class DelegateTaskTool(Tool):
    name = "delegate_task"
    description = "Cria um subagente isolado para executar uma tarefa em paralelo"
    timeout_seconds = 300
    parameters_schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Descricao da tarefa para o subagente"},
            "context": {"type": "string", "description": "Contexto adicional (nao passa historico completo)"},
            "toolsets": {"type": "array", "items": {"type": "string"}, "description": "Toolsets disponiveis"},
            "max_iterations": {"type": "integer", "description": "Budget maximo de iteracoes", "default": 10},
        },
        "required": ["task"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._async_execute(args, state))

    async def _async_execute(self, args: dict, state: AgentState) -> ToolResult:
        from lux.agent.agent import AIAgent

        task = args.get("task", "")
        toolsets = args.get("toolsets", [])
        sub_max = min(args.get("max_iterations", 10), state.max_iterations - state.iteration)
        if sub_max <= 0:
            return ToolResult.failure("Budget esgotado — nao e possivel delegar.")

        sub_task = SubagentTask(
            task=task,
            toolsets=toolsets,
            max_iterations=sub_max,
            parent_task_id=state.task_id,
            user_id=state.user_id,
            status="running",
        )
        state.subagent_tasks.append(sub_task)

        try:
            subagent = AIAgent(
                user_id=state.user_id,
                session_id=f"{state.session_id}_sub_{uuid4().hex[:8]}",
                user_profile=state.user_profile,
                is_subagent=True,
                parent_task_id=state.task_id,
                max_iterations=sub_max,
                compression_threshold=0.85,
                enabled_toolsets=toolsets,
                memory_manager=None,
            )

            result = await subagent.run_conversation(
                user_message=task,
                system_message=args.get("context", ""),
            )

            await subagent.close()
            sub_task.status = "completed"
            sub_task.result = result.final_response
            sub_task.iterations_used = result.iterations_used

            return ToolResult(
                success=result.status.value != "error",
                output=result.final_response[:2000],
                data={
                    "iterations_used": result.iterations_used,
                    "subagent_id": sub_task.id,
                },
                side_effects=[
                    f"Subagente executou {result.iterations_used} iteracoes para: {task[:100]}"
                ],
            )
        except Exception as e:
            sub_task.status = "failed"
            sub_task.error = str(e)
            logger.exception("Subagente falhou")
            return ToolResult.failure(f"Subagente falhou: {e}")


class TodoTool(Tool):
    name = "todo"
    description = "Lista de tarefas local do agente (nao persiste entre sessoes)"
    parameters_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "complete", "list", "clear"]},
            "item": {"type": "string", "description": "Descricao da tarefa (add)"},
            "item_id": {"type": "integer", "description": "ID da tarefa (complete)"},
        },
        "required": ["action"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        action = args.get("action", "list")
        todos = state.agent_todos

        match action:
            case "add":
                item_text = args.get("item", "")
                if not item_text.strip():
                    return ToolResult.failure("Descricao da tarefa vazia.")
                item = TodoItem(id=len(todos) + 1, text=item_text.strip())
                todos.append(item)
                return ToolResult.ok(f"[{item.id}] {item.text} adicionado.")

            case "complete":
                item_id = args.get("item_id", 0)
                item = next((t for t in todos if t.id == item_id), None)
                if not item:
                    return ToolResult.failure(f"Item {item_id} nao encontrado.")
                item.done = True
                return ToolResult.ok(f"[{item.id}] Marcado como concluido.")

            case "list":
                if not todos:
                    return ToolResult.ok("Lista vazia.")
                lines = [
                    f"{'✓' if t.done else '○'} [{t.id}] {t.text}" for t in todos
                ]
                return ToolResult.ok("\n".join(lines))

            case "clear":
                count = len(todos)
                todos.clear()
                return ToolResult.ok(f"{count} itens removidos.")

            case _:
                return ToolResult.failure(f"Acao desconhecida: {action}")
