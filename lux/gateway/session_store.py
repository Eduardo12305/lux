from dataclasses import dataclass, field
import time


@dataclass
class Session:
    session_id: str
    user_id: str
    created_at: float = field(default_factory=time.time)


class SessionStore:
    """In-memory session storage."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, session: Session) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
