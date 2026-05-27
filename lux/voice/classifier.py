# lux/voice/classifier.py
# Módulo: Voice
# Dependências: models/llama_client.py, agent/auxiliary_client.py
# Status: IMPLEMENTADO
# Notas: Triagem híbrida de intenção ("é comigo?").
#   Camada 1: heurística rápida (1 palavra? contém "lux"?)
#   Camada 2: modelo 1.7B classifica contexto

from __future__ import annotations

import logging
from typing import Optional

from lux.agent.state import Task
from lux.agent.model_router import ModelRouter

logger = logging.getLogger(__name__)

DIRECT_TRIGGERS = [
    "lux", "assistente", "lembre", "faça", "faca", "crie", "cria",
    "busque", "busca", "pesquise", "pesquisa", "execute", "executa",
    "mostre", "mostra", "liste", "lista", "qual", "quem", "quando",
    "onde", "como", "por que", "me diga", "me fale", "pode", "poderia",
]

AMBIGUOUS_PATTERNS = [
    "acho que", "sera que", "talvez", "nao sei", "voce acha",
]

BACKGROUND_INDICATORS = [
    "entao", "depois", "tudo bem", "beleza", "obrigado", "valeu",
    "blz", "ok", "tchau", "ate mais", "vou indo", "vou sair",
]


class IntentClassifier:
    """Classificador híbrido de intenção — é comigo ou conversa de fundo?"""

    def __init__(self, llama_client=None):
        self._llama = llama_client
        self._router = ModelRouter()

    async def is_for_me(self, transcript: str) -> bool:
        if not transcript or not transcript.strip():
            return False

        text = transcript.lower().strip()
        words = text.split()

        if len(words) == 1 and len(text) < 4:
            return False

        for trigger in DIRECT_TRIGGERS:
            if trigger in text:
                return True

        if any(ind in text for ind in BACKGROUND_INDICATORS):
            if not any(t in text for t in DIRECT_TRIGGERS):
                return False

        if any(amb in text for amb in AMBIGUOUS_PATTERNS):
            pass

        if self._llama:
            return await self._classify_with_llm(transcript)

        return len(words) >= 3

    async def _classify_with_llm(self, transcript: str) -> bool:
        try:
            config = self._router.get_config(Task.CONFIRMATION_PARSE)
            response = await self._llama.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Voce e um classificador de intencao. "
                            "Responda apenas SIM ou NAO.\n\n"
                            "SIM: a frase e um comando ou pergunta dirigida ao assistente.\n"
                            "NAO: a frase e conversa de fundo, ruido, ou nao e para voce.\n\n"
                            "Exemplos:\n"
                            "- 'qual o status do build?' → SIM\n"
                            "- 'entao depois a gente ve isso' → NAO\n"
                            "- 'acho que vou sair agora' → NAO\n"
                            "- 'lembre de comprar pao' → SIM\n"
                            "- 'blz valeu' → NAO"
                        ),
                    },
                    {"role": "user", "content": f"Frase: '{transcript}'"},
                ],
                model=config.model,
                temperature=0.1,
                max_tokens=4,
            )
            result = response.content.strip().upper()
            return result.startswith("SIM")
        except Exception:
            return len(transcript.split()) >= 3
