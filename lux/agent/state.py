# lux/agent/state.py
# Módulo: Core State Types
# Dependências: nenhuma (tipos puros, sem imports internos)
# Status: IMPLEMENTADO
# Notas: Todos os dataclasses do domínio Lux. SerializableMixin usa dataclasses_json.

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4


# ── Enums ───────────────────────────────────────────────────────────────────


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    THINKING = "thinking"


class Channel(str, Enum):
    CLI = "cli"
    VOICE = "voice"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    SLACK = "slack"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    WEBHOOK = "webhook"
    ACP = "acp"

    @property
    def supports_streaming(self) -> bool:
        return self in (Channel.CLI, Channel.TELEGRAM, Channel.DISCORD, Channel.VOICE)


class Task(str, Enum):
    CONVERSATION = "conversation"
    CONVERSATION_DEEP = "conversation_deep"
    ACTION_PLANNING = "action_planning"
    SKILL_CREATION = "skill_creation"
    SUMMARIZE_LONG = "summarize_long"
    SUMMARIZE_SHORT = "summarize_short"
    TOOL_CALL_COMPLEX = "tool_call_complex"
    INTENT_CLASSIFY = "intent_classify"
    MEMORY_EXTRACT = "memory_extract"
    SENTIMENT_DETECT = "sentiment_detect"
    CONFIRMATION_PARSE = "confirmation_parse"
    ENTITY_EXTRACT = "entity_extract"
    SKILL_TRIGGER_CHECK = "skill_trigger_check"


class Intent(str, Enum):
    CHAT = "chat"
    QUESTION = "question"
    ACTION = "action"
    RECALL = "recall"
    COMMAND = "command"
    CLARIFY = "clarify"
    PLAN = "plan"
    DELEGATE = "delegate"


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class ResponseStyle(str, Enum):
    CONCISE = "concise"
    BALANCED = "balanced"
    DETAILED = "detailed"


class Formality(str, Enum):
    CASUAL = "casual"
    NEUTRAL = "neutral"
    FORMAL = "formal"


class ListeningMode(str, Enum):
    OFF = "off"
    WAKE_WORD = "wake_word"
    PUSH_TO_TALK = "push_to_talk"
    ALWAYS_ON = "always_on"


class PipelineStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    FINALIZING = "finalizing"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    DONE = "done"


class MemoryAction(str, Enum):
    ADD = "add"
    REPLACE = "replace"
    REMOVE = "remove"


class MemoryTarget(str, Enum):
    MEMORY = "memory"
    USER = "user"


class RequestPriority(int, Enum):
    INTERACTIVE = 0
    BATCH = 1
    BACKGROUND = 2


class ToolCallStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class ThinkingState(Enum):
    IDLE = auto()
    IN_OPEN = auto()
    THINKING = auto()
    IN_CLOSE = auto()


# ── Simple Dataclasses ──────────────────────────────────────────────────────


@dataclass
class Attachment:
    name: str
    mime_type: str
    data: bytes = field(repr=False)
    size_bytes: int = 0

    def __post_init__(self):
        if self.size_bytes == 0:
            self.size_bytes = len(self.data)


@dataclass
class Entity:
    name: str
    type: str
    value: str


@dataclass
class ToolCall:
    id: str = field(default_factory=lambda: f"call_{uuid4().hex[:12]}")
    function_name: str = ""
    arguments: dict = field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_openai_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.function_name,
                "arguments": self._serialize_args(),
            },
        }

    def _serialize_args(self) -> str:
        import json

        return json.dumps(self.arguments, ensure_ascii=False)


@dataclass
class ToolResult:
    tool_call_id: str = ""
    success: bool = True
    output: str = ""
    error_message: Optional[str] = None
    data: dict = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, output: str = "", tool_call_id: str = "", **kwargs) -> ToolResult:
        return cls(tool_call_id=tool_call_id, success=True, output=output, **kwargs)

    @classmethod
    def failure(
        cls, error_msg: str, tool_call_id: str = "", output: str = ""
    ) -> ToolResult:
        return cls(
            tool_call_id=tool_call_id,
            success=False,
            error_message=error_msg,
            output=output,
        )

    @classmethod
    def rejected(cls, tool_name: str, tool_call_id: str = "") -> ToolResult:
        return cls(
            tool_call_id=tool_call_id,
            success=False,
            error_message=f"Ferramenta '{tool_name}' rejeitada pelo usuário.",
        )

    @classmethod
    def timed_out(cls, tool_name: str, timeout_s: int, tool_call_id: str = "") -> ToolResult:
        return cls(
            tool_call_id=tool_call_id,
            success=False,
            error_message=f"Timeout após {timeout_s}s na ferramenta '{tool_name}'.",
        )

    def to_string(self) -> str:
        if self.success:
            return self.output or "OK"
        return f"ERRO: {self.error_message}" if self.error_message else "FALHA"


@dataclass
class TodoItem:
    id: int
    text: str
    done: bool = False
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ApprovalPattern:
    label: str
    regex: str
    toolset: str = ""
    always_allow: bool = False
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ApprovalResult:
    approved: bool
    added_to_allowlist: bool = False
    user_response: str = ""


@dataclass
class ApprovalRequest:
    id: str = field(default_factory=lambda: uuid4().hex)
    tool_name: str = ""
    command_preview: str = ""
    args: dict = field(default_factory=dict)
    requested_at: datetime = field(default_factory=datetime.now)
    timeout_seconds: int = 120

    @property
    def expires_at(self) -> datetime:
        from datetime import timedelta

        return self.requested_at + timedelta(seconds=self.timeout_seconds)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or datetime.now()) > self.expires_at


# ── Memory Dataclasses ──────────────────────────────────────────────────────


@dataclass
class MemoryDelta:
    action: MemoryAction
    target: MemoryTarget
    content: Optional[str] = None
    old_text: Optional[str] = None
    user_id: str = ""
    applied: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryChunk:
    id: str
    content: str
    source: str = ""
    score: float = 0.0
    session_id: str = ""
    timestamp: Optional[datetime] = None
    user_id: str = ""

    @classmethod
    def from_qdrant(cls, hit: dict) -> MemoryChunk:
        payload = hit.get("payload", {})
        return cls(
            id=str(hit.get("id", "")),
            content=payload.get("content", ""),
            source="semantic",
            score=hit.get("score", 0.0),
            session_id=payload.get("session_id", ""),
            user_id=payload.get("user_id", ""),
        )


@dataclass
class SessionSearchResult:
    id: str
    session_id: str
    timestamp: str
    role: str
    snippet: str
    score: float
    source: str = "fts5"

    @classmethod
    def from_row(cls, row: tuple) -> SessionSearchResult:
        return cls(
            id=row[0],
            session_id=row[1],
            timestamp=str(row[2]),
            role=row[3],
            snippet=row[4],
            score=float(row[5]),
        )


@dataclass
class MemoryResult:
    success: bool
    message: str = ""
    error_message: Optional[str] = None
    chars_used: int = 0
    chars_limit: int = 0

    @classmethod
    def ok(cls, message: str, **kwargs) -> MemoryResult:
        return cls(success=True, message=message, **kwargs)

    @classmethod
    def failure(cls, error_msg: str, **kwargs) -> MemoryResult:
        return cls(success=False, error_message=error_msg, message=error_msg, **kwargs)


@dataclass
class MergedResult:
    id: str = ""
    content: str = ""
    score: float = 0.0
    sources: list[str] = field(default_factory=list)
    session_id: str = ""
    timestamp: Optional[datetime] = None


# ── Skill Dataclasses ───────────────────────────────────────────────────────


@dataclass
class SkillMetadata:
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    platforms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    category: str = ""
    requires_toolsets: list[str] = field(default_factory=list)
    fallback_for_toolsets: list[str] = field(default_factory=list)
    created_from_task: str = ""
    quality_score: float = 0.0
    use_count: int = 0
    last_used: Optional[str] = None
    config: list[dict] = field(default_factory=list)


@dataclass
class SkillSummary:
    name: str
    description: str
    category: str = ""
    slash_command: bool = True
    platforms: list[str] = field(default_factory=list)
    requires_toolsets: list[str] = field(default_factory=list)
    fallback_for_toolsets: list[str] = field(default_factory=list)
    author: str = ""

    @classmethod
    def from_metadata(cls, meta: SkillMetadata) -> SkillSummary:
        return cls(
            name=meta.name,
            description=meta.description,
            category=meta.category,
            platforms=meta.platforms,
            requires_toolsets=meta.requires_toolsets,
            fallback_for_toolsets=meta.fallback_for_toolsets,
            author=meta.author,
        )


@dataclass
class Skill:
    name: str
    description: str
    raw_content: str
    metadata: SkillMetadata = field(default_factory=SkillMetadata)
    source_path: Optional[Path] = None

    @classmethod
    def from_markdown(cls, content: str, source_path: Optional[Path] = None) -> Skill:
        from lux.skills.loader import SkillLoader

        return SkillLoader().parse(content, source_path)


# ── Subagent ────────────────────────────────────────────────────────────────


@dataclass
class SubagentTask:
    id: str = field(default_factory=lambda: uuid4().hex)
    task: str = ""
    context: Optional[str] = None
    toolsets: list[str] = field(default_factory=list)
    max_iterations: int = 20
    parent_task_id: str = ""
    user_id: str = ""
    status: str = "pending"
    result: Optional[str] = None
    iterations_used: int = 0
    error: Optional[str] = None


# ── Core Message ────────────────────────────────────────────────────────────


@dataclass
class Message:
    id: str = field(default_factory=lambda: uuid4().hex)
    session_id: str = ""
    user_id: str = ""
    channel: Channel = Channel.CLI
    role: Role = Role.USER
    content: str = ""
    thinking_content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    attachments: list[Attachment] = field(default_factory=list)
    intent: Optional[Intent] = None
    entities: list[Entity] = field(default_factory=list)
    requires_approval: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    model_used: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    latency_ms: int = 0
    iteration: int = 0
    task_id: str = ""
    parent_message_id: Optional[str] = None
    memory_hits: list[str] = field(default_factory=list)

    def to_openai_dict(self) -> dict:
        msg: dict = {"role": self.role.value}
        if self.content:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_openai_dict() for tc in self.tool_calls]
        if self.tool_call_id and self.role == Role.TOOL:
            msg["tool_call_id"] = self.tool_call_id
        if self.role == Role.TOOL and not self.content:
            msg["content"] = ""
        return msg


# ── UserProfile ─────────────────────────────────────────────────────────────


@dataclass
class UserProfile:
    user_id: str = ""
    username: str = ""
    display_name: str = ""
    role: UserRole = UserRole.USER
    preferred_language: str = "pt-BR"
    response_style: ResponseStyle = ResponseStyle.BALANCED
    formality: Formality = Formality.CASUAL
    technical_depth: int = 3
    preferred_channel: Channel = Channel.CLI
    voice_enabled: bool = False
    listening_mode: ListeningMode = ListeningMode.PUSH_TO_TALK
    preferred_voice: str = "pt_BR-faber-medium"
    approval_patterns: list[ApprovalPattern] = field(default_factory=list)
    danger_patterns: list[str] = field(default_factory=list)
    enabled_toolsets: list[str] = field(
        default_factory=lambda: [
            "web",
            "tasks",
            "calendar",
            "memory_tools",
            "skills",
            "system",
        ]
    )
    active_projects: list[str] = field(default_factory=list)
    work_hours: tuple[Optional[time], Optional[time]] = (None, None)
    timezone: str = "America/Sao_Paulo"
    disabled_skills: list[str] = field(default_factory=list)
    skill_overrides: dict[str, dict] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_seen: Optional[datetime] = None
    total_sessions: int = 0
    total_tokens_used: int = 0


# ── AgentState ──────────────────────────────────────────────────────────────


@dataclass
class AgentState:
    task_id: str = field(default_factory=lambda: uuid4().hex)
    session_id: str = ""
    user_id: str = ""
    user_profile: UserProfile = field(default_factory=UserProfile)
    channel: Channel = Channel.CLI
    system_prompt_frozen: str = ""
    conversation_history: list[Message] = field(default_factory=list)
    context_files: dict[str, str] = field(default_factory=dict)
    memory_snapshot: str = ""
    user_snapshot: str = ""
    pending_memory_writes: list[MemoryDelta] = field(default_factory=list)
    active_skill: Optional[Skill] = None
    skill_context: Optional[str] = None
    current_tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    pending_approval: Optional[ApprovalRequest] = None
    subagent_tasks: list[SubagentTask] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 50
    budget_warnings_sent: int = 0
    is_subagent: bool = False
    parent_task_id: Optional[str] = None
    compression_count: int = 0
    session_lineage_id: str = ""
    pipeline_status: PipelineStatus = PipelineStatus.IDLE
    error: Optional[str] = None
    trajectory: list[TrajectoryStep] = field(default_factory=list)
    checkpoint_path: Optional[str] = None
    agent_todos: list[TodoItem] = field(default_factory=list)

    _interrupt_event: Optional[asyncio.Event] = field(
        default=None, repr=False, compare=False
    )

    @property
    def interrupt_event(self) -> asyncio.Event:
        if self._interrupt_event is None:
            self._interrupt_event = asyncio.Event()
        return self._interrupt_event

    def to_openai_messages(self) -> list[dict]:
        messages: list[dict] = []

        if self.system_prompt_frozen:
            messages.append({"role": "system", "content": self.system_prompt_frozen})

        for msg in self.conversation_history:
            messages.append(msg.to_openai_dict())

        return messages

    def enforce_alternation(self):
        merged: list[Message] = []
        for msg in self.conversation_history:
            if msg.role == Role.TOOL:
                merged.append(msg)
                continue
            if (
                merged
                and merged[-1].role == msg.role
                and msg.role in (Role.USER, Role.ASSISTANT, Role.SYSTEM)
            ):
                merged[-1].content = merged[-1].content + "\n\n" + msg.content
                merged[-1].tool_calls.extend(msg.tool_calls)
                msg.tool_calls = []
            else:
                merged.append(msg)
        self.conversation_history = merged


# ── Agent Loop Results ──────────────────────────────────────────────────────


@dataclass
class LLMResponse:
    content: str = ""
    thinking_content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    model: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    latency_ms: int = 0

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @classmethod
    def from_raw(cls, raw: dict) -> LLMResponse:
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message", {})
        tool_calls_raw = message.get("tool_calls") or []
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                function_name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", {}),
            )
            for tc in tool_calls_raw
        ]
        usage = raw.get("usage", {})
        return cls(
            content=message.get("content", ""),
            thinking_content=None,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            model=raw.get("model", ""),
            tokens_prompt=usage.get("prompt_tokens", 0),
            tokens_completion=usage.get("completion_tokens", 0),
        )


@dataclass
class TrajectoryStep:
    iteration: int
    messages_before: int
    llm_response: LLMResponse
    tool_calls_executed: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    compressed: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConversationResult:
    final_response: str = ""
    messages: list[Message] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    trajectory: list[TrajectoryStep] = field(default_factory=list)
    session_id: str = ""
    iterations_used: int = 0
    tokens_used: int = 0
    compressed_count: int = 0
    status: PipelineStatus = PipelineStatus.DONE
    pending_items: list[str] = field(default_factory=list)
    error: Optional[str] = None


# ── Startup & Health ────────────────────────────────────────────────────────


@dataclass
class ServiceStatus:
    name: str
    running: bool
    url: str = ""
    error: Optional[str] = None
    latency_ms: Optional[float] = None


@dataclass
class StartupReport:
    success: bool
    services: dict[str, ServiceStatus] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    startup_time_ms: float = 0.0
