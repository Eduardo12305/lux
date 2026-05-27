# lux/tools/implementations/skills_tools.py
from lux.agent.state import AgentState, ToolResult
from lux.tools.base import Tool


class SkillsListTool(Tool):
    name = "skills_list"
    description = "Lista todas as skills disponiveis (Level 0 — apenas nome e descricao)"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        import asyncio
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._async_execute(state))

    async def _async_execute(self, state: AgentState) -> ToolResult:
        from lux.skills.manager import SkillManager
        mgr = SkillManager()
        skills = mgr.get_skills_list_l0(state.user_profile, state.channel)
        if not skills:
            return ToolResult.ok("Nenhuma skill disponivel.")
        lines = ["Skills disponiveis:"]
        for s in skills:
            cmd = f" /{s.name}" if s.slash_command else ""
            lines.append(f"  {s.name}{cmd} — {s.description}")
        return ToolResult.ok("\n".join(lines))


class SkillViewTool(Tool):
    name = "skill_view"
    description = "Carrega o conteudo completo (L1) ou secao especifica (L2) de uma skill"
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nome da skill"},
            "section": {"type": "string", "description": "Secao especifica (L2). Ex: 'Procedimento'"},
        },
        "required": ["name"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        name = args.get("name", "")
        section = args.get("section", "")
        from lux.skills.manager import SkillManager
        mgr = SkillManager()
        try:
            if section:
                content = mgr.get_skill_section_l2(name, section)
                if not content:
                    return ToolResult.ok(f"Secao '{section}' nao encontrada na skill '{name}'.")
                return ToolResult.ok(content)
            content = mgr.get_skill_content_l1(name)
            return ToolResult.ok(content)
        except FileNotFoundError:
            return ToolResult.failure(f"Skill '{name}' nao encontrada.")


class SkillCreateTool(Tool):
    name = "skill_create"
    description = "Cria uma nova skill a partir de uma tarefa bem-sucedida. O LLM gera o SKILL.md completo."
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nome da skill (ex: deploy-docker)"},
            "description": {"type": "string", "description": "Descricao curta do que a skill faz"},
            "procedure": {"type": "string", "description": "Procedimento completo passo a passo em markdown"},
            "category": {"type": "string", "description": "Categoria: development, infrastructure, productivity, system"},
            "toolsets_required": {"type": "array", "items": {"type": "string"}, "description": "Toolsets necessarios"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags para busca"},
        },
        "required": ["name", "description", "procedure"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args, state))

    async def _async_execute(self, args: dict, state: AgentState) -> ToolResult:
        from lux.skills.manager import SkillManager
        from lux.constants import SKILL_CREATION_THRESHOLD

        name = args.get("name", "").strip().lower().replace(" ", "-")
        description = args.get("description", "").strip()
        procedure = args.get("procedure", "").strip()
        category = args.get("category", "general")
        tags = args.get("tags", [])
        toolsets = args.get("toolsets_required", [])

        if not name or not description or not procedure:
            return ToolResult.failure("name, description e procedure sao obrigatorios.")

        tags_yaml = "\n".join(f"    - {t}" for t in tags) if tags else "    - []"
        toolsets_yaml = "\n".join(f"    - {t}" for t in toolsets) if toolsets else "    - []"

        skill_md = f"""---
name: {name}
description: "{description}"
version: 1.0.0
author: lux-agent
platforms: [linux]
metadata:
  lux:
    tags: {tags if tags else '[]'}
    category: {category}
    requires_toolsets: {toolsets if toolsets else '[]'}
    created_from_task: "{state.task_id}"
    use_count: 0
---

# {name.replace('-', ' ').title()}

## Quando Usar
{description}

## Pre-requisitos
{chr(10).join(f'- Toolset `{t}` ativo' for t in toolsets) if toolsets else '- Nenhum toolset especifico'}

## Procedimento
{procedure}

## Pitfalls
- (adicione pitfalls comuns aqui conforme encontrar)

## Verificacao
- (adicione passos de verificacao aqui)
"""

        mgr = SkillManager()

        existing = mgr.get_skills_list_l0(state.user_profile, state.channel)
        existing_names = {s.name for s in existing}
        if name in existing_names:
            return ToolResult.failure(
                f"Skill '{name}' ja existe. Use skill_view('{name}') para ve-la ou "
                f"atualize-a manualmente em ~/.lux/skills/{name}.md"
            )

        try:
            skill = await mgr.create_skill_from_task(skill_md, name)
            return ToolResult.ok(
                f"✅ Skill '/{name}' criada e salva em ~/.lux/skills/{name}.md\n"
                f"   Categoria: {category}\n"
                f"   Use /{name} para ativa-la quando precisar."
            )
        except Exception as e:
            return ToolResult.failure(f"Falha ao criar skill: {e}")
