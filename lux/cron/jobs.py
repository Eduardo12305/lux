# lux/cron/jobs.py
# Módulo: Cron
# Dependências: constants.py, config.py
# Status: IMPLEMENTADO
# Notas: CRUD de CronJob em JSON + tabela SQLite. APScheduler compatível.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from lux.agent.state import Channel
from lux.constants import CRON_DIR

logger = logging.getLogger(__name__)

JOBS_FILE = CRON_DIR / "jobs.json"


@dataclass
class CronJob:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    user_id: str = ""
    name: str = ""
    prompt: str = ""
    schedule: str = ""
    skills: list[str] = field(default_factory=list)
    toolsets: list[str] = field(default_factory=list)
    delivery_channel: Channel = Channel.CLI
    delivery_target: str = ""
    is_active: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "prompt": self.prompt,
            "schedule": self.schedule,
            "skills": self.skills,
            "toolsets": self.toolsets,
            "delivery_channel": self.delivery_channel.value,
            "delivery_target": self.delivery_target,
            "is_active": self.is_active,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> CronJob:
        return cls(
            id=data.get("id", ""),
            user_id=data.get("user_id", ""),
            name=data.get("name", ""),
            prompt=data.get("prompt", ""),
            schedule=data.get("schedule", ""),
            skills=data.get("skills", []),
            toolsets=data.get("toolsets", []),
            delivery_channel=Channel(data.get("delivery_channel", "cli")),
            delivery_target=data.get("delivery_target", ""),
            is_active=data.get("is_active", True),
            last_run=datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None,
            next_run=datetime.fromisoformat(data["next_run"]) if data.get("next_run") else None,
            run_count=data.get("run_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
        )


class CronJobStore:
    """Gerencia persistência de CronJobs em JSON."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or JOBS_FILE
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, jobs: list[dict]):
        self._path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2))

    def list_all(self, user_id: Optional[str] = None) -> list[CronJob]:
        jobs = self._read()
        if user_id:
            jobs = [j for j in jobs if j.get("user_id") == user_id]
        return [CronJob.from_dict(j) for j in jobs]

    def list_active(self) -> list[CronJob]:
        return [j for j in self.list_all() if j.is_active]

    def get(self, job_id: str) -> Optional[CronJob]:
        jobs = self._read()
        for j in jobs:
            if j.get("id") == job_id:
                return CronJob.from_dict(j)
        return None

    def create(self, job: CronJob) -> CronJob:
        jobs = self._read()
        jobs.append(job.to_dict())
        self._write(jobs)
        logger.info("CronJob criado: %s (%s)", job.name, job.schedule)
        return job

    def update(self, job: CronJob) -> bool:
        jobs = self._read()
        for i, j in enumerate(jobs):
            if j.get("id") == job.id:
                jobs[i] = job.to_dict()
                self._write(jobs)
                return True
        return False

    def delete(self, job_id: str) -> bool:
        jobs = self._read()
        before = len(jobs)
        jobs = [j for j in jobs if j.get("id") != job_id]
        if len(jobs) < before:
            self._write(jobs)
            logger.info("CronJob removido: %s", job_id)
            return True
        return False

    def get_due(self, now: Optional[datetime] = None) -> list[CronJob]:
        now = now or datetime.now(timezone.utc)
        due = []
        for job in self.list_active():
            if job.next_run and job.next_run <= now:
                due.append(job)
        return due
