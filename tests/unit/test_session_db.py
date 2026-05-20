# tests/unit/test_session_db.py
# Módulo: Testes de SessionDB
# Status: IMPLEMENTADO

from __future__ import annotations

import asyncio

import pytest

from lux.agent.state import Channel, Message, Role
from lux.memory.session_db import SessionDB

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def session_db(tmp_path):
    db = SessionDB(db_path=tmp_path / "test.db")
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_create_session(session_db):
    await session_db.create_session("sess_1", "user_1", Channel.CLI)
    row = await session_db.get_session("sess_1")
    assert row is not None
    assert row["user_id"] == "user_1"
    assert row["channel"] == "cli"


@pytest.mark.asyncio
async def test_create_child_session(session_db):
    await session_db.create_session("sess_1", "user_1", Channel.CLI)
    child_id = await session_db.create_child_session(
        "sess_1", "resumo da compressao", 20
    )
    child = await session_db.get_session(child_id)
    assert child is not None
    assert child["parent_id"] == "sess_1"
    assert child["compressed"] == 1


@pytest.mark.asyncio
async def test_save_and_load_message(session_db):
    await session_db.create_session("sess_1", "user_1", Channel.CLI)
    msg = Message(
        id="msg_1",
        session_id="sess_1",
        user_id="user_1",
        role=Role.USER,
        content="ola mundo",
    )
    await session_db.save_message(msg)
    history = await session_db.load_history("sess_1")
    assert len(history) == 1
    assert history[0].content == "ola mundo"


@pytest.mark.asyncio
async def test_fts_search(session_db):
    await session_db.create_session("sess_1", "user_1", Channel.CLI)
    msg = Message(
        id="msg_1",
        session_id="sess_1",
        user_id="user_1",
        role=Role.USER,
        content="busca textual para teste",
    )
    await session_db.save_message(msg)
    results = await session_db.fts_search("textual", "user_1", limit=5)
    assert len(results) >= 1
    assert any("textual" in r.snippet.lower() for r in results)


@pytest.mark.asyncio
async def test_fts_search_no_match(session_db):
    await session_db.create_session("sess_1", "user_1", Channel.CLI)
    results = await session_db.fts_search("inexistente_xyz", "user_1", limit=5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_save_messages_batch(session_db):
    await session_db.create_session("sess_1", "user_1", Channel.CLI)
    msgs = [
        Message(id=f"msg_{i}", session_id="sess_1", user_id="user_1",
                role=Role.USER, content=f"msg {i}")
        for i in range(3)
    ]
    await session_db.save_messages(msgs)
    history = await session_db.load_history("sess_1")
    assert len(history) == 3


@pytest.mark.asyncio
async def test_end_session(session_db):
    await session_db.create_session("sess_1", "user_1", Channel.CLI)
    await session_db.end_session("sess_1", tokens_used=500)
    row = await session_db.get_session("sess_1")
    assert row["ended_at"] is not None
