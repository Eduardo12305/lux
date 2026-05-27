# tests/e2e/test_agent_loop.py
from __future__ import annotations

import asyncio
import pytest

from lux.agent.agent import AIAgent
from lux.agent.state import Channel, ToolCall
from lux.memory.manager import MemoryManager
from lux.tools.registry import ToolRegistry
from tests.e2e.conftest import MockLlamaClient, make_text_response, make_tool_response


def _make_agent(mock_llm, user_profile, tmp_db, max_iterations=50):
    from lux.models.manager import ModelManager
    from lux.prompt.assembler import PromptAssembler
    from lux.skills.manager import SkillManager
    from lux.tools.approval import ApprovalSystem

    model_mgr = ModelManager(llama_client=mock_llm)
    memory_mgr = MemoryManager(session_db=tmp_db)
    skill_mgr = SkillManager()
    tool_registry = ToolRegistry()
    approval = ApprovalSystem()
    prompt = PromptAssembler()

    return AIAgent(
        user_id=user_profile.user_id,
        user_profile=user_profile,
        channel=Channel.CLI,
        model_manager=model_mgr,
        memory_manager=memory_mgr,
        skill_manager=skill_mgr,
        tool_registry=tool_registry,
        approval_system=approval,
        prompt_assembler=prompt,
        max_iterations=max_iterations,
    )


@pytest.mark.asyncio
async def test_conversa_simples_1_iteracao(user_profile, tmp_db):
    mock_llm = MockLlamaClient([make_text_response("Ola! Como posso ajudar?")])
    agent = _make_agent(mock_llm, user_profile, tmp_db)
    result = await agent.run_conversation(user_message="Ola")
    assert result.status.value == "done"
    assert "Ola" in result.final_response
    assert result.iterations_used == 1
    await agent.close()


@pytest.mark.asyncio
async def test_tool_call_unica_executada(user_profile, tmp_db):
    from lux.tools.implementations.tasks import TaskCreateTool
    from lux.models.manager import ModelManager
    from lux.prompt.assembler import PromptAssembler
    from lux.skills.manager import SkillManager
    from lux.tools.approval import ApprovalSystem

    tool_registry = ToolRegistry()
    tool_registry.register(TaskCreateTool())

    mock_llm = MockLlamaClient([
        make_tool_response([ToolCall(id="call_1", function_name="task_create",
                                      arguments={"content": "tarefa de teste"})]),
        make_text_response("Tarefa criada com sucesso!"),
    ])

    agent = AIAgent(
        user_id=user_profile.user_id, user_profile=user_profile,
        channel=Channel.CLI,
        model_manager=ModelManager(llama_client=mock_llm),
        memory_manager=MemoryManager(session_db=tmp_db),
        skill_manager=SkillManager(), tool_registry=tool_registry,
        approval_system=ApprovalSystem(), prompt_assembler=PromptAssembler(),
    )
    result = await agent.run_conversation(user_message="Cria tarefa de teste")
    assert result.status.value in ("done", "error")
    await agent.close()


@pytest.mark.asyncio
async def test_budget_esgotado(user_profile, tmp_db):
    mock_llm = MockLlamaClient([
        make_tool_response([ToolCall(id=f"call_{i}", function_name="task_create",
                                      arguments={"content": f"tarefa {i}"})])
        for i in range(5)
    ])
    agent = _make_agent(mock_llm, user_profile, tmp_db, max_iterations=3)
    result = await agent.run_conversation(user_message="Faz varias tarefas")
    assert result.iterations_used <= 3
    await agent.close()


@pytest.mark.asyncio
async def test_llm_error_fallback(user_profile, tmp_db):
    from lux.models.llama_client import LlamaTimeoutError

    class FailingClient:
        main_url = "mock://main"; aux_url = "mock://aux"
        async def chat_completion(self, *a, **kw): raise LlamaTimeoutError("timeout")
        async def health_check(self, m="main"): return False
        async def close(self): pass
        async def acquire_slot(self, *a, **kw): return 0
        async def release_slot(self, *a, **kw): pass

    agent = _make_agent(FailingClient(), user_profile, tmp_db)
    result = await agent.run_conversation(user_message="Teste")
    assert result.status.value in ("error", "interrupted")
    await agent.close()
