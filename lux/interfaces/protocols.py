# lux/interfaces/protocols.py
# Módulo: Interfaces
# Dependências: agent/state.py
# Status: IMPLEMENTADO
# Notas: Protocols para Dependency Inversion (GAP 8/Risco 8 resolvido).

from __future__ import annotations

from typing import Protocol

from lux.agent.state import Channel, SkillSummary, UserProfile


class SkillListProvider(Protocol):
    def get_skills_list_l0(self, user: UserProfile, channel: Channel) -> list[SkillSummary]:
        ...


class ToolSchemaProvider(Protocol):
    def get_active_schemas(self, user: UserProfile, toolsets: list[str]) -> list[dict]:
        ...


class SoulProvider(Protocol):
    def load(self, user: UserProfile) -> str:
        ...
