# lux/skills/creator.py
# Módulo: Skills
# Dependências: skills/manager.py, agent/state.py, models/llama_client.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
from typing import Optional

from lux.agent.state import AgentState
from lux.skills.manager import SkillManager

logger = logging.getLogger(__name__)

SKILL_CREATION_PROMPT = """Crie um SKILL.md para a skill `{skill_name}` baseado na tarefa abaixo.

## Tarefa concluida
{task_summary}

## Ferramentas usadas
{tool_calls_summary}

## Skills existentes (evite duplicatas)
{existing_skills}

## Formato SKILL.md
---
name: {skill_name}
description: "descricao curta do que a skill faz"
version: 1.0.0
author: lux-agent
platforms: [linux]
metadata:
  lux:
    tags: []
    category: ""
    requires_toolsets: []
---

# Titulo

## Quando Usar
...

## Pre-requisitos
...

## Procedimento

### Passo 1
...

## Pitfalls
...

## Verificacao
...

Gere APENAS o conteudo do SKILL.md, sem explicacoes adicionais.
"""


class SkillCreator:
    """Criacao autonoma de skills apos tarefas complexas."""

    def __init__(self, skill_manager: SkillManager):
        self._skill_manager = skill_manager

    def build_creation_prompt(
        self,
        skill_name: str,
        task_summary: str,
        tool_calls_summary: str,
        state: AgentState,
    ) -> str:
        existing = self._skill_manager.get_skills_list_l0(
            state.user_profile, state.channel
        )
        existing_names = "\n".join(f"- {s.name}: {s.description}" for s in existing)

        return SKILL_CREATION_PROMPT.format(
            skill_name=skill_name,
            task_summary=task_summary,
            tool_calls_summary=tool_calls_summary,
            existing_skills=existing_names or "(nenhuma)",
        )

    async def create(
        self, skill_content: str, skill_name: str
    ) -> Optional[any]:
        try:
            skill = await self._skill_manager.create_skill_from_task(
                skill_content, skill_name
            )
            return skill
        except Exception as e:
            logger.error("Falha ao criar skill '%s': %s", skill_name, e)
            return None
