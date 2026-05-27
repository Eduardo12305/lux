# lux/voice/emotional_context.py
# Módulo: Voice
# Dependências: models/llama_client.py (opcional)
# Status: IMPLEMENTADO
# Notas: Detecta estado emocional pelo texto. Usa 1.7B se disponivel, fallback heurístico.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

STATES = ["neutro", "urgente", "frustrado", "satisfeito", "confuso"]

ADJUSTMENTS = {
    "urgente":    "Responda de forma DIRETA e CURTA. Sem introducoes.",
    "frustrado":  "Tom empatico. Reconheca a dificuldade brevemente.",
    "confuso":    "Explique passo a passo. Confirme entendimento ao final.",
    "satisfeito": "Tom normal. Pode sugerir proximos passos.",
    "neutro":     "",
}

URGENT_SIGNALS = [
    "urgente", "rapido", "agora", "ja", "corre", "depressa",
    "importante", "critico", "prazo", "deadline",
]

FRUSTRATED_SIGNALS = [
    "nao funcionou", "de novo", "toda vez", "ja tentei",
    "cansado", "chato", "complicado", "dificil",
]

CONFUSED_SIGNALS = [
    "nao entendi", "como assim", "explica", "por que",
    "nao sei", "duvida", "confuso",
]


@dataclass
class EmotionalState:
    state: str = "neutro"
    confidence: float = 0.0
    signals: list[str] = None

    def __post_init__(self):
        if self.signals is None:
            self.signals = []


class EmotionalContextDetector:
    """Detector de estado emocional via texto transcrito."""

    def __init__(self, llama_client=None):
        self._llama = llama_client

    async def detect(self, text: str) -> EmotionalState:
        if not text or len(text.split()) < 3:
            return EmotionalState()

        lower = text.lower()
        signals: list[str] = []

        for sig in URGENT_SIGNALS:
            if sig in lower:
                signals.append(sig)

        for sig in FRUSTRATED_SIGNALS:
            if sig in lower:
                signals.append(sig)

        for sig in CONFUSED_SIGNALS:
            if sig in lower:
                signals.append(sig)

        if signals:
            if any(s in URGENT_SIGNALS for s in signals):
                return EmotionalState(state="urgente", confidence=0.8, signals=signals)
            if any(s in FRUSTRATED_SIGNALS for s in signals):
                return EmotionalState(state="frustrado", confidence=0.7, signals=signals)
            if any(s in CONFUSED_SIGNALS for s in signals):
                return EmotionalState(state="confuso", confidence=0.7, signals=signals)

        if self._llama:
            return await self._classify_with_llm(text)

        return EmotionalState()

    async def _classify_with_llm(self, text: str) -> EmotionalState:
        try:
            from lux.agent.model_router import ModelRouter
            from lux.agent.state import Task
            router = ModelRouter()
            config = router.get_config(Task.SENTIMENT_DETECT)

            resp = await self._llama.chat_completion(
                messages=[
                    {"role": "system", "content": (
                        "Classifique o estado emocional do usuario. "
                        "Responda apenas uma palavra: neutro, urgente, frustrado, satisfeito, confuso."
                    )},
                    {"role": "user", "content": text},
                ],
                model=config.model,
                temperature=0.1,
                max_tokens=8,
            )
            state = resp.content.strip().lower()
            if state in STATES:
                return EmotionalState(state=state, confidence=0.85)
        except Exception:
            pass
        return EmotionalState()

    def _build_system_adjustment(self, state: EmotionalState) -> str:
        return ADJUSTMENTS.get(state.state, "")
