# lux/prompt/assembler.py
# Módulo: Prompt
# Dependências: agent/state.py, interfaces/protocols.py (Protocols, nao classes concretas)
# Status: IMPLEMENTADO
# Notas: Dependency Inversion via Protocols (GAP 8 resolvido).

from __future__ import annotations

from lux.agent.state import AgentState
from lux.interfaces.protocols import SkillListProvider
from lux.prompt.formatting import (
    format_active_tools,
    format_behavior_instructions,
    format_model_specific_instructions,
    format_skills_list_l0,
    format_subagent_instructions,
)


class PromptAssembler:
    """
    Monta o system prompt completo a partir de multiplas fontes.
    Usa Protocols para evitar dependencia circular com SkillManager e ToolRegistry.
    """

    def __init__(
        self,
        skill_list_provider: SkillListProvider | None = None,
        tool_schema_provider: object | None = None,
        soul_loader: object | None = None,
    ):
        self._skill_list_provider = skill_list_provider
        self._tool_schema_provider = tool_schema_provider
        self._soul_loader = soul_loader

    def build_system_prompt(self, state: AgentState) -> str:
        sections: list[str] = []

        if self._soul_loader and hasattr(self._soul_loader, "load"):
            soul = self._soul_loader.load(state.user_profile)
            if soul:
                sections.append(soul)

        if state.memory_snapshot:
            sections.append(state.memory_snapshot)
        if state.user_snapshot:
            sections.append(state.user_snapshot)

        for path, content in state.context_files.items():
            sections.append(f"### Context: {path}\n{content}")

        if self._skill_list_provider:
            skills_list = self._skill_list_provider.get_skills_list_l0(
                state.user_profile, state.channel
            )
            if skills_list:
                sections.append(format_skills_list_l0(skills_list))

        if self._tool_schema_provider and hasattr(
            self._tool_schema_provider, "get_active_schemas"
        ):
            schemas = self._tool_schema_provider.get_active_schemas(
                state.user_profile,
                state.user_profile.enabled_toolsets,
            )
            if schemas:
                sections.append(format_active_tools(schemas))

        sections.append(
            format_behavior_instructions(
                preferred_language=state.user_profile.preferred_language,
                response_style=state.user_profile.response_style.value,
                formality=state.user_profile.formality.value,
                channel=state.channel.value,
            )
        )

        sections.append(format_model_specific_instructions())

        if state.is_subagent:
            sections.append(
                format_subagent_instructions(
                    max_iterations=state.max_iterations,
                    parent_task_id=state.parent_task_id or "",
                )
            )

        return "\n\n---\n\n".join(filter(None, sections))
