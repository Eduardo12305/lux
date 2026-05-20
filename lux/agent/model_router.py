# lux/agent/model_router.py
# Módulo: Agent
# Dependências: agent/state.py, config.py
# Status: IMPLEMENTADO

from __future__ import annotations

from dataclasses import dataclass, field

from lux.agent.state import Task


@dataclass
class ModelConfig:
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    thinking: bool = False


class ModelRouter:
    """Decide qual modelo usar para cada tipo de tarefa."""

    MAIN_MODEL = "qwen3-14b-q4"
    FAST_MODEL = "qwen3-1.7b-q4"

    ROUTING_TABLE: dict[Task, ModelConfig] = {
        Task.CONVERSATION: ModelConfig(MAIN_MODEL, temperature=0.7, thinking=False),
        Task.CONVERSATION_DEEP: ModelConfig(MAIN_MODEL, temperature=0.6, thinking=True),
        Task.ACTION_PLANNING: ModelConfig(MAIN_MODEL, temperature=0.2, thinking=True),
        Task.SKILL_CREATION: ModelConfig(MAIN_MODEL, temperature=0.4, thinking=True),
        Task.SUMMARIZE_LONG: ModelConfig(MAIN_MODEL, temperature=0.3, thinking=False),
        Task.TOOL_CALL_COMPLEX: ModelConfig(MAIN_MODEL, temperature=0.1, thinking=False),
        Task.INTENT_CLASSIFY: ModelConfig(FAST_MODEL, temperature=0.1, max_tokens=128),
        Task.MEMORY_EXTRACT: ModelConfig(FAST_MODEL, temperature=0.1, max_tokens=256),
        Task.SENTIMENT_DETECT: ModelConfig(FAST_MODEL, temperature=0.1, max_tokens=32),
        Task.CONFIRMATION_PARSE: ModelConfig(FAST_MODEL, temperature=0.1, max_tokens=16),
        Task.SUMMARIZE_SHORT: ModelConfig(FAST_MODEL, temperature=0.3, max_tokens=512),
        Task.ENTITY_EXTRACT: ModelConfig(FAST_MODEL, temperature=0.1, max_tokens=256),
        Task.SKILL_TRIGGER_CHECK: ModelConfig(FAST_MODEL, temperature=0.1, max_tokens=64),
    }

    def get_config(self, task: Task) -> ModelConfig:
        return self.ROUTING_TABLE.get(task, ModelConfig(self.MAIN_MODEL))
