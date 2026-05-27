# lux/skills/loader.py
# Módulo: Skills
# Dependências: nenhuma
# Status: IMPLEMENTADO
# Notas: Parser de frontmatter YAML simplificado + extração de seções para L0/L1/L2.

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_LIST_RE = re.compile(r"^\[(.*)\]$")


class SkillLoader:
    """Parser de arquivos .md com frontmatter YAML simples.

    Suporta:
    - Pares chave: valor simples
    - Listas inline: [item1, item2]
    - Bloco metadata.lux aninhado (2 espaços)
    """

    def parse(self, content: str, source_path: Optional[Path] = None) -> "Skill":
        from lux.agent.state import Skill, SkillMetadata

        meta = SkillMetadata()
        name = "unknown"
        description = ""
        in_frontmatter = False
        frontmatter_lines: list[str] = []
        body_lines: list[str] = []

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "---":
                if not in_frontmatter and not frontmatter_lines:
                    in_frontmatter = True
                    continue
                elif in_frontmatter:
                    in_frontmatter = False
                    continue
            if in_frontmatter:
                frontmatter_lines.append(line)
                continue
            body_lines.append(line)

        if frontmatter_lines:
            self._parse_frontmatter(frontmatter_lines, meta)

        name = meta.name or self._extract_name_from_body(body_lines)
        description = meta.description or ""
        if not meta.name:
            meta.name = name

        return Skill(
            name=name,
            description=description,
            raw_content=content,
            metadata=meta,
            source_path=source_path,
        )

    def extract_section(self, content: str, section: str) -> str:
        lines = content.split("\n")
        in_target = False
        result: list[str] = []
        target_heading = f"## {section}"
        target_heading_alt = f"### {section}"

        for line in lines:
            stripped = line.strip()
            if stripped in (target_heading, target_heading_alt):
                in_target = True
                continue
            if in_target:
                if stripped.startswith("## "):
                    break
                result.append(line)

        return "\n".join(result).strip()

    # ── Frontmatter parsing ────────────────────────────────────────────────

    @staticmethod
    def _parse_list(raw: str) -> list[str]:
        raw = raw.strip()
        if raw in ("", "[]"):
            return []
        m = _LIST_RE.match(raw)
        if m:
            items = m.group(1).split(",")
            return [i.strip().strip('"').strip("'") for i in items if i.strip()]
        return [raw.strip('"').strip("'")]

    @staticmethod
    def _parse_value(raw: str) -> str | int | float | list[str] | None:
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            return SkillLoader._parse_list(raw)
        if raw.startswith('"') or raw.startswith("'"):
            return raw.strip('"').strip("'")
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        if raw.lower() in ("null", "none", ""):
            return None
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass
        return raw

    def _parse_frontmatter(self, lines: list[str], meta: "SkillMetadata"):
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            if ":" in stripped and not stripped.startswith(" "):
                key, _, value = stripped.partition(":")
                key = key.strip().lower()
                value = value.strip()

                if key == "metadata" and (not value or value == ""):
                    i = self._parse_metadata_block(lines, i + 1, meta)
                else:
                    self._apply_field(key, value, meta)

            i += 1

    def _parse_metadata_block(self, lines: list[str], start: int, meta: "SkillMetadata") -> int:
        i = start
        while i < len(lines):
            line = lines[i]
            if not line.startswith("  ") or not line.strip():
                return i

            stripped = line.strip()
            if stripped.startswith("#"):
                i += 1
                continue

            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip().lower()
                value = value.strip()

                if key == "lux" and (not value or value == ""):
                    i = self._parse_lux_block(lines, i + 1, meta)
                else:
                    self._apply_field(key, value, meta)
            i += 1

        return i

    def _parse_lux_block(self, lines: list[str], start: int, meta: "SkillMetadata") -> int:
        i = start
        while i < len(lines):
            line = lines[i]
            if not line.startswith("    ") or not line.strip():
                if not line.startswith("    ") and line.strip():
                    return i
                i += 1
                continue

            stripped = line.strip()
            if stripped.startswith("#"):
                i += 1
                continue

            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip().lower()
                value = value.strip()
                self._apply_field(key, value, meta)
            i += 1

        return i

    def _apply_field(self, key: str, value: str, meta: "SkillMetadata"):
        parsed = self._parse_value(value)

        if key == "name":
            meta.name = str(parsed) if parsed else ""
        elif key == "description":
            meta.description = str(parsed) if parsed else ""
        elif key == "version":
            meta.version = str(parsed) if parsed else "1.0.0"
        elif key == "author":
            meta.author = str(parsed) if parsed else ""
        elif key == "platforms":
            meta.platforms = parsed if isinstance(parsed, list) else [str(parsed)] if parsed else []
        elif key == "tags":
            meta.tags = parsed if isinstance(parsed, list) else [str(parsed)] if parsed else []
        elif key == "category":
            meta.category = str(parsed) if parsed else ""
        elif key == "requires_toolsets":
            meta.requires_toolsets = parsed if isinstance(parsed, list) else [str(parsed)] if parsed else []
        elif key == "fallback_for_toolsets":
            meta.fallback_for_toolsets = parsed if isinstance(parsed, list) else [str(parsed)] if parsed else []
        elif key == "created_from_task":
            meta.created_from_task = str(parsed) if parsed else ""
        elif key == "quality_score":
            meta.quality_score = float(parsed) if isinstance(parsed, (int, float)) else 0.0
        elif key == "use_count":
            meta.use_count = int(parsed) if isinstance(parsed, (int, float)) else 0
        elif key == "last_used":
            meta.last_used = str(parsed) if parsed else None
        elif key == "config":
            if isinstance(parsed, list):
                meta.config = [{"key": i} for i in parsed]
        elif key == "slash_command":
            pass

    @staticmethod
    def _extract_name_from_body(body_lines: list[str]) -> str:
        for line in body_lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped.lstrip("#").strip().lower().replace(" ", "-")
        return "unknown"
