from dataclasses import dataclass
from collections.abc import Awaitable, Callable


@dataclass
class CronJob:
    name: str
    schedule: str
    handler: Callable[[], Awaitable[None]]

    async def run(self) -> None:
        await self.handler()
