from abc import ABC, abstractmethod


class Plugin(ABC):
    """Base class for Lux plugins."""

    name: str = ""
    version: str = "0.1.0"

    @abstractmethod
    async def on_load(self) -> None:
        ...

    @abstractmethod
    async def on_unload(self) -> None:
        ...

    async def on_message(self, message: dict) -> dict | None:
        return None

    async def on_startup(self) -> None:
        pass

    async def on_shutdown(self) -> None:
        pass
