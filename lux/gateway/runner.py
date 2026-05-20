import asyncio


class GatewayRunner:
    """Manages the gateway event loop and WebSocket server."""

    def __init__(self, host: str = "0.0.0.0", port: int = 7878):
        self.host = host
        self.port = port

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass
