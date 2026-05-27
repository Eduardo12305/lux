# lux/reflection/post_task.py
# Módulo: Reflection
# Dependências: models/llama_client.py, memory/manager.py, skills/manager.py, agent/state.py
# Status: IMPLEMENTADO
# Notas: Analisa tarefas concluídas, extrai lições, salva memória/skills em background.

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from lux.agent.state import (
    AgentState, MemoryAction, MemoryTarget, ToolResult, UserRole,
)
from lux.memory.manager import MemoryManager
from lux.memory.session_db import SessionDB
from lux.agent.model_router import ModelRouter
from lux.agent.state import Task
from lux.models.llama_client import LlamaClient

logger = logging.getLogger(__name__)

REFLECTION_PROMPT = """Analise a execucao desta tarefa e extraia licoes de forma estruturada.

TAREFA: {task_description}
RESULTADO: {outcome}
ITERACOES: {iterations_used}/{max_iterations}
FERRAMENTAS USADAS: {tools_used}
ERROS ENCONTRADOS: {errors}

Responda APENAS em JSON valido, sem texto adicional:
{{
  "what_worked": ["lista do que funcionou bem"],
  "what_failed": ["lista do que falhou ou foi subotimo"],
  "root_cause": "causa raiz do problema principal (ou null se nenhum)",
  "lessons": ["licoes aprendidas para tarefas futuras"],
  "skill_opportunity": {{
    "exists": false,
    "name": "",
    "reason": ""
  }},
  "memory_worthy": {{
    "exists": false,
    "content": ""
  }},
  "user_insight": {{
    "exists": false,
    "content": ""
  }}
}}"""


@dataclass
class ReflectionResult:
    task_id: str
    session_id: str
    user_id: str
    outcome: str
    what_worked: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    root_cause: Optional[str] = None
    lessons: list[str] = field(default_factory=list)
    skill_opp_name: Optional[str] = None
    skill_opp_reason: Optional[str] = None
    memory_content: Optional[str] = None
    user_insight_content: Optional[str] = None
    error: Optional[str] = None


class PostTaskReflector:
    """Reflete sobre tarefa concluída e extrai conhecimento em background."""

    def __init__(
        self,
        llama: Optional[LlamaClient] = None,
        memory_mgr: Optional[MemoryManager] = None,
        session_db: Optional[SessionDB] = None,
    ):
        self._llama = llama
        self._memory = memory_mgr
        self._db = session_db or SessionDB()
        self._router = ModelRouter()

    async def reflect(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        task_description: str,
        iterations_used: int,
        max_iterations: int,
        tools_used: list[str],
        errors: list[str],
        outcome: str = "SUCCESS",
    ) -> ReflectionResult:
        prompt = REFLECTION_PROMPT.format(
            task_description=task_description[:1000],
            outcome=outcome,
            iterations_used=iterations_used,
            max_iterations=max_iterations,
            tools_used=", ".join(tools_used[:15]) or "nenhuma",
            errors=", ".join(errors[:5]) if errors else "nenhum",
        )

        try:
            if self._llama:
                config = self._router.get_config(Task.CONVERSATION_DEEP)
                resp = await self._llama.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    model=config.model,
                    temperature=config.temperature,
                    max_tokens=1024,
                    enable_thinking=True,
                )
                raw = resp.content
            else:
                raw = '{"what_worked":[],"what_failed":[],"root_cause":null,"lessons":[],"skill_opportunity":{"exists":false},"memory_worthy":{"exists":false},"user_insight":{"exists":false}}'
        except Exception as e:
            logger.warning("LLM indisponivel para reflexao: %s", e)
            raw = '{"what_worked":[],"what_failed":[],"root_cause":null,"lessons":[],"skill_opportunity":{"exists":false},"memory_worthy":{"exists":false},"user_insight":{"exists":false}}'

        data = self._parse_json(raw)

        result = ReflectionResult(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            outcome=outcome,
            what_worked=data.get("what_worked", []),
            what_failed=data.get("what_failed", []),
            root_cause=data.get("root_cause"),
            lessons=data.get("lessons", []),
        )

        skill = data.get("skill_opportunity", {})
        if isinstance(skill, dict) and skill.get("exists"):
            result.skill_opp_name = skill.get("name", "")
            result.skill_opp_reason = skill.get("reason", "")

        mem = data.get("memory_worthy", {})
        if isinstance(mem, dict) and mem.get("exists"):
            result.memory_content = mem.get("content", "")

        insight = data.get("user_insight", {})
        if isinstance(insight, dict) and insight.get("exists"):
            result.user_insight_content = insight.get("content", "")

        await self._persist_reflection(result)
        return result

    async def _apply_reflection(self, result: ReflectionResult):
        if result.skill_opp_name and result.skill_opp_name.strip():
            await self._queue_skill(result)

        if result.lessons:
            await self._save_lessons(result)

        if result.memory_content and result.memory_content.strip():
            await self._persist_memory_suggestion(result)

    async def _persist_memory_suggestion(self, result: ReflectionResult):
        """Armazena sugestao de memoria para o agente decidir se salva.
        NÃO escreve diretamente em MEMORY.md — o LLM decide via tool 'memory'.
        """
        try:
            conn = await self._db._get_conn()
            await conn.execute(
                """INSERT INTO memory_suggestions (id, user_id, content, source_task_id, dismissed, created_at)
                   VALUES (?, ?, ?, ?, 0, ?)""",
                (
                    uuid4().hex[:12],
                    result.user_id,
                    result.memory_content[:500],
                    result.task_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await conn.commit()
            logger.debug("Sugestao de memoria armazenada: %s", result.memory_content[:60])
        except Exception as e:
            logger.debug("Erro ao armazenar sugestao de memoria: %s", e)

    async def _queue_skill(self, result: ReflectionResult):
        try:
            conn = await self._db._get_conn()
            await conn.execute(
                """INSERT OR REPLACE INTO skill_queue
                   (id, user_id, name, description, source_task_id, usefulness, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    uuid4().hex[:12],
                    result.user_id,
                    result.skill_opp_name[:100],
                    result.skill_opp_reason[:500],
                    result.task_id,
                    0.7,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await conn.commit()
            logger.info("Skill enfileirada: %s", result.skill_opp_name)
        except Exception as e:
            logger.debug("Erro ao enfileirar skill: %s", e)

    async def _save_lessons(self, result: ReflectionResult):
        try:
            conn = await self._db._get_conn()
            for lesson in result.lessons:
                await conn.execute(
                    """INSERT INTO lessons_fts (lesson, context, skill_name)
                       VALUES (?, ?, ?)""",
                    (lesson[:1000], result.task_id, result.skill_opp_name or ""),
                )
            await conn.commit()
        except Exception as e:
            logger.debug("Erro ao salvar licoes: %s", e)

    async def _persist_reflection(self, result: ReflectionResult):
        try:
            conn = await self._db._get_conn()
            await conn.execute(
                """INSERT INTO task_reflections
                   (id, task_id, session_id, user_id, outcome,
                    what_worked, what_failed, root_cause, lessons,
                    skill_opp_name, skill_opp_score, memory_saved, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid4().hex[:12],
                    result.task_id,
                    result.session_id,
                    result.user_id,
                    result.outcome,
                    json.dumps(result.what_worked, ensure_ascii=False),
                    json.dumps(result.what_failed, ensure_ascii=False),
                    result.root_cause,
                    json.dumps(result.lessons, ensure_ascii=False),
                    result.skill_opp_name,
                    0.7 if result.skill_opp_name else 0.0,
                    int(bool(result.memory_content)),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await conn.commit()
        except Exception as e:
            logger.debug("Erro ao persistir reflexao: %s", e)

    def _parse_json(self, raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return {}

    async def reflect_async(
        self,
        task_id: str,
        session_id: str,
        user_id: str,
        task_description: str,
        iterations_used: int,
        max_iterations: int,
        tools_used: list[str],
        errors: list[str],
        outcome: str = "SUCCESS",
    ):
        """Roda reflexao em background e aplica insights."""
        try:
            result = await self.reflect(
                task_id=task_id,
                session_id=session_id,
                user_id=user_id,
                task_description=task_description,
                iterations_used=iterations_used,
                max_iterations=max_iterations,
                tools_used=tools_used,
                errors=errors,
                outcome=outcome,
            )
            await self._apply_reflection(result)
        except Exception:
            logger.exception("Falha na reflexao em background")
