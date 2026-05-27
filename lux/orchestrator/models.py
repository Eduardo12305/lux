# lux/orchestrator/models.py
# Módulo: Orchestrator
# Dependências: nenhuma
# Status: IMPLEMENTADO

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class TaskStatus(str, Enum):
    WAITING   = "waiting"    # esperando dependências
    QUEUED    = "queued"     # na fila, aguardando slot
    RUNNING   = "running"    # subagente ativo
    PAUSED    = "paused"     # pausado pelo usuário
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    URGENT     = "urgent"      # vai para frente da fila
    NORMAL     = "normal"
    BACKGROUND = "background"  # só roda quando não há NORMAL/URGENT


@dataclass
class ManagedTask:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    description: str = ""
    user_id: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.QUEUED
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    toolsets: list[str] = field(default_factory=list)
    subagent_task_id: Optional[str] = None
    subagent_session_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    progress_notes: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED
        )

    @property
    def is_active(self) -> bool:
        return self.status in (TaskStatus.RUNNING, TaskStatus.PAUSED)

    @property
    def dependencies_satisfied(self) -> bool:
        return len(self.dependencies) == 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "user_id": self.user_id,
            "priority": self.priority.value,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "toolsets": self.toolsets,
            "subagent_task_id": self.subagent_task_id,
            "subagent_session_id": self.subagent_session_id,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_summary": self.result_summary,
            "progress_notes": self.progress_notes,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ManagedTask:
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            user_id=data.get("user_id", ""),
            priority=TaskPriority(data.get("priority", "normal")),
            status=TaskStatus(data.get("status", "queued")),
            dependencies=data.get("dependencies", []),
            dependents=data.get("dependents", []),
            toolsets=data.get("toolsets", []),
            subagent_task_id=data.get("subagent_task_id"),
            subagent_session_id=data.get("subagent_session_id"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result_summary=data.get("result_summary"),
            progress_notes=data.get("progress_notes", []),
            error=data.get("error"),
        )


@dataclass
class OrchestratorStatus:
    running: list[ManagedTask] = field(default_factory=list)
    queued: list[ManagedTask] = field(default_factory=list)
    waiting: list[ManagedTask] = field(default_factory=list)
    completed_today: list[ManagedTask] = field(default_factory=list)
    max_concurrent: int = 3
    active_count: int = 0
