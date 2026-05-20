# tests/unit/test_llama_client.py
# Módulo: Testes de LlamaClient
# Status: IMPLEMENTADO

from __future__ import annotations

import asyncio

import pytest

from lux.agent.state import RequestPriority
from lux.models.llama_client import (
    CircuitBreaker,
    CircuitState,
    LlamaClient,
    LlamaClientError,
    LlamaTimeoutError,
    ThinkingParser,
)


# ── ThinkingParser (GAP 4) ─────────────────────────────────────────────────


def test_thinking_parser_simple():
    parser = ThinkingParser()
    thinking, content = parser.feed("<think>hello</think>")
    assert thinking == "hello"
    assert content is None


def test_thinking_parser_tokens_splitted():
    parser = ThinkingParser()
    t1, c1 = parser.feed("<th")
    assert t1 is None and c1 is None
    t2, c2 = parser.feed("ink>")
    assert t2 is None and c2 is None
    t3, c3 = parser.feed("world")
    assert t3 == "world"


def test_thinking_parser_close_tag_splitted():
    parser = ThinkingParser()
    parser.feed("<think>inside")
    t1, c1 = parser.feed("</")
    assert t1 is None and c1 is None
    t2, c2 = parser.feed("think>")
    assert t2 is None and c2 is None
    t3, c3 = parser.feed("after")
    assert t3 is None
    assert c3 == "after"


def test_thinking_parser_no_thinking():
    parser = ThinkingParser()
    t, c = parser.feed("just normal text")
    assert t is None
    assert c == "just normal text"


def test_thinking_parser_less_than_inside_thinking():
    parser = ThinkingParser()
    t1, c1 = parser.feed("<think>compare: a < b and c > d")
    assert t1 == "compare: a < b and c > d"
    assert c1 is None
    t2, c2 = parser.feed("</think>done")
    assert t2 is None
    assert c2 == "done"


def test_thinking_parser_less_than_not_think():
    parser = ThinkingParser()
    t, c = parser.feed("x < 10 and ")
    assert t is None
    assert c == "x < 10 and "


def test_thinking_parser_flush_partial():
    parser = ThinkingParser()
    t1, c1 = parser.feed("<think>unfinished")
    assert t1 == "unfinished"
    thinking, content = parser.flush()
    assert thinking == ""
    assert content == ""


def test_thinking_parser_flush_partial_close():
    parser = ThinkingParser()
    t1, c1 = parser.feed("<think>almost</thi")
    assert t1 == "almost"
    thinking, content = parser.flush()
    assert thinking == "</thi"


def test_thinking_parser_multiple_thinking_blocks():
    parser = ThinkingParser()
    t1, c1 = parser.feed("<think>first</think>")
    assert t1 == "first"
    t2, c2 = parser.feed("middle")
    assert t2 is None
    assert c2 == "middle"
    t3, c3 = parser.feed("<think>second</think>end")
    assert t3 == "second"
    assert c3 == "end"


def test_thinking_parser_lookahead_partial_open_tag():
    parser = ThinkingParser()
    t, c = parser.feed("<th")
    assert t is None and c is None
    t, c = parser.feed("is")
    assert t is None
    assert c == "<this"


# ── CircuitBreaker ──────────────────────────────────────────────────────────


def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_circuit_breaker_records_success():
    cb = CircuitBreaker()
    cb.record_failure()
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_half_open_after_timeout():
    import time
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False
    time.sleep(0.02)
    assert cb.allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN


# ── LlamaClient (Mock) ─────────────────────────────────────────────────────


class MockResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json

    @property
    def text(self):
        import json
        return json.dumps(self._json)


@pytest.fixture
def llama_client():
    return LlamaClient(
        main_url="http://127.0.0.1:9999",
        aux_url="http://127.0.0.1:9998",
        main_parallel_slots=2,
        aux_parallel_slots=4,
    )


def test_url_for_model_main(llama_client):
    assert llama_client._url_for_model("main") == "http://127.0.0.1:9999"
    assert llama_client._url_for_model("qwen3-14b-q4") == "http://127.0.0.1:9999"


def test_url_for_model_aux(llama_client):
    assert llama_client._url_for_model("aux") == "http://127.0.0.1:9998"
    assert llama_client._url_for_model("qwen3-1.7b-q4") == "http://127.0.0.1:9998"
    assert llama_client._url_for_model("fast-model") == "http://127.0.0.1:9998"


@pytest.mark.asyncio
async def test_acquire_slot(llama_client):
    slot = await llama_client.acquire_slot("session_1", "main")
    assert slot == 0


@pytest.mark.asyncio
async def test_acquire_slot_same_session_returns_same(llama_client):
    slot1 = await llama_client.acquire_slot("session_1", "main")
    slot2 = await llama_client.acquire_slot("session_1", "main")
    assert slot1 == slot2


@pytest.mark.asyncio
async def test_acquire_slot_different_sessions(llama_client):
    slot1 = await llama_client.acquire_slot("session_1", "main")
    slot2 = await llama_client.acquire_slot("session_2", "main")
    assert slot1 != slot2


@pytest.mark.asyncio
async def test_release_slot(llama_client):
    slot = await llama_client.acquire_slot("session_1", "main")
    await llama_client.release_slot("session_1", "main")
    assert "session_1" not in llama_client._slot_sessions


@pytest.mark.asyncio
async def test_acquire_slot_race_condition_gap3(llama_client):
    """
    GAP 3: Dois coroutines da mesma sessao chamando acquire_slot
    simultaneamente devem retornar o mesmo slot_id.
    """
    slot_holder = {}

    async def acquire(session_id):
        slot_holder[session_id] = await llama_client.acquire_slot(session_id, "main")

    await asyncio.gather(
        acquire("session_shared"),
        acquire("session_shared"),
    )
    assert slot_holder["session_shared"] == llama_client._slot_sessions["session_shared"]


@pytest.mark.asyncio
async def test_parse_thinking(llama_client):
    thinking, content = llama_client._parse_thinking(
        "<think>raciocinio interno</think>resposta visivel"
    )
    assert thinking == "raciocinio interno"
    assert content == "resposta visivel"


@pytest.mark.asyncio
async def test_parse_thinking_no_thinking(llama_client):
    thinking, content = llama_client._parse_thinking("sem thinking")
    assert thinking is None
    assert content == "sem thinking"


@pytest.mark.asyncio
async def test_close(llama_client):
    await llama_client.close()
    assert llama_client._client is None
