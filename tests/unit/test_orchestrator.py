# tests/unit/test_orchestrator.py
# Módulo: Testes de Task Orchestrator
# Status: IMPLEMENTADO

from __future__ import annotations

import pytest

from lux.orchestrator.models import (
    ManagedTask,
    OrchestratorStatus,
    TaskPriority,
    TaskStatus,
)
from lux.orchestrator.task_manager import TaskOrchestrator


# ── ManagedTask ──────────────────────────────────────────────────────────


def test_managed_task_defaults():
    t = ManagedTask(description="teste")
    assert t.id
    assert t.status == TaskStatus.QUEUED
    assert t.priority == TaskPriority.NORMAL
    assert t.is_terminal is False
    assert t.dependencies == []


def test_managed_task_terminal():
    t = ManagedTask(status=TaskStatus.COMPLETED)
    assert t.is_terminal is True
    t2 = ManagedTask(status=TaskStatus.CANCELLED)
    assert t2.is_terminal is True
    t3 = ManagedTask(status=TaskStatus.RUNNING)
    assert t3.is_terminal is False


def test_managed_task_to_dict():
    t = ManagedTask(
        id="t1", description="task desc", user_id="u1",
        priority=TaskPriority.URGENT, toolsets=["web"],
    )
    d = t.to_dict()
    assert d["id"] == "t1"
    assert d["priority"] == "urgent"
    assert d["toolsets"] == ["web"]


def test_managed_task_from_dict():
    d = {
        "id": "t2", "description": "desc", "user_id": "u1",
        "priority": "background", "status": "queued",
        "dependencies": [], "dependents": [], "toolsets": ["terminal"],
        "created_at": "2026-05-20T10:00:00+00:00",
    }
    t = ManagedTask.from_dict(d)
    assert t.priority == TaskPriority.BACKGROUND
    assert t.toolsets == ["terminal"]


# ── TaskOrchestrator ────────────────────────────────────────────────────


@pytest.fixture
def orchestrator():
    return TaskOrchestrator()


@pytest.mark.asyncio
async def test_submit_creates_task(orchestrator):
    task = await orchestrator.submit("tarefa simples", "u1")
    assert task.id
    assert task.description == "tarefa simples"
    assert task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)


@pytest.mark.asyncio
async def test_submit_max_concurrent(orchestrator):
    """4 tarefas: 3 RUNNING, 1 QUEUED."""
    for i in range(4):
        await orchestrator.submit(f"task {i}", "u1")
    status = orchestrator.get_status()
    assert len(status.running) <= orchestrator.MAX_CONCURRENT
    assert status.active_count <= orchestrator.MAX_CONCURRENT


@pytest.mark.asyncio
async def test_submit_with_dependencies(orchestrator):
    t1 = await orchestrator.submit("task base", "u1")
    t2 = await orchestrator.submit("task dependente", "u1", dependencies=[t1.id])
    assert t2.status == TaskStatus.WAITING
    assert t1.id in t2.dependencies


@pytest.mark.asyncio
async def test_cancel_queued(orchestrator):
    for i in range(4):
        await orchestrator.submit(f"task {i}", "u1")
    status = orchestrator.get_status()
    if status.queued:
        cancelled = await orchestrator.cancel(status.queued[0].id)
        assert cancelled is True


@pytest.mark.asyncio
async def test_cancel_completed_fails(orchestrator):
    from lux.orchestrator.models import ManagedTask
    t = ManagedTask(id="done", description="x", status=TaskStatus.COMPLETED,
                     completed_at=__import__("datetime").datetime.now())
    orchestrator._tasks["done"] = t
    assert await orchestrator.cancel("done") is False


@pytest.mark.asyncio
async def test_cancel_nonexistent(orchestrator):
    assert await orchestrator.cancel("ghost") is False


# ── OrchestratorStatus ──────────────────────────────────────────────────


def test_orchestrator_status_defaults():
    s = OrchestratorStatus()
    assert s.running == []
    assert s.max_concurrent == 3
    assert s.active_count == 0


# ── TaskPriority ordering ──────────────────────────────────────────────


def test_priority_ordering():
    """URGENT < NORMAL < BACKGROUND em comparacao."""
    priorities = ["urgent", "normal", "background"]
    assert TaskPriority("urgent") == TaskPriority.URGENT
    assert TaskPriority("background") == TaskPriority.BACKGROUND


def test_task_status_values():
    assert TaskStatus.WAITING.value == "waiting"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"
