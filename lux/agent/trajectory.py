# lux/agent/trajectory.py
# Módulo: Agent
# Dependências: agent/state.py, memory/session_db.py
# Status: IMPLEMENTADO

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

from lux.agent.state import AgentState, LLMResponse, TrajectoryStep
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)


class TrajectorySaver:
    """Salva trajetorias de sessoes para fine-tuning futuro."""

    def __init__(self, session_db: SessionDB):
        self._db = session_db

    def record_step(self, state: AgentState, llm_response: LLMResponse):
        step = TrajectoryStep(
            iteration=state.iteration,
            messages_before=len(state.conversation_history),
            llm_response=llm_response,
            compressed=state.compression_count > 0,
        )
        state.trajectory.append(step)

    async def save_trajectory(self, state: AgentState):
        if not state.trajectory:
            return
        conn = await self._db._get_conn()
        steps_json = json.dumps(
            [
                {
                    "iteration": s.iteration,
                    "messages_before": s.messages_before,
                    "content": s.llm_response.content,
                    "tool_calls": [
                        tc.function_name for tc in s.llm_response.tool_calls
                    ],
                    "compressed": s.compressed,
                }
                for s in state.trajectory
            ],
            ensure_ascii=False,
        )
        await conn.execute(
            """INSERT INTO trajectories (id, task_id, session_id, user_id,
               steps, final_response, iterations_used, tokens_used, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid4().hex,
                state.task_id,
                state.session_id,
                state.user_id,
                steps_json,
                "",
                state.iteration,
                sum(
                    s.llm_response.tokens_prompt + s.llm_response.tokens_completion
                    for s in state.trajectory
                ),
                datetime.now().isoformat(),
            ),
        )
        await conn.commit()
        logger.debug("Trajetoria salva: %d steps", len(state.trajectory))
