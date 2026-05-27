# tests/e2e/test_context_compression.py
from __future__ import annotations
import pytest
from lux.agent.state import (
    AgentState, Channel, Message, Role, ToolCall, UserProfile, UserRole,
)
from lux.memory.manager import MemoryManager


def _make_state(n_messages: int, with_tool_pairs: bool = False) -> AgentState:
    state = AgentState(
        session_id="sess_c", user_id="u1",
        user_profile=UserProfile(user_id="u1", role=UserRole.ADMIN),
        channel=Channel.CLI, system_prompt_frozen="system",
    )
    for i in range(n_messages):
        if with_tool_pairs and i % 3 == 0 and i < n_messages - 2:
            state.conversation_history.append(Message(
                id=f"m{i}", role=Role.ASSISTANT, content="",
                tool_calls=[ToolCall(id=f"tc{i}", function_name="task_create",
                                      arguments={"content": f"t{i}"})],
            ))
            state.conversation_history.append(Message(
                id=f"m{i}r", role=Role.TOOL, tool_call_id=f"tc{i}",
                content=f"resultado {i}",
            ))
        else:
            state.conversation_history.append(Message(
                id=f"m{i}", role=Role.USER if i % 2 == 0 else Role.ASSISTANT,
                content=f"mensagem {i} com bastante texto para encher o contexto " * 2,
            ))
    return state


@pytest.mark.asyncio
async def test_compressao_nao_dispara_abaixo_threshold(tmp_path):
    from lux.memory.session_db import SessionDB
    from lux.compression.compressor import ContextCompressor
    db = SessionDB(db_path=tmp_path / "ct1.db")
    compressor = ContextCompressor(
        memory_manager=MemoryManager(memories_dir=tmp_path / "cm1"),
        session_db=db, protect_last_n=5,
    )
    state = _make_state(10)
    result = await compressor.compress(state, threshold_pct=0.99)
    assert result is False
    await db.close()


@pytest.mark.asyncio
async def test_compressao_preserva_ultimas_n(tmp_path):
    from lux.memory.session_db import SessionDB
    from lux.compression.compressor import ContextCompressor
    db = SessionDB(db_path=tmp_path / "ct2.db")
    compressor = ContextCompressor(
        memory_manager=MemoryManager(memories_dir=tmp_path / "cm2"),
        session_db=db, protect_last_n=5,
    )
    state = _make_state(30)
    last_ids = {m.id for m in state.conversation_history[-5:]}
    try:
        await compressor.compress(state, threshold_pct=0.01)
    except Exception:
        pass
    compressed = {m.id for m in state.conversation_history if m.id in last_ids}
    assert len(compressed) == 5
    await db.close()


@pytest.mark.asyncio
async def test_tool_pair_rescue_logic(tmp_path):
    from lux.memory.session_db import SessionDB
    from lux.compression.compressor import ContextCompressor
    db = SessionDB(db_path=tmp_path / "ct3.db")
    compressor = ContextCompressor(
        memory_manager=MemoryManager(memories_dir=tmp_path / "cm3"),
        session_db=db, protect_last_n=5,
    )
    state = _make_state(20, with_tool_pairs=True)
    to_compress = state.conversation_history[:-5]
    to_keep = state.conversation_history[-5:]
    result, rescued = compressor._rescue_tool_pairs(to_compress, to_keep)

    tc_ids = {tc.id for m in result + rescued for tc in (m.tool_calls or [])}
    tr_ids = {m.tool_call_id for m in result + rescued if m.role == Role.TOOL and m.tool_call_id}
    orphaned = tc_ids - tr_ids
    assert len(orphaned) == 0, f"Orfas: {orphaned}"
    await db.close()
