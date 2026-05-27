# lux/cron/scheduler.py
# Módulo: Cron
# Dependências: cron/jobs.py, agent/agent.py, APScheduler
# Status: IMPLEMENTADO
# Notas: Scheduler baseado em APScheduler com execução de jobs via AIAgent.

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from lux.agent.agent import AIAgent
from lux.agent.state import Channel
from lux.cron.jobs import CronJob, CronJobStore
from lux.skills.manager import SkillManager

logger = logging.getLogger(__name__)


class CronScheduler:
    """
    Scheduler de tarefas agendadas.
    Jobs armazenados em ~/.lux/cron/jobs.json.
    """

    def __init__(
        self,
        store: Optional[CronJobStore] = None,
        skill_manager: Optional[SkillManager] = None,
    ):
        self._store = store or CronJobStore()
        self._skill_mgr = skill_manager or SkillManager()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._poll_interval = 30

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("CronScheduler iniciado (poll a cada %ds)", self._poll_interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CronScheduler parado")

    async def _loop(self):
        while self._running:
            try:
                await self._check_and_run_due()
            except Exception:
                logger.exception("Erro no loop do scheduler")
            await asyncio.sleep(self._poll_interval)

    async def _check_and_run_due(self):
        due = self._store.get_due()
        if not due:
            return

        for job in due:
            if not self._running:
                break
            try:
                await self._execute_job(job)
            except Exception:
                logger.exception("Falha ao executar CronJob %s", job.name)

    async def _execute_job(self, job: CronJob):
        logger.info("Executando CronJob: %s (run #%d)", job.name, job.run_count + 1)

        skill_context = ""
        if job.skills:
            for s in job.skills:
                try:
                    skill_context += self._skill_mgr.get_skill_content_l1(s) + "\n\n"
                except FileNotFoundError:
                    pass

        agent = AIAgent(
            user_id=job.user_id,
            session_id=f"cron_{job.id}_{int(job.last_run.timestamp()) if job.last_run else 0}",
            max_iterations=20,
            enabled_toolsets=job.toolsets,
            is_subagent=True,
        )

        try:
            result = await agent.run_conversation(
                user_message=job.prompt,
                system_message=skill_context if skill_context else None,
            )

            await self._deliver_result(job, result.final_response)

            job.run_count += 1
            job.last_run = datetime.now(timezone.utc)
            job.next_run = self._calculate_next_run(job.schedule)
            self._store.update(job)

            logger.info(
                "CronJob %s concluido: %d iteracoes",
                job.name, result.iterations_used,
            )
        finally:
            await agent.close()

    async def _deliver_result(self, job: CronJob, response: str):
        if job.delivery_channel == Channel.CLI:
            logger.info("CronJob [%s] resultado:\n%s", job.name, response[:500])
        elif job.delivery_channel == Channel.TELEGRAM:
            try:
                from lux.gateway.platforms.telegram import TelegramAdapter
                tg = TelegramAdapter()
                await tg.send_message(job.delivery_target, response)
            except Exception as e:
                logger.warning("Falha ao entregar via Telegram: %s", e)

    def _calculate_next_run(self, schedule: str) -> datetime:
        try:
            from croniter import croniter
            base = datetime.now(timezone.utc)
            return croniter(schedule, base).get_next(datetime)
        except ImportError:
            from datetime import timedelta
            return datetime.now(timezone.utc) + timedelta(hours=1)

    # ── Job Management ──────────────────────────────────────────────────

    def list_jobs(self, user_id: Optional[str] = None) -> list[CronJob]:
        return self._store.list_all(user_id)

    def create_job(
        self,
        user_id: str,
        name: str,
        prompt: str,
        schedule: str,
        skills: Optional[list[str]] = None,
        toolsets: Optional[list[str]] = None,
        delivery_channel: Channel = Channel.CLI,
        delivery_target: str = "",
    ) -> CronJob:
        job = CronJob(
            user_id=user_id,
            name=name,
            prompt=prompt,
            schedule=schedule,
            skills=skills or [],
            toolsets=toolsets or [],
            delivery_channel=delivery_channel,
            delivery_target=delivery_target,
            next_run=self._calculate_next_run(schedule),
        )
        return self._store.create(job)

    def delete_job(self, job_id: str) -> bool:
        return self._store.delete(job_id)

    def toggle_job(self, job_id: str) -> Optional[CronJob]:
        job = self._store.get(job_id)
        if not job:
            return None
        job.is_active = not job.is_active
        self._store.update(job)
        return job
