# lux/workflows/parser.py
# Módulo: Workflow Engine — Parser YAML
# Dependências: nenhuma (parser manual, sem PyYAML)
# Status: IMPLEMENTADO
# Notas: Parser de arquivos .yaml/.yml de workflow com validação.
#   Suporta triggers, etapas encadeadas e configuração por skill.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    ON_START = "on_start"
    ON_SCHEDULE = "on_schedule"
    ON_FILE_CHANGE = "on_file_change"
    ON_EMAIL_RECEIVED = "on_email_received"
    ON_REQUEST = "on_request"


@dataclass
class WorkflowTrigger:
    type: TriggerType = TriggerType.ON_REQUEST
    schedule: str = ""
    filter_category: str = ""
    directory: str = ""
    frequency: str = ""
    horario: str = ""

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "schedule": self.schedule,
            "filter_category": self.filter_category,
            "directory": self.directory,
            "frequency": self.frequency,
            "horario": self.horario,
        }


@dataclass
class WorkflowStep:
    skill: str
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"skill": self.skill, "config": self.config}


@dataclass
class WorkflowDefinition:
    id: str
    nome: str
    descricao: str = ""
    enabled: bool = True
    trigger: WorkflowTrigger = field(default_factory=WorkflowTrigger)
    steps: list[WorkflowStep] = field(default_factory=list)
    source_path: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
            "enabled": self.enabled,
            "trigger": self.trigger.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
        }


class WorkflowParser:
    """Parser manual de arquivos YAML de workflow.

    Suporta um subconjunto de YAML suficiente para definições de workflow:
    - Chave: valor simples
    - Listas inline: [a, b]
    - Blocos aninhados com indentação de 2 espaços
    - Strings com e sem aspas
    """

    def __init__(self, workflow_dir: Optional[Path] = None):
        from lux.config import get_config
        config = get_config()
        self._workflow_dir = workflow_dir or Path(
            str(config.workflow_dir)
        ).expanduser()
        self._workflow_dir.mkdir(parents=True, exist_ok=True)

    @property
    def workflow_dir(self) -> Path:
        return self._workflow_dir

    def discover(self) -> list[WorkflowDefinition]:
        workflows = []
        for pattern in ["*.yaml", "*.yml"]:
            for yaml_file in sorted(self._workflow_dir.glob(pattern)):
                try:
                    wf = self.parse_file(yaml_file)
                    if wf:
                        workflows.append(wf)
                except Exception as e:
                    logger.warning("Falha ao parse workflow %s: %s", yaml_file, e)
        logger.info("Workflows descobertos: %d", len(workflows))
        return workflows

    def parse_file(self, path: Path) -> Optional[WorkflowDefinition]:
        if not path.exists():
            return None
        content = path.read_text()
        return self.parse(content, str(path))

    def parse(self, content: str, source_path: str = "") -> Optional[WorkflowDefinition]:
        lines = content.split("\n")
        root = self._parse_lines_to_dict(lines)
        return self._dict_to_workflow(root, source_path)

    def _parse_lines_to_dict(self, lines: list[str]) -> dict:
        result: dict = {}
        stack: list[tuple[int, dict]] = [(-1, result)]
        i = 0

        while i < len(lines):
            line = lines[i]
            if not line.strip() or line.strip().startswith("#"):
                i += 1
                continue

            indent = len(line) - len(line.lstrip())
            stripped = line.strip()

            while stack and stack[-1][0] >= indent:
                stack.pop()

            current_indent, current_dict = stack[-1]

            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                if self._is_list_item(stripped, i, lines):
                    parsed = self._parse_list_value(value)
                    current_dict[key] = parsed
                elif value == "" or value == "|":
                    i, nested = self._parse_block(lines, i + 1, indent + 2)
                    if isinstance(nested, list):
                        current_dict[key] = nested
                    elif nested:
                        sub_dict: dict = {}
                        current_dict[key] = sub_dict
                        stack.append((indent + 2, sub_dict))
                        if isinstance(nested, dict):
                            sub_dict.update(nested)
                    else:
                        current_dict[key] = {}
                        sub_dict = current_dict[key]
                        stack.append((indent + 2, sub_dict))
                    continue
                else:
                    current_dict[key] = self._parse_scalar(value)
            elif stripped.startswith("- "):
                pass

            i += 1

        return result

    def _parse_scalar(self, value: str) -> str | int | float | bool | list:
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            return self._parse_list_value(value)
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        if value.lower() in ("true", "yes"):
            return True
        if value.lower() in ("false", "no"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _parse_list_value(self, value: str) -> list:
        value = value.strip()
        if value in ("[]", ""):
            return []
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
        else:
            inner = value
        items = inner.split(",")
        return [
            self._parse_scalar(item.strip())
            for item in items
            if item.strip()
        ]

    def _is_list_item(self, line: str, idx: int, lines: list[str]) -> bool:
        return line.strip().startswith("- ")

    def _parse_block(self, lines: list[str], start: int, base_indent: int):
        result: dict = {}
        list_result: list = []
        i = start
        last_list_indent = -1

        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if line.strip().startswith("#"):
                i += 1
                continue

            indent = len(line) - len(line.lstrip())
            if indent < base_indent:
                break

            stripped = line.strip()

            if stripped.startswith("- "):
                item_value = stripped[2:].strip()
                last_list_indent = indent
                if ":" in item_value:
                    key, _, val = item_value.partition(":")
                    key = key.strip()
                    val = val.strip()
                    if val == "":
                        i, nested = self._parse_block(lines, i + 1, indent + 2)
                        if isinstance(nested, list):
                            list_result.append({key: nested})
                        elif isinstance(nested, dict):
                            list_result.append({key: nested})
                        else:
                            list_result.append({key: val})
                        continue
                    else:
                        list_result.append({key: self._parse_scalar(val)})
                else:
                    list_result.append(self._parse_scalar(item_value))
                i += 1
                continue

            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                if list_result and indent > last_list_indent and isinstance(list_result[-1], dict):
                    last = list_result[-1]
                    if value == "":
                        i, nested = self._parse_block(lines, i + 1, indent + 2)
                        last[key] = nested
                        continue
                    else:
                        last[key] = self._parse_scalar(value)
                        i += 1
                        continue

                if value == "":
                    i, nested = self._parse_block(lines, i + 1, indent + 2)
                    if isinstance(nested, list):
                        result[key] = nested
                    else:
                        result[key] = nested
                else:
                    result[key] = self._parse_scalar(value)
            i += 1

        if list_result and not result:
            return i, list_result
        return i, result

    def _dict_to_workflow(
        self, d: dict, source_path: str
    ) -> Optional[WorkflowDefinition]:
        wf_id = str(d.get("id", ""))
        if not wf_id:
            return None

        trigger_data = d.get("trigger", d.get("gatilho", {}))
        if isinstance(trigger_data, dict):
            trigger_type_str = str(
                trigger_data.get("type", trigger_data.get("tipo", "on_request"))
            ).lower()
            try:
                trigger_type = TriggerType(trigger_type_str)
            except ValueError:
                trigger_type = TriggerType.ON_REQUEST

            trigger = WorkflowTrigger(
                type=trigger_type,
                schedule=str(trigger_data.get("schedule", "")),
                filter_category=str(
                    trigger_data.get("filter_category",
                                     trigger_data.get("filtro_categoria", ""))
                ),
                directory=str(
                    trigger_data.get("directory",
                                     trigger_data.get("diretorio", ""))
                ),
                frequency=str(
                    trigger_data.get("frequency",
                                     trigger_data.get("frequencia", ""))
                ),
                horario=str(trigger_data.get("horario", "")),
            )
        else:
            trigger = WorkflowTrigger()

        steps_data = d.get("steps", d.get("etapas", []))
        steps: list[WorkflowStep] = []
        if isinstance(steps_data, list):
            for s in steps_data:
                if isinstance(s, dict):
                    steps.append(WorkflowStep(
                        skill=str(s.get("skill", "")),
                        config=s.get("config", {}),
                    ))
                elif isinstance(s, str):
                    steps.append(WorkflowStep(skill=s))

        return WorkflowDefinition(
            id=wf_id,
            nome=str(d.get("nome", d.get("name", wf_id))),
            descricao=str(d.get("descricao", d.get("description", ""))),
            enabled=bool(d.get("enabled", True)),
            trigger=trigger,
            steps=steps,
            source_path=source_path,
        )
