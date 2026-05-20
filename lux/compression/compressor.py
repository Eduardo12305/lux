# lux/compression/compressor.py
# Módulo: Compression
# Dependências: agent/state.py, memory/manager.py, memory/session_db.py, models/llama_client.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
from typing import Optional

from lux.agent.state import AgentState, Message, Role
from lux.memory.manager import MemoryManager
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)

COMPRESSION_PROMPT = """Resuma a conversa abaixo de forma concisa, preservando:
1. Decisoes tomadas pelo usuario
2. Fatos importantes mencionados
3. Tarefas concluidas e seus resultados
4. Tarefas pendentes

Conversa:
{conversation}

Usuario: {user_display_name}

Resumo (em portugues):"""


class ContextCompressor:
    """Compressao lossy do historico com tool pair rescue e lineage tracking."""

    PROTECT_LAST_N = 20

    def __init__(
        self,
        memory_manager: MemoryManager,
        session_db: SessionDB,
        protect_last_n: int = 20,
    ):
        self._memory = memory_manager
        self._session_db = session_db
        self.PROTECT_LAST_N = protect_last_n

    async def compress(
        self,
        state: AgentState,
        threshold_pct: float = 0.50,
    ) -> bool:
        history = state.conversation_history
        if len(history) <= self.PROTECT_LAST_N:
            return False

        ctx_size = self._estimate_context_tokens(state)
        max_ctx = 8192
        if ctx_size / max_ctx < threshold_pct:
            return False

        to_compress = history[: -self.PROTECT_LAST_N]
        to_keep = history[-self.PROTECT_LAST_N :]

        to_compress, rescued = self._rescue_tool_pairs(to_compress, to_keep)

        if not to_compress:
            return False

        summary = self._build_compression_summary(
            to_compress, state.user_profile.display_name
        )

        await self._memory._session_db.create_child_session(
            state.session_id, summary, len(to_compress)
        )

        state.compression_count += 1
        summary_msg = Message(
            role=Role.SYSTEM,
            content=f"[RESUMO DA CONVERSA ANTERIOR]\n{summary}",
        )
        state.conversation_history = [summary_msg] + rescued + to_keep

        logger.info(
            "Contexto comprimido: %d msgs -> resumo + %d msgs (rescued: %d)",
            len(history), len(to_keep), len(rescued),
        )
        return True

    def _build_compression_summary(
        self, messages: list[Message], display_name: str
    ) -> str:
        conversation_text = []
        for m in messages:
            prefix = f"[{m.role.value.upper()}]"
            if m.content:
                conversation_text.append(f"{prefix} {m.content}")
            if m.tool_calls:
                for tc in m.tool_calls:
                    conversation_text.append(
                        f"{prefix} [tool_call: {tc.function_name}]"
                    )
        formatted = "\n".join(conversation_text)
        return COMPRESSION_PROMPT.format(
            conversation=formatted[:8000],
            user_display_name=display_name,
        )

    def _rescue_tool_pairs(
        self,
        to_compress: list[Message],
        to_keep: list[Message],
    ) -> tuple[list[Message], list[Message]]:
        tc_ids = {
            tc.id for msg in to_compress if msg.tool_calls for tc in msg.tool_calls
        }
        tr_ids = {
            msg.tool_call_id
            for msg in to_compress
            if msg.role == Role.TOOL and msg.tool_call_id
        }
        orphaned = tc_ids - tr_ids

        if not orphaned:
            return to_compress, []

        rescued = []
        i = len(to_compress) - 1
        while i >= 0 and orphaned:
            msg = to_compress[i]
            if msg.role == Role.ASSISTANT and any(
                tc.id in orphaned for tc in (msg.tool_calls or [])
            ):
                popped = to_compress.pop(i)
                rescued.insert(0, popped)
                for tc in popped.tool_calls or []:
                    orphaned.discard(tc.id)
            i -= 1

        rescued_by_call_id = {r.tool_calls[0].id for r in rescued if r.tool_calls}
        new_orphaned = {
            msg.tool_call_id
            for msg in to_compress
            if msg.role == Role.TOOL and msg.tool_call_id
        }
        all_orphaned = (tc_ids - new_orphaned) | {
            tc_id for tc_id in tc_ids if tc_id not in orphaned
        }
        for tc_id in rescued_by_call_id:
            all_orphaned.discard(tc_id)

        if all_orphaned:
            logger.warning(
                "Compressao abortada: pares tool_call/tool_result orfaos detectados"
            )
            return [], []

        return to_compress, rescued

    def _estimate_context_tokens(self, state: AgentState) -> int:
        total = len(state.system_prompt_frozen) // 4
        for m in state.conversation_history:
            total += len(m.content) // 4
            if m.thinking_content:
                total += len(m.thinking_content) // 4
        return total
