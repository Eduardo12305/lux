# lux/tools/implementations/workflow_tools.py
# Módulo: Tools — Gerenciamento de Workflows pelo Agente
# Dependências: workflows/creator.py, workflows/parser.py, workflows/runner.py
# Status: IMPLEMENTADO
# Notas: Permite ao agente criar, listar, ativar/desativar e remover workflows.
#   Os workflows rodam em background sem travar o agente.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lux.agent.state import AgentState, ToolResult
from lux.tools.base import Tool
from lux.workflows.creator import WorkflowCreator
from lux.workflows.parser import WorkflowParser
from lux.workflows.runner import WorkflowRunner

logger = logging.getLogger(__name__)


class WorkflowListTool(Tool):
    name = "workflow_list"
    description = "Lista todos os workflows configurados e seus status"
    parameters_schema = {
        "type": "object",
        "properties": {},
    }

    def __init__(
        self,
        parser: Optional[WorkflowParser] = None,
        runner: Optional[WorkflowRunner] = None,
    ):
        self._parser = parser or WorkflowParser()
        self._runner = runner

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        workflows = self._parser.discover()
        if not workflows:
            return ToolResult.ok(
                "Nenhum workflow encontrado. Use workflow_create para criar um."
            )

        lines = [f"Workflows ({len(workflows)}):"]
        for w in workflows:
            status_icon = "✅" if w.enabled else "⏸️"
            trigger_label = w.trigger.type.value
            lines.append(
                f"  {status_icon} {w.id} — {w.nome}"
            )
            lines.append(f"     Trigger: {trigger_label} | Steps: {len(w.steps)}")
            if w.descricao:
                lines.append(f"     {w.descricao[:80]}")

        return ToolResult.ok("\n".join(lines))


class WorkflowViewTool(Tool):
    name = "workflow_view"
    description = "Exibe o conteúdo YAML completo de um workflow"
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "ID do workflow a visualizar",
            },
        },
        "required": ["workflow_id"],
    }

    def __init__(self, parser: Optional[WorkflowParser] = None):
        self._parser = parser or WorkflowParser()

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        wf_id = args.get("workflow_id", "")
        file_path = self._parser.workflow_dir / f"{wf_id}.yaml"
        if not file_path.exists():
            file_path = self._parser.workflow_dir / f"{wf_id}.yml"
        if not file_path.exists():
            return ToolResult.failure(f"Workflow '{wf_id}' não encontrado.")

        content = file_path.read_text()
        return ToolResult.ok(f"```yaml\n{content}\n```")


class WorkflowCreateTool(Tool):
    name = "workflow_create"
    description = (
        "Cria um novo workflow de automação. "
        "Gere o YAML e forneça o id. O workflow será salvo e carregado automaticamente. "
        "Workflows rodam em background sem travar o agente."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "ID único do workflow (snake_case, ex: backup_diario)",
            },
            "yaml_content": {
                "type": "string",
                "description": "Conteúdo YAML completo do workflow",
            },
        },
        "required": ["workflow_id", "yaml_content"],
    }

    def __init__(
        self,
        creator: Optional[WorkflowCreator] = None,
        runner: Optional[WorkflowRunner] = None,
    ):
        self._creator = creator or WorkflowCreator()
        self._runner = runner

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        wf_id = args.get("workflow_id", "").strip()
        yaml_content = args.get("yaml_content", "").strip()

        if not wf_id or not yaml_content:
            return ToolResult.failure("workflow_id e yaml_content são obrigatórios.")

        wf_id = wf_id.lower().replace(" ", "_").replace("-", "_")

        valid, msg = self._creator.validate(yaml_content)
        if not valid:
            return ToolResult.failure(f"Workflow inválido: {msg}")

        file_path = self._creator.create(yaml_content, wf_id)
        if not file_path:
            return ToolResult.failure("Falha ao salvar o workflow.")

        if self._runner:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._runner.reload())
            except RuntimeError:
                pass

        return ToolResult.ok(
            f"Workflow '{wf_id}' criado em {file_path}.\n"
            "Ele será carregado automaticamente e executará em background."
        )


class WorkflowToggleTool(Tool):
    name = "workflow_toggle"
    description = "Ativa ou desativa um workflow existente"
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "ID do workflow a ativar/desativar",
            },
            "enabled": {
                "type": "boolean",
                "description": "true para ativar, false para desativar",
            },
        },
        "required": ["workflow_id", "enabled"],
    }

    def __init__(self, parser: Optional[WorkflowParser] = None):
        self._parser = parser or WorkflowParser()

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        wf_id = args.get("workflow_id", "")
        enabled = args.get("enabled", True)

        file_path = self._parser.workflow_dir / f"{wf_id}.yaml"
        if not file_path.exists():
            file_path = self._parser.workflow_dir / f"{wf_id}.yml"
        if not file_path.exists():
            return ToolResult.failure(f"Workflow '{wf_id}' não encontrado.")

        content = file_path.read_text()
        new_enabled = "enabled: true" if enabled else "enabled: false"
        import re
        content = re.sub(r"enabled:\s*(true|false|yes|no)", new_enabled, content)
        file_path.write_text(content)

        status = "ativado" if enabled else "desativado"
        return ToolResult.ok(f"Workflow '{wf_id}' {status}.")


class WorkflowDeleteTool(Tool):
    name = "workflow_delete"
    description = "Remove um workflow permanentemente"
    parameters_schema = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "ID do workflow a remover",
            },
        },
        "required": ["workflow_id"],
    }

    def __init__(self, parser: Optional[WorkflowParser] = None):
        self._parser = parser or WorkflowParser()

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        wf_id = args.get("workflow_id", "")

        file_path = self._parser.workflow_dir / f"{wf_id}.yaml"
        if not file_path.exists():
            file_path = self._parser.workflow_dir / f"{wf_id}.yml"
        if not file_path.exists():
            return ToolResult.failure(f"Workflow '{wf_id}' não encontrado.")

        backup = self._parser.workflow_dir / f"{wf_id}.removed.yaml"
        file_path.rename(backup)

        return ToolResult.ok(
            f"Workflow '{wf_id}' removido. Backup em {backup}"
        )
