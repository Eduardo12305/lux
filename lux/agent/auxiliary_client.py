# lux/agent/auxiliary_client.py
# Módulo: Agent
# Dependências: models/llama_client.py, agent/model_router.py, agent/state.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
from typing import Optional

from lux.agent.model_router import ModelRouter
from lux.agent.state import LLMResponse, Task
from lux.models.llama_client import LlamaClient

logger = logging.getLogger(__name__)


class AuxiliaryLLMClient:
    """Cliente para o modelo auxiliar (1.7B) — tarefas rapidas e classificatorias."""

    def __init__(self, llama_client: LlamaClient, model_router: ModelRouter):
        self._client = llama_client
        self._router = model_router

    async def classify_intent(self, message: str) -> LLMResponse:
        config = self._router.get_config(Task.INTENT_CLASSIFY)
        return await self._client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "Classifique a intencao do usuario em uma palavra: chat, question, action, recall, command.",
                },
                {"role": "user", "content": message},
            ],
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    async def extract_memory(self, conversation: str) -> LLMResponse:
        config = self._router.get_config(Task.MEMORY_EXTRACT)
        return await self._client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "Extraia fatos importantes da conversa que devem ser salvos em memoria.",
                },
                {"role": "user", "content": conversation},
            ],
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

    async def summarize_short(self, text: str, max_tokens: int = 512) -> LLMResponse:
        config = self._router.get_config(Task.SUMMARIZE_SHORT)
        return await self._client.chat_completion(
            messages=[
                {"role": "system", "content": "Resuma o texto em portugues."},
                {"role": "user", "content": text},
            ],
            model=config.model,
            temperature=config.temperature,
            max_tokens=max_tokens,
        )
