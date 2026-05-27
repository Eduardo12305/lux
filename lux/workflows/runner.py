# lux/workflows/runner.py
# Módulo: Workflow Engine — Runner + EventBus
# Dependências: parser.py, cron/scheduler.py, skills/manager.py, memory/manager.py
# Status: IMPLEMENTADO
# Notas: Executor de workflows com EventBus para triggers.
#   Integra com o plano_agente_inteligente.md — Módulo 3.

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from lux.config import get_config
from lux.constants import LUX_HOME
from lux.workflows.parser import (
    TriggerType,
    WorkflowDefinition,
    WorkflowParser,
)

logger = logging.getLogger(__name__)

EXECUTION_LOG_PATH = LUX_HOME / "workflows" / "execution_log.json"


@dataclass
class ExecutionLog:
    workflow_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    status: str = "pending"
    step_results: list[dict] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "step_results": self.step_results,
            "error": self.error,
        }


class EventBus:
    """Barramento de eventos para triggers de workflow."""

    def __init__(self):
        self._listeners: dict[TriggerType, list[Callable]] = {
            t: [] for t in TriggerType
        }

    def on(self, trigger_type: TriggerType, callback: Callable):
        self._listeners[trigger_type].append(callback)

    async def emit(self, trigger_type: TriggerType, **event_data):
        for callback in self._listeners.get(trigger_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_data)
                else:
                    callback(event_data)
            except Exception:
                logger.exception(
                    "Erro no listener de evento %s", trigger_type.value
                )

    def clear(self):
        for t in TriggerType:
            self._listeners[t].clear()


class WorkflowRunner:
    """Executor de workflows: carrega, agenda e executa cadeias de skills."""

    def __init__(
        self,
        parser: Optional[WorkflowParser] = None,
        event_bus: Optional[EventBus] = None,
    ):
        config = get_config()
        self._parser = parser or WorkflowParser()
        self._bus = event_bus or EventBus()
        self._enabled = config.workflows_enabled
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._agent = None
        self._memory_manager = None
        self._cron_scheduler = None
        self._execution_history: list[ExecutionLog] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def set_agent(self, agent):
        self._agent = agent

    def set_memory_manager(self, memory_manager):
        self._memory_manager = memory_manager

    def set_cron_scheduler(self, scheduler):
        self._cron_scheduler = scheduler

    async def start(self):
        if not self._enabled:
            logger.info("WorkflowRunner desabilitado")
            return

        self._running = True
        self._workflows = {}
        self._load_execution_history()

        for wf in self._parser.discover():
            if wf.enabled:
                self._workflows[wf.id] = wf

        self._register_builtin_handlers()
        logger.info("WorkflowRunner iniciado: %d workflows", len(self._workflows))

        for wf in self._workflows.values():
            await self._schedule_workflow(wf)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        self._bus.clear()

    async def reload(self):
        self._workflows.clear()
        for wf in self._parser.discover():
            if wf.enabled:
                self._workflows[wf.id] = wf
        logger.info("Workflows recarregados: %d", len(self._workflows))

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[WorkflowDefinition]:
        return list(self._workflows.values())

    async def execute_workflow(self, wf: WorkflowDefinition, context: dict | None = None):
        log = ExecutionLog(
            workflow_id=wf.id,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )

        logger.info("Executando workflow: %s (%d etapas)", wf.nome, len(wf.steps))
        step_output = context or {}

        for i, step in enumerate(wf.steps):
            step_log = {"step": i, "skill": step.skill, "status": "ok"}
            try:
                result = await self._execute_step(step, step_output)
                step_log["result"] = str(result)[:500]
                step_output[f"step_{i}_output"] = result
            except Exception as e:
                step_log["status"] = "error"
                step_log["error"] = str(e)
                logger.warning("Workflow %s — etapa %d falhou: %s", wf.id, i, e)
                if not self._should_continue_on_error(step):
                    log.status = "error"
                    log.error = str(e)
                    break

            log.step_results.append(step_log)

        if log.status == "running":
            log.status = "completed"
        log.finished_at = datetime.now(timezone.utc).isoformat()

        await self._save_result(wf, log, step_output)
        self._execution_history.append(log)
        self._save_execution_history()

        logger.info("Workflow %s: %s", wf.id, log.status)
        return log

    async def _execute_step(self, step, context: dict) -> str:
        skill_name = step.skill
        config = step.config

        if self._agent and hasattr(self._agent, 'run_conversation'):
            prompt = self._build_step_prompt(skill_name, config, context)
            try:
                result = await asyncio.wait_for(
                    self._agent.run_conversation(user_message=prompt),
                    timeout=120.0,
                )
                return result.final_response
            except asyncio.TimeoutError:
                return f"[timeout] {skill_name}"
            except Exception as e:
                logger.warning("Skill %s falhou: %s", skill_name, e)
                raise

        if skill_name == "web_search":
            return await self._execute_web_search(config)
        elif skill_name == "file_summarizer":
            return await self._execute_file_summarizer(config)
        elif skill_name == "email_summarizer":
            return await self._execute_email_summarizer(config)
        elif skill_name == "save_to_memory":
            return await self._execute_save_to_memory(config, context)
        elif skill_name == "notify_user":
            return self._execute_notify_user(config)
        elif skill_name == "content_summarizer":
            return self._execute_content_summarizer(config, context)
        elif skill_name == "index_to_memory":
            return await self._execute_index_to_memory(config, context)
        else:
            return f"[skill não implementada: {skill_name}]"

    def _build_step_prompt(self, skill: str, config: dict, context: dict) -> str:
        parts = [f"Execute a skill '{skill}' com a seguinte configuração:"]
        if config:
            parts.append(json.dumps(config, ensure_ascii=False, indent=2))
        if context:
            relevant = {k: v for k, v in context.items()
                        if isinstance(v, (str, int, float, bool))}
            if relevant:
                parts.append("\nContexto da execução anterior:")
                parts.append(json.dumps(relevant, ensure_ascii=False, indent=2))
        return "\n".join(parts)

    async def _execute_web_search(self, config: dict) -> str:
        query = config.get("query", "")
        max_results = config.get("max_resultados", config.get("max_results", 5))
        fontes = config.get("fontes", config.get("sources", []))
        source_filter = " ".join(f"site:{s}" for s in fontes) if fontes else ""
        full_query = f"{query} {source_filter}".strip()

        if self._agent:
            try:
                result = await self._agent.run_conversation(
                    user_message=f"Busque na web: {full_query}. "
                                 f"Retorne os {max_results} resultados mais relevantes."
                )
                return result.final_response
            except Exception:
                pass
        return f"[busca web indisponível: {full_query}]"

    async def _execute_file_summarizer(self, config: dict) -> str:
        path = config.get("path", config.get("caminho", ""))
        if path:
            try:
                content = Path(path).expanduser().read_text(errors="replace")[:3000]
                return f"Arquivo: {Path(path).name}\n\n{content}"
            except Exception as e:
                return f"[erro ao ler arquivo: {e}]"
        return "[caminho não especificado]"

    async def _execute_email_summarizer(self, config: dict) -> str:
        limit = config.get("limit", config.get("limite", 10))
        try:
            from lux.tools.implementations.email_classifier import EmailClassifier
            classifier = EmailClassifier()
            entries = classifier.index.entries[:limit]
            if not entries:
                return "Nenhum e-mail no índice."
            lines = [f"Resumo dos últimos {len(entries)} e-mails:"]
            for e in entries:
                lines.append(f"  [{e.category}] {e.subject[:80]} — {e.sender}")
            return "\n".join(lines)
        except Exception as e:
            return f"[classificador de e-mail indisponível: {e}]"

    async def _execute_save_to_memory(self, config: dict, context: dict) -> str:
        key = config.get("key", config.get("chave", "workflow_output"))
        ttl_hours = config.get("ttl_horas", config.get("ttl_hours", 24))
        content = json.dumps(
            {k: str(v)[:500] for k, v in context.items()},
            ensure_ascii=False,
        )

        if self._memory_manager:
            try:
                await self._memory_manager.add_memory(
                    key, content,
                    target=f"workflow/{key}",
                    user_id="system",
                )
                return f"Salvo em memória: {key} (TTL: {ttl_hours}h)"
            except Exception as e:
                return f"[erro ao salvar memória: {e}]"

        mem_path = LUX_HOME / "workflows" / "memory"
        mem_path.mkdir(parents=True, exist_ok=True)
        (mem_path / f"{key}.json").write_text(content)
        return f"Salvo em arquivo: {key}"

    def _execute_notify_user(self, config: dict) -> str:
        mensagem = config.get("mensagem",
                               config.get("message", "Workflow concluído."))
        prioridade = config.get("prioridade",
                                 config.get("priority", "normal"))
        formato = config.get("formato", config.get("format", "text"))

        prefix = "🔴 " if prioridade == "alta" else "📰 "
        if formato == "markdown":
            print(f"\n{prefix}**{mensagem}**\n")
        else:
            print(f"\n{prefix}{mensagem}\n")
        return f"Notificação enviada: {mensagem[:100]}"

    def _execute_content_summarizer(self, config: dict, context: dict) -> str:
        max_tokens = config.get("max_tokens", config.get("max_tokens", 300))
        idioma = config.get("idioma", config.get("idioma", "pt-BR"))
        parts = []
        for key, value in context.items():
            if isinstance(value, str) and len(value) > 50:
                parts.append(value)
        combined = "\n\n".join(parts)
        if len(combined) > max_tokens * 4:
            combined = combined[:max_tokens * 4] + "..."
        return f"[Resumo — {idioma} — {len(combined)} chars]:\n{combined[:2000]}"

    async def _execute_index_to_memory(self, config: dict, context: dict) -> str:
        try:
            from lux.tools.implementations.file_watcher import FileIndex
            if self._memory_manager:
                await self._memory_manager.add_memory(
                    "workflow_index",
                    json.dumps(
                        {"context": {k: str(v)[:200] for k, v in context.items()}},
                        ensure_ascii=False,
                    ),
                    target="workflow/index",
                    user_id="system",
                )
            return f"Indexados {len(context)} itens na memória"
        except Exception as e:
            return f"[erro ao indexar: {e}]"

    def _should_continue_on_error(self, step) -> bool:
        return step.config.get("continue_on_error",
                                step.config.get("ignorar_erro", False))

    async def _save_result(self, wf, log, output):
        result_dir = LUX_HOME / "workflows" / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = result_dir / f"{wf.id}_{ts}.json"
        data = {
            "workflow": wf.to_dict(),
            "execution": log.to_dict(),
            "output": {k: str(v)[:1000] for k, v in output.items()},
        }
        result_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _load_execution_history(self):
        if EXECUTION_LOG_PATH.exists():
            try:
                data = json.loads(EXECUTION_LOG_PATH.read_text())
                self._execution_history = [
                    ExecutionLog(
                        workflow_id=e.get("workflow_id", ""),
                        started_at=e.get("started_at", ""),
                        finished_at=e.get("finished_at", ""),
                        status=e.get("status", ""),
                        step_results=e.get("step_results", []),
                        error=e.get("error", ""),
                    )
                    for e in data.get("history", [])[-50:]
                ]
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_execution_history(self):
        EXECUTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "history": [e.to_dict() for e in self._execution_history[-50:]],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        EXECUTION_LOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    async def _schedule_workflow(self, wf: WorkflowDefinition):
        trigger = wf.trigger
        if trigger.type == TriggerType.ON_START:
            if trigger.frequency in ("diaria", "daily"):
                self._bus.on(TriggerType.ON_START, lambda e: asyncio.ensure_future(
                    self._run_if_not_executed_today(wf)
                ))
            else:
                asyncio.create_task(self.execute_workflow(wf))
        elif trigger.type == TriggerType.ON_SCHEDULE:
            if self._cron_scheduler:
                self._schedule_cron_workflow(wf)
        elif trigger.type == TriggerType.ON_FILE_CHANGE:
            self._bus.on(TriggerType.ON_FILE_CHANGE, lambda e: asyncio.ensure_future(
                self._on_file_change(wf, e)
            ))
        elif trigger.type == TriggerType.ON_EMAIL_RECEIVED:
            self._bus.on(TriggerType.ON_EMAIL_RECEIVED, lambda e: asyncio.ensure_future(
                self._on_email_received(wf, e)
            ))

    async def _run_if_not_executed_today(self, wf: WorkflowDefinition):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        already = any(
            e.workflow_id == wf.id and e.started_at[:10] == today
            for e in self._execution_history
            if e.status == "completed"
        )
        if not already:
            await self.execute_workflow(wf)

    def _schedule_cron_workflow(self, wf: WorkflowDefinition):
        try:
            from lux.cron.jobs import CronJob, CronJobStore
            store = CronJobStore()
            trigger = wf.trigger
            schedule = trigger.schedule or "0 8 * * *"
            if trigger.horario and not trigger.schedule:
                parts = trigger.horario.split(":")
                h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                schedule = f"{m} {h} * * *"
            job = CronJob(
                id=f"wf_{wf.id}",
                description=wf.nome,
                schedule=schedule,
                enabled=True,
            )
            store.save(job)
            logger.info("Workflow %s agendado: %s", wf.id, schedule)
        except Exception as e:
            logger.warning("Falha ao agendar workflow %s: %s", wf.id, e)

    async def _on_file_change(self, wf: WorkflowDefinition, event_data: dict):
        directory = wf.trigger.directory
        file_path = event_data.get("path", "")
        if directory and directory not in file_path:
            return
        await self.execute_workflow(wf, context={"changed_file": file_path})

    async def _on_email_received(self, wf: WorkflowDefinition, event_data: dict):
        category = wf.trigger.filter_category
        email_category = event_data.get("category", "")
        if category and category != email_category:
            return
        await self.execute_workflow(wf, context=event_data)

    def _register_builtin_handlers(self):
        self._bus.on(TriggerType.ON_START, self._handle_start)
        self._bus.on(TriggerType.ON_FILE_CHANGE, self._handle_file_change)
        self._bus.on(TriggerType.ON_EMAIL_RECEIVED, self._handle_email_received)

    async def _handle_start(self, event_data: dict):
        logger.debug("EventBus: on_start — %d workflows", len(self._workflows))

    async def _handle_file_change(self, event_data: dict):
        logger.debug("EventBus: on_file_change — %s", event_data.get("path", ""))

    async def _handle_email_received(self, event_data: dict):
        logger.debug("EventBus: on_email_received — %s",
                      event_data.get("category", "geral"))
