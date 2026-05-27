# lux/acp/protocol.py
# Módulo: ACP
# Dependências: nenhuma
# Status: IMPLEMENTADO
# Notas: Protocolo ACP (Agent Communication Protocol) — compatível Hermes.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4


class ACPMessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    STREAM_START = "stream_start"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    ERROR = "error"
    STATUS = "status"
    TOOL_CALL = "tool_call"


@dataclass
class ACPFileContext:
    path: str = ""
    language: str = ""
    content: str = ""
    selection: Optional[str] = None
    cursor_line: int = 0
    cursor_column: int = 0


@dataclass
class ACPDiagnostic:
    severity: str = "error"
    message: str = ""
    line: int = 0
    column: int = 0
    source: str = ""


@dataclass
class ACPRequest:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    type: ACPMessageType = ACPMessageType.REQUEST
    user_id: str = ""
    session_id: str = ""
    message: str = ""
    open_file: Optional[ACPFileContext] = None
    diagnostics: list[ACPDiagnostic] = field(default_factory=list)
    workspace_path: str = ""
    conversation_history: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict) -> ACPRequest:
        open_file = None
        if data.get("open_file"):
            of = data["open_file"]
            open_file = ACPFileContext(
                path=of.get("path", ""),
                language=of.get("language", ""),
                content=of.get("content", ""),
                selection=of.get("selection"),
                cursor_line=of.get("cursor_line", 0),
                cursor_column=of.get("cursor_column", 0),
            )

        diagnostics = [
            ACPDiagnostic(
                severity=d.get("severity", "error"),
                message=d.get("message", ""),
                line=d.get("line", 0),
                column=d.get("column", 0),
                source=d.get("source", ""),
            )
            for d in data.get("diagnostics", [])
        ]

        return cls(
            id=data.get("id") or uuid4().hex[:12],
            type=ACPMessageType(data.get("type", "request")),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            message=data.get("message", ""),
            open_file=open_file,
            diagnostics=diagnostics,
            workspace_path=data.get("workspace_path", ""),
            conversation_history=data.get("conversation_history", []),
        )


@dataclass
class ACPResponse:
    id: str = ""
    type: ACPMessageType = ACPMessageType.RESPONSE
    message: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    status: str = "done"
    tokens_used: int = 0
    error: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "message": self.message,
            "tool_calls": self.tool_calls,
            "status": self.status,
            "tokens_used": self.tokens_used,
            "error": self.error,
        }
