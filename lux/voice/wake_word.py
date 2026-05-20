import asyncio


class WakeWordDetector:
    """Wake word detection stub."""

    def __init__(self, wake_words: list[str] | None = None):
        self.wake_words = wake_words or ["hey lux"]

    async def listen(self) -> str:
        await asyncio.sleep(0.1)
        return self.wake_words[0]
