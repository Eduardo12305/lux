# tests/e2e/conftest.py
from __future__ import annotations
import pytest
from datetime import datetime, timezone
from lux.agent.state import (
    AgentState, Channel, ConversationResult, LLMResponse, Message,
    PipelineStatus, Role, ToolCall, ToolResult, UserProfile, UserRole,
)
from lux.memory.session_db import SessionDB


class MockLlamaClient:
    """Simula llama-server para testes E2E sem servidor real."""

    def __init__(self, responses: list[LLMResponse] | None = None):
        self._responses = responses or []
        self._call_count = 0
        self._closed = False
        self.main_url = "mock://main"
        self.aux_url = "mock://aux"

    async def chat_completion(self, messages, model="main", temperature=0.7,
                               max_tokens=4096, tools=None, enable_thinking=False,
                               session_id="", **kwargs) -> LLMResponse:
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return LLMResponse(content="resposta mock")

    async def chat_completion_stream(self, *args, **kwargs):
        yield "resposta"
        yield " mock"
        yield " streaming"

    async def health_check(self, model="main"):
        return True

    async def close(self):
        self._closed = True

    async def acquire_slot(self, session_id, model="main"):
        return 0

    async def release_slot(self, session_id, model="main"):
        pass


def make_text_response(text: str, model="qwen3-14b-q4") -> LLMResponse:
    return LLMResponse(
        content=text,
        model=model,
        finish_reason="stop",
        tokens_prompt=100,
        tokens_completion=len(text) // 4,
    )


def make_tool_response(tool_calls: list[ToolCall]) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=tool_calls,
        model="qwen3-14b-q4",
        finish_reason="tool_calls",
        tokens_prompt=200,
        tokens_completion=50,
    )


@pytest.fixture
def tmp_db(tmp_path):
    db = SessionDB(db_path=tmp_path / "e2e_test.db")
    return db


@pytest.fixture
def user_profile():
    return UserProfile(
        user_id="usr_e2e",
        username="e2e_user",
        display_name="E2E Test",
        role=UserRole.ADMIN,
        enabled_toolsets=["terminal", "web", "tasks", "git", "memory_tools",
                          "skills", "system", "subagent"],
        created_at=datetime.now(timezone.utc),
    )
