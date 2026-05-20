from lux.plugins.base import Plugin


class PluginManager:
    """Discovers, loads, and manages plugins."""

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}

    async def discover(self, plugin_dir: str) -> list[str]:
        return []

    async def load(self, name: str) -> None:
        pass

    async def unload(self, name: str) -> None:
        pass

    async def shutdown(self) -> None:
        for plugin in self._plugins.values():
            await plugin.on_shutdown()
        self._plugins.clear()
