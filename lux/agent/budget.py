# lux/agent/budget.py
# Módulo: Agent
# Dependências: nenhuma
# Status: IMPLEMENTADO

from __future__ import annotations

from typing import Optional


class IterationBudget:
    """Rastreia uso do budget de iteracoes com warnings progressivos."""

    def __init__(self, max_iterations: int = 50):
        self.max = max_iterations
        self.used = 0

    def consume(self):
        self.used += 1

    def get_warning(self) -> Optional[str]:
        remaining = self.max - self.used
        pct_used = self.used / self.max if self.max > 0 else 1.0

        if pct_used >= 0.95:
            return (
                f"[BUDGET CRITICO] {remaining} iteracao(oes) restantes. "
                f"Conclua a tarefa IMEDIATAMENTE ou entregue o que foi feito."
            )
        if pct_used >= 0.80:
            return (
                f"[BUDGET] {remaining} iteracoes restantes. "
                f"Priorize as acoes mais importantes."
            )
        if pct_used >= 0.60:
            return f"[INFO] {remaining} iteracoes restantes de {self.max}."
        return None

    @property
    def is_exhausted(self) -> bool:
        return self.used >= self.max
