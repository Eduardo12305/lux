# lux/agent/agent.py
# Módulo: Agent Core
# Dependências: state, models, memory, prompt, skills, compression, tools
# Status: IMPLEMENTADO
# Notas: Loop principal do Lux. ~2000 linhas implementadas em ordem interna.

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional
from uuid import uuid4

from lux.agent.auxiliary_client import AuxiliaryLLMClient
from lux.agent.budget import IterationBudget
from lux.agent.model_router import ModelRouter
from lux.agent.state import (
    AgentState,
    ApprovalRequest,
    Channel,
    ConversationResult,
    LLMResponse,
    MemoryAction,
    MemoryDelta,
    MemoryTarget,
    Message,
    PipelineStatus,
    Role,
    SubagentTask,
    Task,
    ToolCall,
    ToolCallStatus,
    ToolResult,
    UserProfile,
)
from lux.agent.trajectory import TrajectorySaver
from lux.compression.compressor import ContextCompressor
from lux.config import get_config
from lux.memory.manager import MemoryManager
from lux.memory.nudge import MemoryNudgeSystem, SkillNudgeSystem
from lux.memory.session_db import SessionDB
from lux.models.llama_client import (
    AgentInterruptedException,
    LlamaClient,
    LlamaTimeoutError,
)
from lux.models.manager import ModelManager
from lux.prompt.assembler import PromptAssembler
from lux.prompt.context_files import ContextFileLoader
from lux.prompt.soul import SoulLoader
from lux.skills.creator import SkillCreator
from lux.skills.manager import SkillManager
from lux.tools.approval import ApprovalSystem
from lux.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

INTERACTIVE_TOOLS = {"clarify", "approve", "ask_user"}


class AIAgent:
    """Motor central do Lux. Orquestra todo o agent loop."""

    def __init__(
        self,
        user_id: str = "",
        session_id: str = "",
        user_profile: Optional[UserProfile] = None,
        channel: Channel = Channel.CLI,
        is_subagent: bool = False,
        parent_task_id: Optional[str] = None,
        max_iterations: int = 50,
        compression_threshold: float = 0.50,
        enabled_toolsets: Optional[list[str]] = None,
        model_manager: Optional[ModelManager] = None,
        memory_manager: Optional[MemoryManager] = None,
        skill_manager: Optional[SkillManager] = None,
        tool_registry: Optional[ToolRegistry] = None,
        approval_system: Optional[ApprovalSystem] = None,
        prompt_assembler: Optional[PromptAssembler] = None,
    ):
        config = get_config()
        self.user_id = user_id
        self.session_id = session_id or uuid4().hex
        self._channel = channel
        self._is_subagent = is_subagent
        self._parent_task_id = parent_task_id
        self._max_iterations = max_iterations
        self._compression_threshold = compression_threshold
        self._enabled_toolsets = enabled_toolsets

        self._model_mgr = model_manager or ModelManager.get_instance()
        self._memory_mgr = memory_manager or MemoryManager()
        self._skill_mgr = skill_manager or SkillManager()
        self._tool_registry = tool_registry or ToolRegistry()
        self._approval = approval_system or ApprovalSystem()
        self._router = ModelRouter()
        self._budget = IterationBudget(max_iterations=self._max_iterations)
        self._context_loader = ContextFileLoader()
        self._soul_loader = SoulLoader()
        self._nudge = MemoryNudgeSystem()
        self._skill_nudge = SkillNudgeSystem()
        self._compressor = ContextCompressor(
            memory_manager=self._memory_mgr,
            session_db=self._memory_mgr.session_db,
            protect_last_n=config.protect_last_n,
        )
        self._trajectory = TrajectorySaver(self._memory_mgr.session_db)
        self._aux_client = AuxiliaryLLMClient(self._model_mgr.llama, self._router)

        self._prompt_assembler = prompt_assembler or PromptAssembler(
            skill_list_provider=self._skill_mgr,
            tool_schema_provider=self._tool_registry,
            soul_loader=self._soul_loader,
        )

        self.state: Optional[AgentState] = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._injected_skills: set[str] = set()

    # ── Public Interface ──────────────────────────────────────────────────

    def chat(self, message: str, **kwargs) -> str:
        result = asyncio.run(self.run_conversation(user_message=message, **kwargs))
        return result.final_response

    async def run_conversation(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        conversation_history: Optional[list] = None,
        task_id: Optional[str] = None,
        max_iterations: Optional[int] = None,
        enable_thinking: bool = False,
    ) -> ConversationResult:
        if max_iterations:
            self._max_iterations = max_iterations
            self._budget = IterationBudget(max_iterations=max_iterations)

        self._injected_skills.clear()

        state = await self._init_state(
            user_message=user_message,
            system_message=system_message,
            conversation_history=conversation_history,
            task_id=task_id,
        )
        self.state = state

        try:
            return await self._agent_loop(state)
        except Exception as e:
            logger.exception("Erro fatal no agent loop")
            return ConversationResult(
                final_response=f"Erro interno: {e}",
                session_id=state.session_id,
                status=PipelineStatus.ERROR,
                error=str(e),
            )
        finally:
            await self._cleanup(state)

    async def run_conversation_stream(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        conversation_history: Optional[list] = None,
        task_id: Optional[str] = None,
        max_iterations: Optional[int] = None,
    ):
        """Versao streaming: yield cada token conforme o LLM gera."""
        if max_iterations:
            self._max_iterations = max_iterations
            self._budget = IterationBudget(max_iterations=max_iterations)

        self._injected_skills.clear()

        state = await self._init_state(
            user_message=user_message,
            system_message=system_message,
            conversation_history=conversation_history,
            task_id=task_id,
        )
        self.state = state

        try:
            while not self._budget.is_exhausted:
                if state.interrupt_event.is_set():
                    yield "[INTERROMPIDO]"
                    return

                if self._needs_preflight_compression(state):
                    await self._compressor.compress(state, self._compression_threshold)

                api_messages = state.to_openai_messages()

                skill_context = self._get_skill_context(state, api_messages)
                if skill_context:
                    api_messages.insert(
                        1, {"role": "system", "content": skill_context}
                    )

                tools = self._tool_registry.get_active_schemas(
                    state.user_profile, state.user_profile.enabled_toolsets,
                )

                task_config = self._router.get_config(Task.CONVERSATION)

                full_response = []
                try:
                    async for token in self._model_mgr.llama.chat_completion_stream(
                        messages=api_messages,
                        model=task_config.model,
                        temperature=task_config.temperature,
                        max_tokens=task_config.max_tokens,
                        tools=tools if tools else None,
                        session_id=state.session_id,
                    ):
                        full_response.append(token)
                        yield token
                except Exception as e:
                    logger.exception("Erro no streaming")
                    yield f"\n[ERRO: {e}]"
                    return

                self._budget.consume()
                state.iteration += 1

                llm_response = LLMResponse(
                    content="".join(full_response),
                    model=task_config.model,
                    finish_reason="stop",
                    tokens_prompt=0,
                    tokens_completion=len(full_response),
                )

                if llm_response.tool_calls:
                    await self._execute_tool_calls(llm_response.tool_calls, state)
                    continue

                await self._finalize(state, llm_response)
                return

        finally:
            await self._cleanup(state)

    # ── 55.1 _init_state ─────────────────────────────────────────────────

    async def _init_state(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        conversation_history: Optional[list] = None,
        task_id: Optional[str] = None,
    ) -> AgentState:
        user_profile = UserProfile(
            user_id=self.user_id,
            username=self.user_id,
            display_name=self.user_id,
            enabled_toolsets=self._enabled_toolsets
            or [
                "terminal",
                "web",
                "tasks",
                "calendar",
                "memory_tools",
                "skills",
                "system",
                "git",
            ],
        )

        memory_snap, user_snap = await self._memory_mgr.load_frozen_snapshot(
            self.user_id
        )

        context_files = self._context_loader.load_for_workspace(
            get_config().lux_home
        )

        state = AgentState(
            task_id=task_id or uuid4().hex,
            session_id=self.session_id,
            user_id=self.user_id,
            user_profile=user_profile,
            channel=self._channel,
            memory_snapshot=memory_snap,
            user_snapshot=user_snap,
            context_files=context_files,
            max_iterations=self._max_iterations,
            is_subagent=self._is_subagent,
            parent_task_id=self._parent_task_id,
        )

        system_prompt = self._prompt_assembler.build_system_prompt(state)
        state.system_prompt_frozen = system_prompt

        user_msg = Message(
            role=Role.USER,
            content=user_message,
            session_id=state.session_id,
            user_id=self.user_id,
        )
        state.conversation_history.append(user_msg)

        if conversation_history:
            for h in conversation_history:
                if isinstance(h, dict):
                    state.conversation_history.insert(
                        0,
                        Message(
                            role=Role(h.get("role", "user")),
                            content=h.get("content", ""),
                            session_id=state.session_id,
                            user_id=self.user_id,
                        ),
                    )
                elif isinstance(h, Message):
                    state.conversation_history.insert(0, h)

        state.enforce_alternation()
        return state

    # ── 55.9 _agent_loop ─────────────────────────────────────────────────

    def _get_skill_context(
        self, state: AgentState, api_messages: list[dict]
    ) -> str | None:
        """Escaneia a conversa por referências a skills e injeta L1."""
        if not self._skill_mgr:
            return None

        available = self._skill_mgr.get_skills_list_l0(
            state.user_profile, state.channel
        )
        skill_names = {s.name for s in available}

        combined_text = " ".join(
            m.get("content", "") for m in api_messages
            if isinstance(m.get("content"), str)
        ).lower()

        for name in skill_names:
            if name in self._injected_skills:
                continue
            if name.replace("-", " ") in combined_text or name in combined_text:
                try:
                    content = self._skill_mgr.get_skill_content_l1(name)
                    if content:
                        self._injected_skills.add(name)
                        return (
                            f"[SKILL CONTEXT — Siga estas instruções]\n\n"
                            f"{content}\n\n"
                            f"Use esta skill para a tarefa atual quando aplicável."
                        )
                except FileNotFoundError:
                    continue
        return None

    async def _agent_loop(self, state: AgentState) -> ConversationResult:
        while not self._budget.is_exhausted:
            if state.interrupt_event.is_set():
                return self._build_interrupted_result(state)

            budget_warning = self._get_budget_warning()

            if self._needs_preflight_compression(state):
                await self._compressor.compress(
                    state, self._compression_threshold
                )

            api_messages = state.to_openai_messages()
            if budget_warning:
                api_messages.append(
                    {"role": "user", "content": budget_warning}
                )

            memory_nudge = self._nudge.maybe_inject_nudge(state)
            if memory_nudge:
                api_messages.append({"role": "user", "content": memory_nudge})

            skill_nudge = self._skill_nudge.maybe_inject_nudge(state)
            if skill_nudge:
                api_messages.append({"role": "user", "content": skill_nudge})

            skill_context = self._get_skill_context(state, api_messages)
            if skill_context:
                api_messages.insert(
                    1, {"role": "system", "content": skill_context}
                )

            task_config = self._router.get_config(
                Task.CONVERSATION_DEEP
                if len(api_messages) > 20
                else Task.CONVERSATION
            )

            has_pending_tools = bool(state.current_tool_calls)
            enable_thinking = not has_pending_tools

            try:
                llm_response = await self._interruptible_llm_call(
                    messages=api_messages,
                    tools=self._tool_registry.get_active_schemas(
                        state.user_profile,
                        state.user_profile.enabled_toolsets,
                    ),
                    model=task_config.model,
                    temperature=task_config.temperature,
                    enable_thinking=enable_thinking,
                    session_id=state.session_id,
                )
            except AgentInterruptedException:
                return self._build_interrupted_result(state)
            except LlamaTimeoutError:
                state.error = "Timeout do LLM"
                return self._build_error_result(state)

            self._budget.consume()
            state.iteration += 1

            self._trajectory.record_step(state, llm_response)

            if llm_response.tool_calls:
                self._skill_nudge.track_tool_call()
                await self._execute_tool_calls(llm_response.tool_calls, state)
                continue

            state.pipeline_status = PipelineStatus.FINALIZING
            await self._finalize(state, llm_response)

            return ConversationResult(
                final_response=llm_response.content,
                messages=list(state.conversation_history),
                session_id=state.session_id,
                iterations_used=state.iteration,
                tokens_used=llm_response.tokens_prompt + llm_response.tokens_completion,
                compressed_count=state.compression_count,
                status=PipelineStatus.DONE,
            )

        return self._build_budget_exhausted_result(state)

    # ── 55.2 _interruptible_llm_call ─────────────────────────────────────

    async def _interruptible_llm_call(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        enable_thinking: bool = False,
        session_id: str = "",
    ) -> LLMResponse:
        return await self._model_mgr.llama.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools if tools else None,
            enable_thinking=enable_thinking,
            session_id=session_id or self.session_id,
        )

    # ── 55.4 _execute_tool_calls ─────────────────────────────────────────

    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        state: AgentState,
    ):
        interactive = [
            tc for tc in tool_calls if tc.function_name in INTERACTIVE_TOOLS
        ]
        parallel = [
            tc for tc in tool_calls if tc.function_name not in INTERACTIVE_TOOLS
        ]

        results: dict[str, ToolResult] = {}

        if parallel:
            loop = asyncio.get_event_loop()
            futures = {
                loop.run_in_executor(
                    self._executor, self._execute_single_tool_sync, tc, state
                ): tc.id
                for tc in parallel
            }
            for future in as_completed(futures):
                tc_id = futures[future]
                try:
                    results[tc_id] = future.result(timeout=300)
                except Exception as e:
                    results[tc_id] = ToolResult.failure(
                        str(e), tool_call_id=tc_id
                    )

        for tc in interactive:
            results[tc.id] = await self._execute_single_tool_async(tc, state)

        for tc in tool_calls:
            result = results.get(tc.id, ToolResult.failure("Resultado nao encontrado"))
            result_msg = Message(
                role=Role.TOOL,
                tool_call_id=tc.id,
                content=result.to_string(),
                session_id=state.session_id,
                user_id=state.user_id,
            )
            state.conversation_history.append(result_msg)
            state.tool_results.append(result)

    def _execute_single_tool_sync(
        self, tool_call: ToolCall, state: AgentState
    ) -> ToolResult:
        return self._execute_single_tool(tool_call, state)

    async def _execute_single_tool_async(
        self, tool_call: ToolCall, state: AgentState
    ) -> ToolResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self._execute_single_tool, tool_call, state
        )

    # ── 55.3 _execute_single_tool ────────────────────────────────────────

    def _execute_single_tool(
        self, tool_call: ToolCall, state: AgentState
    ) -> ToolResult:
        fn_name = tool_call.function_name
        args = tool_call.arguments

        if fn_name == "memory":
            return self._handle_memory_tool(args, state)
        if fn_name == "session_search":
            return self._handle_session_search(args, state)
        if fn_name == "delegate_task":
            return self._handle_delegation(args, state)

        if self._approval.requires_approval(fn_name, args, state):
            approval_result = self._approval.request_approval(
                fn_name, args, state
            )
            if not approval_result.approved:
                return ToolResult.rejected(fn_name)

        return self._tool_registry.execute(fn_name, args, state)

    # ── Agent-Level Tools ────────────────────────────────────────────────

    def _handle_memory_tool(self, args: dict, state: AgentState) -> ToolResult:
        action_str = args.get("action", "add")
        target_str = args.get("target", "memory")
        content = args.get("content", "")
        old_text = args.get("old_text", "")

        try:
            action = MemoryAction(action_str)
        except ValueError:
            return ToolResult.failure(f"Acao invalida: {action_str}")

        try:
            target = MemoryTarget(target_str)
        except ValueError:
            return ToolResult.failure(f"Target invalido: {target_str}")

        loop = asyncio.get_event_loop()
        mem_result = loop.run_until_complete(
            self._memory_mgr.apply_memory_action(
                action=action,
                target=target,
                content=content,
                old_text=old_text if old_text else None,
                user_id=state.user_id,
            )
        )

        if mem_result.success:
            return ToolResult.ok(mem_result.message)
        return ToolResult.failure(mem_result.error_message or "Falha na memoria")

    def _handle_session_search(self, args: dict, state: AgentState) -> ToolResult:
        query = args.get("query", "")
        limit = args.get("limit", 5)
        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(
            self._memory_mgr.session_search(query, state.user_id, limit)
        )
        if not results:
            return ToolResult.ok("Nenhum resultado encontrado.")
        output = "\n".join(
            f"[{r.score:.2f}] {r.snippet} (sessao: {r.session_id[:8]}...)"
            for r in results
        )
        return ToolResult.ok(output)

    def _handle_delegation(self, args: dict, state: AgentState) -> ToolResult:
        task = args.get("task", "")
        toolsets = args.get("toolsets", [])
        sub_max = min(args.get("max_iterations", 20), state.max_iterations - state.iteration)
        if sub_max <= 0:
            return ToolResult.failure("Budget esgotado — nao e possivel delegar.")

        loop = asyncio.get_event_loop()
        sub_task = SubagentTask(
            task=task,
            toolsets=toolsets,
            max_iterations=sub_max,
            parent_task_id=state.task_id,
            user_id=state.user_id,
        )
        state.subagent_tasks.append(sub_task)
        return ToolResult.ok(
            f"Subagente criado: {sub_task.id[:8]} — task: {task[:100]}",
            data={"subagent_id": sub_task.id},
        )

    # ── 55.5 Preflight Compression ───────────────────────────────────────

    def _needs_preflight_compression(self, state: AgentState) -> bool:
        history_len = len(state.conversation_history)
        if history_len <= self._compressor.PROTECT_LAST_N:
            return False
        est_tokens = self._compressor._estimate_context_tokens(state)
        return est_tokens / 8192 >= self._compression_threshold

    # ── 55.6 Budget Warning ──────────────────────────────────────────────

    def _get_budget_warning(self) -> Optional[str]:
        return self._budget.get_warning()

    # ── 55.7 Flush Pending Memory ────────────────────────────────────────

    async def _flush_pending_memory(self, state: AgentState):
        for delta in state.pending_memory_writes:
            if not delta.applied:
                await self._memory_mgr.apply_memory_action(
                    action=delta.action,
                    target=delta.target,
                    content=delta.content,
                    old_text=delta.old_text,
                    user_id=delta.user_id,
                )
                delta.applied = True
        state.pending_memory_writes.clear()

    # ── 55.8 _finalize ──────────────────────────────────────────────────

    async def _finalize(self, state: AgentState, llm_response: LLMResponse):
        assistant_msg = Message(
            role=Role.ASSISTANT,
            content=llm_response.content,
            thinking_content=llm_response.thinking_content,
            model_used=llm_response.model,
            tokens_prompt=llm_response.tokens_prompt,
            tokens_completion=llm_response.tokens_completion,
            latency_ms=llm_response.latency_ms,
            iteration=state.iteration,
            session_id=state.session_id,
            user_id=state.user_id,
            task_id=state.task_id,
        )
        state.conversation_history.append(assistant_msg)

        await self._flush_pending_memory(state)
        await self._trajectory.save_trajectory(state)
        await self._memory_mgr.session_db.save_messages(
            state.conversation_history
        )
        await self._memory_mgr.session_db.end_session(
            state.session_id,
            tokens_used=llm_response.tokens_prompt + llm_response.tokens_completion,
        )

        asyncio.create_task(self._reflect_async(state, llm_response))

    async def _reflect_async(self, state: AgentState, llm_response: LLMResponse):
        try:
            from lux.reflection.post_task import PostTaskReflector
            tools_used = list({
                tc.function_name
                for msg in state.conversation_history
                if msg.tool_calls
                for tc in msg.tool_calls
            })
            errors = [
                r.error_message for r in state.tool_results if not r.success and r.error_message
            ]

            reflector = PostTaskReflector(
                llama=self._model_mgr.llama,
                memory_mgr=self._memory_mgr,
                session_db=self._memory_mgr.session_db,
            )
            await reflector.reflect_async(
                task_id=state.task_id,
                session_id=state.session_id,
                user_id=state.user_id,
                task_description=llm_response.content[:200],
                iterations_used=state.iteration,
                max_iterations=state.max_iterations,
                tools_used=tools_used,
                errors=errors,
                outcome="SUCCESS",
            )
        except Exception:
            logger.debug("Reflexao em background falhou", exc_info=True)

    # ── 55.10-55.11 Result Builders ──────────────────────────────────────

    def _build_interrupted_result(self, state: AgentState) -> ConversationResult:
        return ConversationResult(
            final_response="[interrompido]",
            session_id=state.session_id,
            iterations_used=state.iteration,
            status=PipelineStatus.INTERRUPTED,
        )

    def _build_budget_exhausted_result(self, state: AgentState) -> ConversationResult:
        pending = []
        if state.subagent_tasks:
            for t in state.subagent_tasks:
                if t.status == "pending":
                    pending.append(f"Subagente: {t.task[:80]}")
        return ConversationResult(
            final_response="Budget de iteracoes esgotado.",
            session_id=state.session_id,
            iterations_used=state.iteration,
            status=PipelineStatus.DONE,
            pending_items=pending,
        )

    def _build_error_result(self, state: AgentState) -> ConversationResult:
        return ConversationResult(
            final_response=f"Erro: {state.error or 'desconhecido'}",
            session_id=state.session_id,
            status=PipelineStatus.ERROR,
            error=state.error,
        )

    # ── 55.12 Checkpoint ────────────────────────────────────────────────

    async def save_checkpoint(self, state: AgentState) -> str:
        import json as _json
        from pathlib import Path

        checkpoint_dir = Path("~/.lux/checkpoints/").expanduser()
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = checkpoint_dir / f"{state.session_id}_{ts}.json"

        data = {
            "session_id": state.session_id,
            "task_id": state.task_id,
            "user_id": state.user_id,
            "channel": state.channel.value,
            "iteration": state.iteration,
            "compression_count": state.compression_count,
            "pipeline_status": state.pipeline_status.value,
            "conversation_history": [
                {
                    "id": m.id,
                    "role": m.role.value,
                    "content": m.content,
                    "tool_calls": [
                        {"id": tc.id, "name": tc.function_name}
                        for tc in m.tool_calls
                    ],
                    "tool_call_id": m.tool_call_id,
                    "iteration": m.iteration,
                }
                for m in state.conversation_history
            ],
            "timestamp": ts,
        }
        path.write_text(_json.dumps(data, ensure_ascii=False, indent=2))
        state.checkpoint_path = str(path)
        logger.info("Checkpoint salvo: %s", path)
        return str(path)

    # ── Cleanup ─────────────────────────────────────────────────────────

    async def _cleanup(self, state: AgentState):
        pass

    async def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
        await self._model_mgr.shutdown()
        await self._memory_mgr.close()
