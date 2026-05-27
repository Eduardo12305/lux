# tests/e2e/test_memory_persistence.py
# Cenário 2: Busca cross-session com FTS5 + MemoryManager frozen snapshot

from __future__ import annotations

import pytest

from lux.agent.state import Channel, Message, Role
from lux.memory.manager import MemoryManager
from lux.memory.session_db import SessionDB


@pytest.mark.asyncio
async def test_memory_frozen_snapshot(tmp_path):
    """Frozen snapshot: mudanças mid-session NÃO aparecem na mesma sessão."""
    mgr = MemoryManager(memories_dir=tmp_path / "mem")
    user_dir = tmp_path / "mem" / "u1"
    user_dir.mkdir(parents=True)
    (user_dir / "MEMORY.md").write_text("antes")

    snap_before, _ = await mgr.load_frozen_snapshot("u1")
    assert "antes" in snap_before

    from lux.agent.state import MemoryAction, MemoryTarget
    await mgr.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="depois", user_id="u1",
    )

    snap_after, _ = await mgr.load_frozen_snapshot("u1")
    assert "depois" in snap_after

    path = user_dir / "MEMORY.md"
    content = path.read_text()
    assert "antes" in content
    assert "depois" in content


@pytest.mark.asyncio
async def test_fts5_search_cross_session(tmp_path):
    """FTS5: busca retorna snippet relevante com marcação."""
    db = SessionDB(db_path=tmp_path / "fts5_test.db")
    await db.create_session("sess_1", "u1", Channel.CLI)

    msg = Message(
        id="msg_fts5_1", session_id="sess_1", user_id="u1",
        role=Role.USER, content="discutimos Rust ownership na semana passada",
    )
    await db.save_message(msg)

    results = await db.fts_search("Rust ownership", "u1", limit=5)
    assert len(results) >= 1
    assert any("Rust" in r.snippet for r in results)


@pytest.mark.asyncio
async def test_memory_add_and_remove(tmp_path):
    """MemoryManager: add + remove entrada corretamente."""
    mgr = MemoryManager(memories_dir=tmp_path / "mem2")
    from lux.agent.state import MemoryAction, MemoryTarget

    await mgr.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="entrada para remover", user_id="u1",
    )
    result = await mgr.apply_memory_action(
        MemoryAction.REMOVE, MemoryTarget.MEMORY,
        old_text="entrada para remover", user_id="u1",
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_memory_char_limit_enforced(tmp_path):
    """MemoryManager: add falha quando limite de chars excedido."""
    mgr = MemoryManager(memories_dir=tmp_path / "mem3")
    from lux.agent.state import MemoryAction, MemoryTarget

    fill = "x" * 2200
    await mgr.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY, content=fill, user_id="u1",
    )
    result = await mgr.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="overflow", user_id="u1",
    )
    assert result.success is False


@pytest.mark.asyncio
async def test_fts5_boolean_search(tmp_path):
    """FTS5: busca booleana (AND/OR) funciona."""
    db = SessionDB(db_path=tmp_path / "fts5_bool.db")
    await db.create_session("sess_1", "u1", Channel.CLI)

    await db.save_message(Message(
        id="mb1", session_id="sess_1", user_id="u1",
        role=Role.USER, content="erro no deploy do Docker com Kubernetes",
    ))
    await db.save_message(Message(
        id="mb2", session_id="sess_1", user_id="u1",
        role=Role.USER, content="deploy do frontend React",
    ))

    results = await db.fts_search("Docker AND Kubernetes", "u1", limit=5)
    assert len(results) >= 1

    results2 = await db.fts_search("Python AND Rust", "u1", limit=5)
    assert len(results2) == 0


@pytest.mark.asyncio
async def test_memory_replace_ambiguous(tmp_path):
    """MemoryManager: replace falha com substring ambígua."""
    mgr = MemoryManager(memories_dir=tmp_path / "mem4")
    from lux.agent.state import MemoryAction, MemoryTarget

    for entry in ["entrada alpha beta", "entrada alpha gamma"]:
        await mgr.apply_memory_action(
            MemoryAction.ADD, MemoryTarget.MEMORY,
            content=entry, user_id="u1",
        )

    result = await mgr.apply_memory_action(
        MemoryAction.REPLACE, MemoryTarget.MEMORY,
        content="nova", old_text="alpha", user_id="u1",
    )
    assert result.success is False
    assert "ambigua" in result.error_message.lower()
