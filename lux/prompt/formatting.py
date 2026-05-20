# lux/prompt/formatting.py
# Módulo: Prompt
# Dependências: nenhuma
# Status: IMPLEMENTADO

from __future__ import annotations

from lux.agent.state import SkillSummary


def format_skills_list_l0(skills: list[SkillSummary]) -> str:
    if not skills:
        return "## Skills Disponíveis\n\nNenhuma skill disponível no momento."

    lines = [
        "## Skills Disponíveis\n",
        "Use `skills_list()` para detalhes ou `/<skill-name>` para ativar.\n",
    ]
    for s in skills:
        cmd = f"  `/{s.name}`" if s.slash_command else ""
        lines.append(f"- **{s.name}**{cmd}: {s.description}")
    return "\n".join(lines)


def format_active_tools(tools: list[dict]) -> str:
    if not tools:
        return "## Ferramentas Disponíveis\n\nNenhuma ferramenta ativa."
    lines = ["## Ferramentas Disponíveis\n"]
    for t in tools:
        fn = t.get("function", {})
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        lines.append(f"- **{name}**: {desc}")
    return "\n".join(lines)


def format_behavior_instructions(
    preferred_language: str = "pt-BR",
    response_style: str = "balanced",
    formality: str = "casual",
    channel: str = "cli",
) -> str:
    return f"""
## Comportamento

Idioma: {preferred_language}
Estilo: {response_style} | Formalidade: {formality}
Canal: {channel}

Regras de memória:
- Use `memory(action="add", target="memory")` para persistir fatos do ambiente
- Use `memory(action="add", target="user")` para persistir preferencias do usuario
- Salve PROATIVAMENTE — nao espere ser pedido
- Quando memoria estiver cheia, consolide entradas antigas antes de adicionar novas

Regras de skills:
- Carregue skills completas (L1) apenas quando necessario para a tarefa atual
- Apos tarefas complexas bem-sucedidas (>5 steps), considere criar uma nova skill
""".strip()


def format_model_specific_instructions() -> str:
    return """
## Instruções para Qwen3

- Use `/<skill-name>` para ativar skills
- Use `<think>...</think>` para raciocinio quando necessario (thinking mode)
- Ferramentas retornam resultados estruturados — use os dados, nao invente
- Se uma tool call falhar, corrija os argumentos e tente novamente (max 3x)
- Nunca invente ferramentas — use apenas as listadas acima
""".strip()


def format_subagent_instructions(
    max_iterations: int = 20,
    parent_task_id: str = "",
) -> str:
    return f"""
## Modo Subagente

Você é um subagente com budget limitado.
Max iteracoes: {max_iterations}
Tarefa pai: {parent_task_id}

Regras:
- Escopo limitado a tarefa delegada
- Nao use delegate_task (nao crie sub-subagentes)
- Responda apenas o resultado da tarefa — sem conversa
- Se nao conseguir completar em {max_iterations} iteracoes, retorne o progresso
""".strip()
