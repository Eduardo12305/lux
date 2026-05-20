# lux/memory/nudge.py
# Módulo: Memory
# Dependências: agent/state.py
# Status: IMPLEMENTADO

from __future__ import annotations

from typing import Optional

from lux.agent.state import AgentState
from lux.constants import NUDGE_AT_CONTEXT_PCT, NUDGE_AT_TURNS


class MemoryNudgeSystem:
    """
    Injeta lembretes ephemeros no contexto para persistir conhecimento
    antes de perder contexto por compressao.
    """

    def __init__(
        self,
        nudge_at_context_pct: float = NUDGE_AT_CONTEXT_PCT,
        nudge_at_turns: int = NUDGE_AT_TURNS,
    ):
        self._context_pct = nudge_at_context_pct
        self._turns = nudge_at_turns

    def maybe_inject_nudge(self, state: AgentState) -> Optional[str]:
        ctx_pct = self._estimate_context_usage(state)
        turns = state.iteration

        should_nudge = (
            ctx_pct > self._context_pct
            or (turns > 0 and turns % self._turns == 0)
        )
        if not should_nudge:
            return None

        return (
            "[SISTEMA] Lembre-se de persistir quaisquer fatos importantes "
            "aprendidos nesta sessao usando a ferramenta `memory` antes que "
            "o contexto seja comprimido."
        )

    def _estimate_context_usage(self, state: AgentState) -> float:
        total_chars = sum(len(m.content) for m in state.conversation_history)
        estimated_tokens = total_chars / 4
        max_tokens = 8192.0
        return estimated_tokens / max_tokens
