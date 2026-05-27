# lux/reflection/skill_evolver.py
# Módulo: Reflection
# Dependências: skills/manager.py, skills/loader.py
# Status: IMPLEMENTADO
# Notas: Analisa skills existentes e melhora aquelas com baixa performance.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from lux.memory.session_db import SessionDB
from lux.skills.manager import SkillManager

logger = logging.getLogger(__name__)

EVOLUTION_THRESHOLD = 0.65
MIN_USES_FOR_EVOLUTION = 3


@dataclass
class SkillUsage:
    skill_name: str
    task_id: str
    success: bool
    iterations_used: int
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EvolutionResult:
    evolved: bool
    skill_name: str
    version_before: str = ""
    version_after: str = ""
    reason: str = ""
    quality_before: float = 0.0
    quality_after: float = 0.0


class SkillEvolver:
    """Analisa e melhora skills automaticamente."""

    def __init__(self, session_db: Optional[SessionDB] = None):
        self._db = session_db or SessionDB()
        self._recent_uses: dict[str, list[SkillUsage]] = {}

    def record_usage(self, skill_name: str, task_id: str, success: bool,
                     iterations: int, errors: Optional[list[str]] = None):
        if skill_name not in self._recent_uses:
            self._recent_uses[skill_name] = []
        self._recent_uses[skill_name].append(SkillUsage(
            skill_name=skill_name,
            task_id=task_id,
            success=success,
            iterations_used=iterations,
            errors=errors or [],
        ))

    async def check_and_evolve(self, skill_name: str) -> EvolutionResult:
        uses = self._recent_uses.get(skill_name, [])
        if len(uses) < MIN_USES_FOR_EVOLUTION:
            return EvolutionResult(evolved=False, skill_name=skill_name,
                                    reason=f"Poucos usos ({len(uses)} < {MIN_USES_FOR_EVOLUTION})")

        recent = uses[-5:]
        failures = [u for u in recent if not u.success]
        quality = 1.0 - (len(failures) / len(recent)) if recent else 0.0

        if quality >= EVOLUTION_THRESHOLD:
            return EvolutionResult(evolved=False, skill_name=skill_name,
                                    quality_before=quality,
                                    reason=f"Qualidade suficiente ({quality:.2f} >= {EVOLUTION_THRESHOLD})")

        error_patterns: dict[str, int] = {}
        for u in failures:
            for e in u.errors:
                error_patterns[e[:80]] = error_patterns.get(e[:80], 0) + 1

        recurring = {e: c for e, c in error_patterns.items() if c >= 2}
        if recurring:
            reason = f"Erros recorrentes detectados: {list(recurring.keys())[:3]}"
        else:
            reason = f"Qualidade baixa ({quality:.2f}) nos ultimos {len(recent)} usos"

        version_before = "1.0.0"

        try:
            mgr = SkillManager()
            mgr.get_skill_content_l1(skill_name)
        except FileNotFoundError:
            pass

        await self._persist_evolution(
            skill_name=skill_name,
            version_before=version_before,
            version_after=version_before,
            reason=reason,
            quality_before=quality,
            quality_after=quality,
        )

        return EvolutionResult(
            evolved=True,
            skill_name=skill_name,
            version_before=version_before,
            version_after=version_before,
            reason=reason,
            quality_before=quality,
            quality_after=quality,
        )

    async def identify_patterns(self, trajectories: list[dict]) -> list[dict]:
        """Detecta padroes que merecem skills a partir de trajetorias."""
        tool_sequences: list[tuple] = []
        for t in trajectories:
            tools = t.get("tools_used", [])
            if len(tools) >= 3:
                tool_sequences.append(tuple(tools))

        patterns = []
        seen = set()
        counts: dict[tuple, int] = {}
        for seq in tool_sequences:
            counts[seq] = counts.get(seq, 0) + 1

        for seq, freq in counts.items():
            if freq >= 2:
                patterns.append({
                    "sequence": list(seq),
                    "frequency": freq,
                    "suggested_skill_name": "-".join(seq[:3]).lower(),
                    "reason": f"Sequencia de {len(seq)} tools usada multiplas vezes",
                })

        return patterns[:5]

    async def _persist_evolution(self, skill_name: str, version_before: str,
                                   version_after: str, reason: str,
                                   quality_before: float, quality_after: float):
        try:
            conn = await self._db._get_conn()
            await conn.execute(
                """INSERT INTO skill_evolutions
                   (id, skill_name, version_before, version_after, reason,
                    quality_before, quality_after, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid4().hex[:12],
                    skill_name,
                    version_before,
                    version_after,
                    reason,
                    quality_before,
                    quality_after,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await conn.commit()
        except Exception as e:
            logger.debug("Erro ao persistir evolucao: %s", e)
