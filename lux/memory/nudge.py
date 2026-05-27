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


class SkillNudgeSystem:
    """Sugere criacao de skill apos tarefas complexas bem-sucedidas."""

    def __init__(self, min_tool_calls: int = 5):
        self._min_tool_calls = min_tool_calls
        self._last_nudge_at = 0
        self._tool_call_count = 0

    def track_tool_call(self):
        self._tool_call_count += 1

    def maybe_inject_nudge(self, state: AgentState) -> Optional[str]:
        if state.iteration <= self._last_nudge_at + 5:
            return None

        if self._tool_call_count < self._min_tool_calls:
            return None

        recent_failures = sum(
            1 for r in state.tool_results[-self._tool_call_count:]
            if not r.success
        )
        if recent_failures > self._tool_call_count * 0.3:
            return None

        self._last_nudge_at = state.iteration
        self._tool_call_count = 0

        return (
            "[SISTEMA] Voce concluiu uma tarefa complexa com varias ferramentas. "
            "Considere criar uma skill com `skill_create` para reutilizar este "
            "procedimento no futuro. Skills criadas ficam salvas em "
            "~/.lux/skills/ e aparecem na lista L0 para sessoes futuras. "
            "Use `skills_list` para ver skills existentes e evitar duplicatas."
        )
