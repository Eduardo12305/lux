import asyncio


class DeliveryService:
    """Handles message delivery to connected clients."""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    async def send(self, session_id: str, message: dict) -> None:
        queue = self._queues.get(session_id)
        if queue:
            await queue.put(message)

    def register(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[session_id] = queue
        return queue

    def unregister(self, session_id: str) -> None:
        self._queues.pop(session_id, None)
