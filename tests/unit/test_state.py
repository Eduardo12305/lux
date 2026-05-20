# tests/unit/test_state.py
# Módulo: Testes de State
# Status: IMPLEMENTADO

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from lux.agent.state import (
    AgentState,
    ApprovalPattern,
    ApprovalRequest,
    ApprovalResult,
    Channel,
    ConversationResult,
    Formality,
    Intent,
    ListeningMode,
    LLMResponse,
    MemoryAction,
    MemoryChunk,
    MemoryDelta,
    MemoryResult,
    MemoryTarget,
    MergedResult,
    Message,
    PipelineStatus,
    ResponseStyle,
    Role,
    SessionSearchResult,
    Skill,
    SkillMetadata,
    SkillSummary,
    StartupReport,
    SubagentTask,
    Task,
    TodoItem,
    ToolCall,
    ToolCallStatus,
    ToolResult,
    TrajectoryStep,
    UserProfile,
    UserRole,
)


# ── ToolCall ────────────────────────────────────────────────────────────────


def test_tool_call_defaults():
    tc = ToolCall()
    assert tc.id.startswith("call_")
    assert tc.status == ToolCallStatus.PENDING
    assert tc.arguments == {}


def test_tool_call_to_openai_dict():
    tc = ToolCall(
        id="call_abc123",
        function_name="shell_run",
        arguments={"command": "ls", "timeout_seconds": 10},
    )
    d = tc.to_openai_dict()
    assert d["id"] == "call_abc123"
    assert d["type"] == "function"
    assert d["function"]["name"] == "shell_run"
    import json

    args = json.loads(d["function"]["arguments"])
    assert args["command"] == "ls"


# ── ToolResult ──────────────────────────────────────────────────────────────


def test_tool_result_ok():
    r = ToolResult.ok("feito", tool_call_id="call_1")
    assert r.success is True
    assert r.output == "feito"
    assert r.error_message is None


def test_tool_result_error():
    r = ToolResult.failure("falhou", tool_call_id="call_1")
    assert r.success is False
    assert r.error_message == "falhou"


def test_tool_result_rejected():
    r = ToolResult.rejected("shell_run", tool_call_id="call_1")
    assert r.success is False
    assert "rejeitada" in r.error_message.lower()


def test_tool_result_timed_out():
    r = ToolResult.timed_out("shell_run", 30, tool_call_id="call_1")
    assert r.success is False
    assert "timeout" in r.error_message.lower()


def test_tool_result_to_string_ok():
    r = ToolResult.ok("saída do comando")
    assert r.to_string() == "saída do comando"


def test_tool_result_to_string_error():
    r = ToolResult.failure("erro fatal")
    assert r.to_string() == "ERRO: erro fatal"


def test_tool_result_to_string_empty_ok():
    r = ToolResult.ok("")
    assert r.to_string() == "OK"


# ── Message ─────────────────────────────────────────────────────────────────


def test_message_to_openai_dict_user():
    msg = Message(role=Role.USER, content="olá")
    d = msg.to_openai_dict()
    assert d == {"role": "user", "content": "olá"}


def test_message_to_openai_dict_assistant_with_tool_calls():
    tc = ToolCall(
        id="call_x", function_name="shell_run", arguments={"command": "ls"}
    )
    msg = Message(role=Role.ASSISTANT, content="", tool_calls=[tc])
    d = msg.to_openai_dict()
    assert d["role"] == "assistant"
    assert len(d["tool_calls"]) == 1
    assert d["tool_calls"][0]["id"] == "call_x"


def test_message_to_openai_dict_tool():
    msg = Message(
        role=Role.TOOL, tool_call_id="call_1", content="resultado do comando"
    )
    d = msg.to_openai_dict()
    assert d["role"] == "tool"
    assert d["tool_call_id"] == "call_1"
    assert d["content"] == "resultado do comando"


def test_message_to_openai_dict_tool_empty_content():
    msg = Message(role=Role.TOOL, tool_call_id="call_1")
    d = msg.to_openai_dict()
    assert d["content"] == ""


# ── LLMResponse ─────────────────────────────────────────────────────────────


def test_llm_response_has_tool_calls_false():
    resp = LLMResponse(content="resposta simples")
    assert resp.has_tool_calls is False


def test_llm_response_has_tool_calls_true():
    tc = ToolCall(function_name="shell_run")
    resp = LLMResponse(tool_calls=[tc])
    assert resp.has_tool_calls is True


def test_llm_response_from_raw():
    raw = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "resultado",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "shell_run",
                                "arguments": {"command": "ls"},
                            },
                        }
                    ],
                },
            }
        ],
        "model": "qwen3-14b",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    resp = LLMResponse.from_raw(raw)
    assert resp.content == "resultado"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].function_name == "shell_run"
    assert resp.model == "qwen3-14b"
    assert resp.tokens_prompt == 100
    assert resp.tokens_completion == 50


def test_llm_response_from_raw_no_tool_calls():
    raw = {
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "model": "qwen3-14b",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    resp = LLMResponse.from_raw(raw)
    assert resp.content == "ok"
    assert len(resp.tool_calls) == 0


def test_llm_response_from_raw_empty_choices():
    raw = {"choices": [], "model": "", "usage": {}}
    resp = LLMResponse.from_raw(raw)
    assert resp.content == ""
    assert len(resp.tool_calls) == 0


# ── AgentState ──────────────────────────────────────────────────────────────


def test_agent_state_to_openai_messages():
    state = AgentState(
        system_prompt_frozen="system prompt",
        conversation_history=[
            Message(role=Role.USER, content="user msg"),
            Message(role=Role.ASSISTANT, content="assistant msg"),
        ],
    )
    msgs = state.to_openai_messages()
    assert len(msgs) == 3
    assert msgs[0] == {"role": "system", "content": "system prompt"}
    assert msgs[1] == {"role": "user", "content": "user msg"}
    assert msgs[2] == {"role": "assistant", "content": "assistant msg"}


def test_agent_state_enforce_alternation():
    state = AgentState(
        conversation_history=[
            Message(role=Role.USER, content="msg1"),
            Message(role=Role.USER, content="msg2"),
            Message(role=Role.ASSISTANT, content="msg3"),
            Message(role=Role.ASSISTANT, content="msg4"),
        ]
    )
    state.enforce_alternation()
    assert len(state.conversation_history) == 2
    assert state.conversation_history[0].role == Role.USER
    assert "msg1" in state.conversation_history[0].content
    assert "msg2" in state.conversation_history[0].content
    assert state.conversation_history[1].role == Role.ASSISTANT
    assert "msg3" in state.conversation_history[1].content
    assert "msg4" in state.conversation_history[1].content


def test_agent_state_enforce_alternation_tool_messages_preserved():
    state = AgentState(
        conversation_history=[
            Message(role=Role.ASSISTANT, content="", tool_calls=[
                ToolCall(id="c1", function_name="x")
            ]),
            Message(role=Role.TOOL, tool_call_id="c1", content="r1"),
            Message(role=Role.TOOL, tool_call_id="c2", content="r2"),
        ]
    )
    state.enforce_alternation()
    assert len(state.conversation_history) == 3


def test_agent_state_enforce_alternation_system_merged():
    state = AgentState(
        conversation_history=[
            Message(role=Role.SYSTEM, content="sys1"),
            Message(role=Role.SYSTEM, content="sys2"),
        ]
    )
    state.enforce_alternation()
    assert len(state.conversation_history) == 1
    assert state.conversation_history[0].role == Role.SYSTEM


def test_agent_state_interrupt_event():
    state = AgentState()
    evt = state.interrupt_event
    assert isinstance(evt, asyncio.Event)
    assert not evt.is_set()
    evt2 = state.interrupt_event
    assert evt is evt2


def test_agent_state_defaults():
    state = AgentState()
    assert state.iteration == 0
    assert state.max_iterations == 50
    assert state.pipeline_status == PipelineStatus.IDLE
    assert state.agent_todos == []
    assert state.conversation_history == []


# ── UserProfile ─────────────────────────────────────────────────────────────


def test_user_profile_defaults():
    user = UserProfile()
    assert user.preferred_language == "pt-BR"
    assert user.response_style == ResponseStyle.BALANCED
    assert user.formality == Formality.CASUAL
    assert user.role == UserRole.USER
    assert user.timezone == "America/Sao_Paulo"
    assert len(user.enabled_toolsets) > 0


# ── Channel ─────────────────────────────────────────────────────────────────


def test_channel_streaming_support():
    assert Channel.CLI.supports_streaming is True
    assert Channel.TELEGRAM.supports_streaming is True
    assert Channel.DISCORD.supports_streaming is True
    assert Channel.SLACK.supports_streaming is False
    assert Channel.EMAIL.supports_streaming is False


# ── MemoryDelta ─────────────────────────────────────────────────────────────


def test_memory_delta_creation():
    delta = MemoryDelta(
        action=MemoryAction.ADD,
        target=MemoryTarget.MEMORY,
        content="nova entrada",
        user_id="user_1",
    )
    assert delta.action == MemoryAction.ADD
    assert delta.target == MemoryTarget.MEMORY
    assert delta.applied is False


# ── MemoryResult ────────────────────────────────────────────────────────────


def test_memory_result_ok():
    result = MemoryResult.ok("salvo", chars_used=100, chars_limit=2200)
    assert result.success is True
    assert result.chars_used == 100
    assert result.chars_limit == 2200


def test_memory_result_error():
    result = MemoryResult.failure("memória cheia", chars_used=2200, chars_limit=2200)
    assert result.success is False
    assert "cheia" in result.error_message


# ── MemoryChunk ─────────────────────────────────────────────────────────────


def test_memory_chunk_from_qdrant():
    hit = {
        "id": "abc",
        "score": 0.85,
        "payload": {
            "content": "texto recuperado",
            "session_id": "sess_1",
            "user_id": "user_1",
        },
    }
    chunk = MemoryChunk.from_qdrant(hit)
    assert chunk.id == "abc"
    assert chunk.score == 0.85
    assert chunk.content == "texto recuperado"
    assert chunk.source == "semantic"


# ── SessionSearchResult ─────────────────────────────────────────────────────


def test_session_search_result_from_row():
    row = ("msg_1", "sess_1", "2026-05-19T10:00:00", "user", "<b>hit</b>", 0.92)
    result = SessionSearchResult.from_row(row)
    assert result.id == "msg_1"
    assert result.session_id == "sess_1"
    assert result.score == 0.92
    assert result.source == "fts5"


# ── Skill / SkillSummary ────────────────────────────────────────────────────


def test_skill_summary_from_metadata():
    meta = SkillMetadata(
        name="deploy-docker",
        description="Deploy Docker",
        category="infra",
        platforms=["linux"],
        requires_toolsets=["terminal"],
    )
    s = SkillSummary.from_metadata(meta)
    assert s.name == "deploy-docker"
    assert s.category == "infra"


def test_skill_from_markdown_minimal():
    content = """---
name: test-skill
description: uma skill de teste
version: 1.0.0
---
# Test Skill

## Procedimento
Passo 1.
"""
    skill = Skill.from_markdown(content)
    assert skill.name == "test-skill"
    assert skill.description == "uma skill de teste"
    assert skill.metadata.name == "test-skill"


# ── Approval ────────────────────────────────────────────────────────────────


def test_approval_request_expiry():
    req = ApprovalRequest(
        tool_name="shell_run",
        command_preview="rm -rf /",
        timeout_seconds=1,
    )
    assert not req.is_expired()
    import time

    time.sleep(1.1)
    assert req.is_expired()


def test_approval_pattern():
    p = ApprovalPattern(
        label="git commit",
        regex=r"git commit",
        toolset="git",
        always_allow=True,
    )
    assert p.always_allow is True
    assert p.regex == r"git commit"


# ── SubagentTask ────────────────────────────────────────────────────────────


def test_subagent_task_defaults():
    t = SubagentTask(task="pesquisar X")
    assert t.max_iterations == 20
    assert t.status == "pending"


# ── TodoItem ────────────────────────────────────────────────────────────────


def test_todo_item():
    item = TodoItem(id=1, text="fazer algo")
    assert item.id == 1
    assert item.done is False


# ── ConversationResult ──────────────────────────────────────────────────────


def test_conversation_result():
    result = ConversationResult(
        final_response="tudo certo",
        session_id="sess_1",
        iterations_used=5,
        tokens_used=1200,
    )
    assert result.status == PipelineStatus.DONE
    assert result.pending_items == []


# ── StartupReport ───────────────────────────────────────────────────────────


def test_startup_report():
    report = StartupReport(success=True, startup_time_ms=1500.0)
    assert report.success is True
    assert report.warnings == []


# ── MergedResult ────────────────────────────────────────────────────────────


def test_merged_result():
    r = MergedResult(
        id="m1",
        content="resultado unificado",
        score=0.75,
        sources=["fts5", "semantic"],
    )
    assert len(r.sources) == 2
    assert r.score == 0.75
