# lux/voice/conversation_mode.py
# Módulo: Voice
# Dependências: nenhuma
# Status: IMPLEMENTADO
# Notas: Máquina de estados da janela de conversação contínua.

from __future__ import annotations

import time

TOPIC_CHANGE_INDICATORS = [
    "outra coisa", "mudando de assunto", "agora quero", "diferente",
    "esquece", "cancela", "nao, pera", "alias", "na verdade",
    "deixa pra la", "deixa quieto", "muda de topico", "troca de assunto",
]


class ConversationModeManager:
    """Gerencia janela de conversação pós-detecção de fala. 30s de escuta ativa."""

    CONVERSATION_WINDOW_S = 30.0
    FOLLOW_UP_SILENCE_S = 2.5

    def __init__(self):
        self._in_conversation = False
        self._last_interaction = 0.0
        self._utterances: list[str] = []

    @property
    def is_active(self) -> bool:
        return (
            self._in_conversation
            and time.monotonic() - self._last_interaction < self.CONVERSATION_WINDOW_S
        )

    @property
    def context(self) -> list[str]:
        return list(self._utterances)

    def activate(self):
        self._in_conversation = True
        self._last_interaction = time.monotonic()
        self._utterances.clear()

    def update(self, utterance: str):
        self._last_interaction = time.monotonic()
        self._utterances.append(utterance)

    def deactivate(self, reason: str = "timeout"):
        self._in_conversation = False
        self._utterances.clear()

    def is_topic_change(self, text: str) -> bool:
        return any(ind in text.lower() for ind in TOPIC_CHANGE_INDICATORS)
