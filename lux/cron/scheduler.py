import asyncio


class CronScheduler:
    """Schedules and runs cron jobs."""

    def __init__(self):
        self._jobs: dict[str, "CronJob"] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def add_job(self, job: "CronJob") -> None:
        self._jobs[job.name] = job

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        for task in self._tasks.values():
            task.cancel()
