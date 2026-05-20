import uuid


class DMPairingService:
    """Handles DM pairing via verification codes."""

    def __init__(self):
        self._pending: dict[str, str] = {}

    async def initiate_pairing(self, user_id: str) -> str:
        code = uuid.uuid4().hex[:6]
        self._pending[code] = user_id
        return code

    async def confirm_pairing(self, code: str) -> str | None:
        return self._pending.pop(code, None)
