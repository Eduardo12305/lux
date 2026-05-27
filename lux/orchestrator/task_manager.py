# lux/orchestrator/task_manager.py
# Módulo: Orchestrator
# Dependências: orchestrator/models.py, agent/agent.py
# Status: IMPLEMENTADO
# Notas: Gerencia múltiplas tarefas com fila, prioridade, dependências.

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from lux.agent.agent import AIAgent
from lux.agent.state import Channel, UserProfile
from lux.orchestrator.models import (
    ManagedTask,
    OrchestratorStatus,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    """
    Gerencia tarefas paralelas com controle de concorrência e dependências.
    Não substitui subagentes — os orquestra.
    """

    MAX_CONCURRENT = 3
    QUEUE_SIZE = 20

    def __init__(self):
        self._tasks: dict[str, ManagedTask] = {}
        self._queue: list[str] = []
        self._running: set[str] = set()
        self._callbacks: dict[str, Callable] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        description: str,
        user_id: str,
        user_profile: Optional[UserProfile] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: Optional[list[str]] = None,
        toolsets: Optional[list[str]] = None,
        callback: Optional[Callable] = None,
    ) -> ManagedTask:
        async with self._lock:
            if len(self._tasks) >= self.QUEUE_SIZE:
                oldest = min(self._tasks.values(), key=lambda t: t.created_at)
                if oldest.is_terminal:
                    del self._tasks[oldest.id]
                else:
                    raise RuntimeError(f"Fila cheia (max {self.QUEUE_SIZE} tarefas)")

            task = ManagedTask(
                description=description,
                user_id=user_id,
                priority=priority,
                dependencies=dependencies or [],
                toolsets=toolsets or [],
            )

            unsatisfied = [d for d in task.dependencies if d not in self._tasks or not self._tasks[d].is_terminal]
            if unsatisfied:
                task.status = TaskStatus.WAITING
                for dep_id in unsatisfied:
                    if dep_id in self._tasks:
                        self._tasks[dep_id].dependents.append(task.id)

            self._tasks[task.id] = task
            if callback:
                self._callbacks[task.id] = callback

            if task.status != TaskStatus.WAITING:
                await self._enqueue(task)

            logger.info(
                "Tarefa submetida: %s [%s] status=%s deps=%d",
                task.id[:8], task.description[:60], task.status.value, len(task.dependencies),
            )
            return task

    async def _enqueue(self, task: ManagedTask):
        if len(self._running) < self.MAX_CONCURRENT:
            await self._start_task(task)
            return

        self._queue.append(task.id)
        task.status = TaskStatus.QUEUED

        self._queue.sort(
            key=lambda tid: (
                0 if self._tasks[tid].priority == TaskPriority.URGENT else
                1 if self._tasks[tid].priority == TaskPriority.NORMAL else 2,
                self._tasks[tid].created_at,
            )
        )

    async def _start_task(self, task: ManagedTask):
        self._running.add(task.id)
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)

        asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: ManagedTask):
        try:
            agent = AIAgent(
                user_id=task.user_id,
                session_id=f"orch_{task.id}",
                max_iterations=20,
                enabled_toolsets=task.toolsets,
                is_subagent=True,
                compression_threshold=0.85,
            )

            result = await agent.run_conversation(user_message=task.description)
            await agent.close()

            task.result_summary = result.final_response[:2000]
            task.status = TaskStatus.COMPLETED if result.status.value == "done" else TaskStatus.FAILED
            if result.error:
                task.error = result.error

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.exception("Tarefa orquestrada falhou: %s", task.id[:8])

        finally:
            task.completed_at = datetime.now(timezone.utc)
            await self._on_task_complete(task)

    async def _on_task_complete(self, task: ManagedTask):
        async with self._lock:
            self._running.discard(task.id)

            for dep_id in task.dependents:
                if dep_id in self._tasks:
                    dep_task = self._tasks[dep_id]
                    dep_task.dependencies = [d for d in dep_task.dependencies if d != task.id]
                    if not dep_task.dependencies:
                        dep_task.status = TaskStatus.QUEUED
                        await self._enqueue(dep_task)

            while len(self._running) < self.MAX_CONCURRENT and self._queue:
                next_id = self._queue.pop(0)
                if next_id in self._tasks:
                    next_task = self._tasks[next_id]
                    if next_task.status == TaskStatus.QUEUED:
                        await self._start_task(next_task)

        if task.id in self._callbacks:
            try:
                self._callbacks[task.id](task)
            except Exception as e:
                logger.warning("Callback falhou para tarefa %s: %s", task.id[:8], e)

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.CANCELLED
                self._running.discard(task_id)
                task.completed_at = datetime.now(timezone.utc)
            elif task.status == TaskStatus.PAUSED:
                task.status = TaskStatus.CANCELLED
                self._running.discard(task_id)
                task.completed_at = datetime.now(timezone.utc)
            elif task.status == TaskStatus.QUEUED:
                task.status = TaskStatus.CANCELLED
                if task_id in self._queue:
                    self._queue.remove(task_id)
                task.completed_at = datetime.now(timezone.utc)
            elif task.status == TaskStatus.WAITING:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now(timezone.utc)
            else:
                return False

            logger.info("Tarefa cancelada: %s", task_id[:8])
            return True

    def get_status(self) -> OrchestratorStatus:
        now = datetime.now(timezone.utc)
        running = [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]
        queued = [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
        waiting = [t for t in self._tasks.values() if t.status == TaskStatus.WAITING]
        completed = [
            t for t in self._tasks.values()
            if t.is_terminal and t.completed_at and (now - t.completed_at).days < 1
        ]

        running.sort(key=lambda t: t.started_at or t.created_at)
        queued.sort(key=lambda t: (t.priority.value, t.created_at))
        waiting.sort(key=lambda t: t.created_at)
        completed.sort(key=lambda t: t.completed_at or t.created_at, reverse=True)

        return OrchestratorStatus(
            running=running,
            queued=queued,
            waiting=waiting,
            completed_today=completed,
            max_concurrent=self.MAX_CONCURRENT,
            active_count=len(self._running),
        )

    def get_task(self, task_id: str) -> Optional[ManagedTask]:
        return self._tasks.get(task_id)
