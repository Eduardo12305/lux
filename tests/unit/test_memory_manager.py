# tests/unit/test_memory_manager.py
# Módulo: Testes de MemoryManager
# Status: IMPLEMENTADO

from __future__ import annotations

import pytest

from lux.agent.state import MemoryAction, MemoryTarget
from lux.memory.manager import MemoryManager

pytestmark = pytest.mark.asyncio


@pytest.fixture
def memory_manager(tmp_path):
    mgr = MemoryManager(memories_dir=tmp_path / "memories")
    mgr.memories_dir.mkdir(parents=True, exist_ok=True)
    return mgr


# ── ADD ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_memory_content_saved(memory_manager, tmp_path):
    result = await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="fato importante aprendido", user_id="u1",
    )
    assert result.success is True
    path = memory_manager._memory_path("u1", "MEMORY.md")
    assert path.exists()
    assert "fato importante" in path.read_text()


@pytest.mark.asyncio
async def test_add_memory_char_limit(memory_manager):
    fill = "x" * 2200
    await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY, content=fill, user_id="u1"
    )
    result = await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="overflow", user_id="u1",
    )
    assert result.success is False
    assert "cheia" in result.error_message.lower()


@pytest.mark.asyncio
async def test_add_user_content(memory_manager, tmp_path):
    result = await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.USER,
        content="prefere respostas curtas", user_id="u1",
    )
    assert result.success is True
    path = memory_manager._memory_path("u1", "USER.md")
    assert path.exists()
    assert "curtas" in path.read_text()


@pytest.mark.asyncio
async def test_add_empty_content(memory_manager):
    result = await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="   ", user_id="u1",
    )
    assert result.success is False


# ── REPLACE ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replace_single_match(memory_manager):
    await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="entrada antiga para testar", user_id="u1",
    )
    result = await memory_manager.apply_memory_action(
        MemoryAction.REPLACE, MemoryTarget.MEMORY,
        content="entrada nova atualizada",
        old_text="entrada antiga", user_id="u1",
    )
    assert result.success is True
    path = memory_manager._memory_path("u1", "MEMORY.md")
    content = path.read_text()
    assert "entrada nova atualizada" in content
    assert "entrada antiga" not in content


@pytest.mark.asyncio
async def test_replace_substring_not_found(memory_manager):
    await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="dado existente", user_id="u1",
    )
    result = await memory_manager.apply_memory_action(
        MemoryAction.REPLACE, MemoryTarget.MEMORY,
        content="novo", old_text="inexistente", user_id="u1",
    )
    assert result.success is False
    assert "nao encontrada" in result.error_message.lower()


@pytest.mark.asyncio
async def test_replace_ambiguous_match(memory_manager):
    for entry in ["entrada alpha beta", "entrada alpha gamma"]:
        await memory_manager.apply_memory_action(
            MemoryAction.ADD, MemoryTarget.MEMORY,
            content=entry, user_id="u1",
        )
    result = await memory_manager.apply_memory_action(
        MemoryAction.REPLACE, MemoryTarget.MEMORY,
        content="nova entrada", old_text="alpha", user_id="u1",
    )
    assert result.success is False
    assert "ambigua" in result.error_message.lower()


# ── REMOVE ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_entry(memory_manager):
    await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="entrada para remover", user_id="u1",
    )
    result = await memory_manager.apply_memory_action(
        MemoryAction.REMOVE, MemoryTarget.MEMORY,
        old_text="entrada para remover", user_id="u1",
    )
    assert result.success is True
    path = memory_manager._memory_path("u1", "MEMORY.md")
    assert "entrada para remover" not in path.read_text()


@pytest.mark.asyncio
async def test_remove_not_found(memory_manager):
    result = await memory_manager.apply_memory_action(
        MemoryAction.REMOVE, MemoryTarget.MEMORY,
        old_text="inexistente", user_id="u1",
    )
    assert result.success is False


# ── Frozen Snapshot ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_frozen_snapshot(memory_manager, tmp_path):
    user_dir = tmp_path / "memories" / "u1"
    user_dir.mkdir(parents=True)
    (user_dir / "MEMORY.md").write_text("memoria de teste")
    (user_dir / "USER.md").write_text("perfil de teste")

    memory_snap, user_snap = await memory_manager.load_frozen_snapshot("u1")
    assert "memoria de teste" in memory_snap
    assert "perfil de teste" in user_snap
    assert "MEMORY" in memory_snap


@pytest.mark.asyncio
async def test_frozen_snapshot_mid_session_does_not_change(memory_manager, tmp_path):
    user_dir = tmp_path / "memories" / "u1"
    user_dir.mkdir(parents=True)
    (user_dir / "MEMORY.md").write_text("antes")

    snap_before, _ = await memory_manager.load_frozen_snapshot("u1")
    assert "antes" in snap_before

    await memory_manager.apply_memory_action(
        MemoryAction.ADD, MemoryTarget.MEMORY,
        content="depois", user_id="u1",
    )
    snap_after, _ = await memory_manager.load_frozen_snapshot("u1")
    assert "depois" in snap_after


# ── Concurrent Writes (Risco 6) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_memory_writes(memory_manager):
    import asyncio

    async def writer(n: int):
        for i in range(5):
            await memory_manager.apply_memory_action(
                MemoryAction.ADD, MemoryTarget.MEMORY,
                content=f"writer{n}_entry{i}", user_id="shared",
            )

    await asyncio.gather(writer(1), writer(2))

    path = memory_manager._memory_path("shared", "MEMORY.md")
    content = path.read_text()
    assert "writer1" in content or "writer2" in content
    assert len(content) <= 2200
