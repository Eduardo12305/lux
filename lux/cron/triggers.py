# lux/cron/triggers.py
# Módulo: Cron
# Dependências: cron/scheduler.py, agent/state.py
# Status: IMPLEMENTADO
# Notas: Triggers condicionais que disparam sem schedule fixo.

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from lux.agent.state import AgentState
from lux.cron.jobs import CronJobStore

logger = logging.getLogger(__name__)


class AutonomyLevel(str, Enum):
    SILENT = "silent"
    NOTIFY = "notify"
    CONFIRM = "confirm"


@dataclass
class ProactiveTrigger:
    id: str
    condition: str
    action: str
    autonomy: AutonomyLevel = AutonomyLevel.NOTIFY
    cooldown_minutes: int = 30
    last_fired: Optional[datetime] = None

    def is_cooled_down(self, now: Optional[datetime] = None) -> bool:
        if not self.last_fired:
            return True
        now = now or datetime.now(timezone.utc)
        return (now - self.last_fired).total_seconds() / 60 >= self.cooldown_minutes

    def fire(self):
        self.last_fired = datetime.now(timezone.utc)


BUILT_IN_TRIGGERS = [
    ProactiveTrigger(
        id="vram_high",
        condition="VRAM > 85% por 5+ minutos",
        action="Alertar usuario sobre uso elevado de VRAM e sugerir acoes",
        autonomy=AutonomyLevel.NOTIFY,
        cooldown_minutes=30,
    ),
    ProactiveTrigger(
        id="long_session_no_memory",
        condition="Sessao com >40 mensagens sem salvar memoria",
        action="Fazer backup de memoria da sessao e sugerir consolidacao",
        autonomy=AutonomyLevel.SILENT,
        cooldown_minutes=0,
    ),
    ProactiveTrigger(
        id="pending_reminders",
        condition="Lembretes pendentes nao disparados",
        action="Notificar usuario sobre lembretes atrasados",
        autonomy=AutonomyLevel.NOTIFY,
        cooldown_minutes=15,
    ),
    ProactiveTrigger(
        id="disk_low",
        condition="Disco < 5GB livre",
        action="Alertar usuario sobre pouco espaco em disco",
        autonomy=AutonomyLevel.NOTIFY,
        cooldown_minutes=120,
    ),
]


class ProactiveTriggerEngine:
    """Avalia e dispara triggers condicionais periodicamente."""

    def __init__(self, store: Optional[CronJobStore] = None):
        self._store = store or CronJobStore()
        self._triggers: list[ProactiveTrigger] = list(BUILT_IN_TRIGGERS)
        self._custom_triggers: list[ProactiveTrigger] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = 30

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("ProactiveTriggerEngine iniciado")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while self._running:
            try:
                await self._evaluate_all()
            except Exception:
                logger.exception("Erro no loop de triggers")
            await asyncio.sleep(self._poll_interval)

    async def _evaluate_all(self):
        all_triggers = self._triggers + self._custom_triggers
        now = datetime.now(timezone.utc)

        for trigger in all_triggers:
            if not trigger.is_cooled_down(now):
                continue

            if await self._check_condition(trigger):
                await self._fire_trigger(trigger)

    async def _check_condition(self, trigger: ProactiveTrigger) -> bool:
        if trigger.id == "vram_high":
            try:
                from lux.models.vram_guard import VRAMGuard
                guard = VRAMGuard()
                ratio = await guard.usage_ratio()
                return ratio > 0.85
            except Exception:
                return False

        if trigger.id == "disk_low":
            import shutil
            usage = shutil.disk_usage("/")
            free_gb = usage.free / (1024**3)
            return free_gb < 5.0

        if trigger.id == "pending_reminders":
            from lux.constants import LUX_HOME
            calendar_dir = LUX_HOME / "calendar"
            if not calendar_dir.exists():
                return False
            now = datetime.now(timezone.utc)
            for f in calendar_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError):
                    continue
                for r in data.get("reminders", []):
                    if not r.get("fired") and r.get("fire_at", "") < now.isoformat():
                        return True
            return False

        return False

    async def _fire_trigger(self, trigger: ProactiveTrigger):
        trigger.fire()
        logger.info(
            "Trigger disparado: %s (autonomy=%s)",
            trigger.id, trigger.autonomy.value,
        )
        if trigger.autonomy == AutonomyLevel.NOTIFY:
            logger.warning("TRIGGER [%s]: %s", trigger.id, trigger.action)

    def add_trigger(self, trigger: ProactiveTrigger):
        self._custom_triggers.append(trigger)

    def remove_trigger(self, trigger_id: str):
        self._custom_triggers = [
            t for t in self._custom_triggers if t.id != trigger_id
        ]

    def list_triggers(self) -> list[ProactiveTrigger]:
        return self._triggers + self._custom_triggers

    @property
    def is_running(self) -> bool:
        return self._running
