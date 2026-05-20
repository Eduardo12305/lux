class ACPServer:
    """Agent Communication Protocol server stub."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9090):
        self.host = host
        self.port = port

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass
