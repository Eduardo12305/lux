# lux/reflection/behavior_analyzer.py
# Módulo: Reflection
# Dependências: memory/session_db.py
# Status: IMPLEMENTADO
# Notas: Analisa padroes de uso e atualiza USER.md. Roda a cada 20 sessoes.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from lux.agent.state import MemoryAction, MemoryTarget
from lux.memory.manager import MemoryManager
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)

ANALYZE_EVERY_N_SESSIONS = 20


@dataclass
class BehaviorReport:
    user_id: str
    work_hours: dict[int, int] = field(default_factory=dict)
    top_tools: list[dict] = field(default_factory=list)
    top_skills: list[dict] = field(default_factory=list)
    task_types: dict[str, int] = field(default_factory=dict)
    correction_count: int = 0
    insights: list[str] = field(default_factory=list)
    automation_suggestions: list[dict] = field(default_factory=list)


class UserBehaviorAnalyzer:
    """Analisa historico de sessoes e atualiza USER.md com insights."""

    def __init__(
        self,
        session_db: Optional[SessionDB] = None,
        memory_mgr: Optional[MemoryManager] = None,
    ):
        self._db = session_db or SessionDB()
        self._memory = memory_mgr
        self._last_analyzed: dict[str, datetime] = {}

    async def should_analyze(self, user_id: str) -> bool:
        last = self._last_analyzed.get(user_id)
        if last is None:
            profile = await self._db.get_profile(user_id)
            if profile:
                sessions = profile.total_sessions
                return sessions > 0 and sessions % ANALYZE_EVERY_N_SESSIONS == 0
            return False
        return (datetime.now(timezone.utc) - last) > timedelta(hours=24)

    async def analyze(self, user_id: str) -> BehaviorReport:
        report = BehaviorReport(user_id=user_id)

        try:
            conn = await self._db._get_conn()
            cursor = await conn.execute(
                """SELECT m.timestamp, m.role, m.content, m.tool_calls
                   FROM messages m
                   JOIN sessions s ON m.session_id = s.id
                   WHERE s.user_id = ? AND s.started_at > ?
                   ORDER BY m.timestamp DESC
                   LIMIT 500""",
                (user_id, (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()),
            )
            rows = await cursor.fetchall()

            hour_dist: dict[int, int] = {}
            tool_counts: dict[str, int] = {}
            responses = 0
            corrections = 0

            for row in rows:
                row = dict(row)
                ts = row.get("timestamp", "")
                if ts:
                    try:
                        hour = datetime.fromisoformat(ts).hour
                        hour_dist[hour] = hour_dist.get(hour, 0) + 1
                    except (ValueError, TypeError):
                        pass

                tool_calls = row.get("tool_calls", "")
                if tool_calls:
                    try:
                        for tc in json.loads(tool_calls) if isinstance(tool_calls, str) else (tool_calls or []):
                            name = tc.get("function", {}).get("name", "") if isinstance(tc, dict) else getattr(tc, "function_name", "")
                            if name:
                                tool_counts[name] = tool_counts.get(name, 0) + 1
                    except (json.JSONDecodeError, TypeError):
                        pass

                content = row.get("content", "")
                if content and "corrig" in content.lower():
                    corrections += 1
                if row.get("role") in ("assistant", "user"):
                    responses += 1

            report.work_hours = hour_dist
            report.top_tools = sorted(
                [{"tool": k, "count": v} for k, v in tool_counts.items()],
                key=lambda x: x["count"], reverse=True,
            )[:10]
            report.correction_count = corrections

            peak_hours = sorted(hour_dist, key=hour_dist.get, reverse=True)[:3]
            if peak_hours:
                start = min(peak_hours)
                end = max(peak_hours)
                report.insights.append(
                    f"Trabalha principalmente entre {start}h e {end}h "
                    f"(pico de atividade)"
                )

            if responses > 100:
                avg = corrections / responses if responses else 0
                if avg > 0.05:
                    report.insights.append(
                        f"Corrigiu o Lux em {corrections} de {responses} mensagens "
                        f"({avg*100:.1f}%) — pode estar respondendo incorretamente"
                    )

            if tool_counts:
                top = sorted(tool_counts, key=tool_counts.get, reverse=True)[:3]
                report.insights.append(f"Ferramentas mais usadas: {', '.join(top)}")

            repeated_hours = [h for h, c in hour_dist.items() if c > 10]
            if repeated_hours:
                for h in repeated_hours:
                    report.automation_suggestions.append({
                        "hour": h,
                        "suggestion": f"Considere agendar tarefas recorrentes para as {h}h",
                    })

        except Exception as e:
            logger.debug("Erro na analise comportamental: %s", e)

        self._last_analyzed[user_id] = datetime.now(timezone.utc)
        await self._apply_insights(report)
        return report

    async def _apply_insights(self, report: BehaviorReport):
        if not self._memory or not report.insights:
            return
        try:
            for insight in report.insights:
                await self._memory.apply_memory_action(
                    action=MemoryAction.ADD,
                    target=MemoryTarget.USER,
                    content=f"[auto-analise] {insight[:500]}",
                    user_id=report.user_id,
                )
        except Exception as e:
            logger.debug("Erro ao aplicar insights: %s", e)
