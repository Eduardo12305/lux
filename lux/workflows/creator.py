# lux/workflows/creator.py
# Módulo: Workflow Engine — Criação Autônoma de Workflows
# Dependências: parser.py, runner.py
# Status: IMPLEMENTADO
# Notas: Permite ao agente criar novos workflows .yaml automaticamente,
#   similar ao SkillCreator para skills.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lux.workflows.parser import WorkflowParser

logger = logging.getLogger(__name__)

WORKFLOW_CREATION_PROMPT = """Crie um arquivo YAML de workflow para automação com base na tarefa abaixo.

## Tarefa concluída ou necessidade detectada
{task_summary}

## Ferramentas e skills disponíveis
{available_skills}

## Workflows existentes (evite duplicatas)
{existing_workflows}

## Formato do arquivo .yaml
```yaml
id: nome_unico_do_workflow
nome: Nome Legível
descricao: O que este workflow faz
enabled: true

trigger:
  type: on_schedule    # on_start | on_schedule | on_file_change | on_email_received | on_request
  schedule: "0 9 * * *"  # cron (se type=on_schedule)
  frequency: diaria    # diaria | semanal | (se type=on_start)
  horario: "09:00"     # opcional

steps:
  - skill: nome_da_skill
    config:
      parametro1: valor1
      parametro2: valor2

  - skill: notify_user
    config:
      mensagem: "Workflow concluído!"
      prioridade: normal
```

## Skills built-in disponíveis para usar nos steps:
- web_search: busca na web (config: query, max_resultados, fontes)
- content_summarizer: resume conteúdo (config: max_tokens, idioma)
- file_summarizer: resume arquivos (config: path)
- email_summarizer: resume e-mails (config: limit)
- save_to_memory: salva na memória (config: chave, ttl_horas)
- notify_user: notifica o usuário (config: mensagem, prioridade, formato)
- index_to_memory: indexa dados na memória (config: sem parâmetros)

## Regras
1. Use id em snake_case, sem espaços
2. Priorize on_schedule para tarefas recorrentes
3. Sempre inclua notify_user como último step
4. Máximo 5 steps por workflow
5. Gere APENAS o YAML, sem explicações, sem blocos de código markdown
"""


class WorkflowCreator:
    """Criação autônoma de workflows baseada em tarefas concluídas."""

    def __init__(self, parser: Optional[WorkflowParser] = None):
        self._parser = parser or WorkflowParser()

    def build_creation_prompt(
        self,
        task_summary: str,
    ) -> str:
        existing = self._parser.discover()
        existing_names = "\n".join(
            f"- {w.id}: {w.nome} — {w.descricao}" for w in existing
        )

        available = (
            "- web_search: busca na web\n"
            "- content_summarizer: resume conteúdo\n"
            "- file_summarizer: resume arquivos\n"
            "- email_summarizer: resume e-mails\n"
            "- save_to_memory: salva na memória\n"
            "- notify_user: notifica o usuário\n"
            "- index_to_memory: indexa dados"
        )

        return WORKFLOW_CREATION_PROMPT.format(
            task_summary=task_summary,
            available_skills=available,
            existing_workflows=existing_names or "(nenhum)",
        )

    def create(self, yaml_content: str, workflow_id: str) -> Optional[Path]:
        yaml_content = yaml_content.strip()
        if yaml_content.startswith("```"):
            lines = yaml_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            yaml_content = "\n".join(lines)

        workflow_dir = self._parser.workflow_dir
        workflow_dir.mkdir(parents=True, exist_ok=True)

        file_path = workflow_dir / f"{workflow_id}.yaml"
        if file_path.exists():
            backup = workflow_dir / f"{workflow_id}.bak.yaml"
            file_path.rename(backup)
            logger.info("Backup do workflow %s criado", workflow_id)

        file_path.write_text(yaml_content)
        logger.info("Workflow criado: %s", workflow_id)
        return file_path

    def validate(self, yaml_content: str) -> tuple[bool, str]:
        try:
            wf = self._parser.parse(yaml_content)
            if wf is None:
                return False, "YAML inválido: não foi possível parsear"
            if not wf.id:
                return False, "YAML inválido: 'id' é obrigatório"
            if not wf.steps:
                return False, "YAML inválido: 'steps' é obrigatório"
            return True, f"Workflow '{wf.id}' válido com {len(wf.steps)} steps"
        except Exception as e:
            return False, f"Erro de validação: {e}"
