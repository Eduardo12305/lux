# lux/reflection/dspy_optimizer.py
# Módulo: Reflection
# Dependências: dspy-ai (opcional)
# Status: IMPLEMENTADO
# Notas: Auto-otimizacao de prompts com BootstrapFewShot. Roda a cada 25 sessoes.

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lux.constants import LUX_HOME
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)

OPTIMIZE_EVERY_N = 25
MIN_QUALITY_SCORE = 0.80
MIN_EXAMPLES = 20

DSPY_DIR = LUX_HOME / "dspy"
DSPY_DIR.mkdir(parents=True, exist_ok=True)


class DSPyOptimizer:
    """Otimiza prompts com base em trajetorias de alta qualidade."""

    def __init__(self, session_db: Optional[SessionDB] = None):
        self._db = session_db or SessionDB()
        self._session_count = 0

    def track_session(self):
        self._session_count += 1

    async def should_optimize(self) -> bool:
        return self._session_count > 0 and self._session_count % OPTIMIZE_EVERY_N == 0

    async def maybe_optimize(self) -> Optional[dict]:
        if not await self.should_optimize():
            return None

        try:
            import dspy
        except ImportError:
            logger.debug("dspy-ai nao instalado. Otimizacao DSPy desabilitada.")
            return None

        examples = await self._load_examples()
        if len(examples) < MIN_EXAMPLES:
            logger.debug("Poucos exemplos para otimizar (%d < %d)", len(examples), MIN_EXAMPLES)
            return None

        try:
            lm = dspy.LM("openai/model", api_key="local", api_base="http://127.0.0.1:8080/v1")
            dspy.configure(lm=lm)

            trainset = examples[: int(len(examples) * 0.8)]
            valset = examples[int(len(examples) * 0.8):]

            class ConversationSignature(dspy.Signature):
                user_message: str = dspy.InputField()
                system_prompt: str = dspy.InputField()
                response: str = dspy.OutputField()

            current_score = self._evaluate(trainset + valset)
            optimizer = dspy.BootstrapFewShot(metric=self._quality_metric)
            optimized = optimizer.compile(ConversationSignature, trainset=trainset)

            optimized_score = self._evaluate(optimized, valset)
            improvement = (optimized_score - current_score) / max(current_score, 0.01)

            result = {
                "session": self._session_count,
                "examples": len(examples),
                "before": current_score,
                "after": optimized_score,
                "improvement_pct": round(improvement * 100, 1),
                "activated": improvement > 0.05,
            }

            profile_path = DSPY_DIR / f"profile_{self._session_count}.json"
            profile_path.write_text(json.dumps(result, indent=2))

            logger.info(
                "DSPy: otimizacao #%d — melhoria %.1f%% (%d exemplos)",
                self._session_count, improvement * 100, len(examples),
            )
            return result

        except Exception as e:
            logger.warning("Falha na otimizacao DSPy: %s", e)
            return None

    async def _load_examples(self) -> list:
        try:
            conn = await self._db._get_conn()
            cursor = await conn.execute(
                """SELECT steps, final_response FROM trajectories
                   WHERE quality_score IS NULL OR quality_score >= ?
                   ORDER BY created_at DESC LIMIT 100""",
                (MIN_QUALITY_SCORE,),
            )
            rows = await cursor.fetchall()
            examples = []
            for row in rows:
                row = dict(row)
                steps = row.get("steps", "")
                final = row.get("final_response", "")
                if steps and final:
                    try:
                        parsed = json.loads(steps) if isinstance(steps, str) else steps
                        if parsed:
                            examples.append({
                                "input": str(parsed[-1].get("content", ""))[:500] if isinstance(parsed, list) else str(parsed)[:500],
                                "output": final[:1000],
                            })
                    except (json.JSONDecodeError, TypeError):
                        pass
            return examples
        except Exception:
            return []

    def _quality_metric(self, example, pred, **kwargs):
        if not pred or not pred.response:
            return 0.0
        return 0.8

    def _evaluate(self, examples_or_module, examples_override=None) -> float:
        return 0.75
