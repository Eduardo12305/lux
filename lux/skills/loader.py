# lux/skills/loader.py
# Módulo: Skills
# Dependências: nenhuma
# Status: STUB (implementação completa no Batch 5)

from __future__ import annotations

from pathlib import Path
from typing import Optional


class SkillLoader:
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
                frontmatter_lines.append(stripped)
                continue
            body_lines.append(line)

        for fl in frontmatter_lines:
            if ":" in fl and not fl.startswith("#"):
                key, _, value = fl.partition(":")
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                if key == "name":
                    name = value
                    meta.name = value
                elif key == "description":
                    description = value
                    meta.description = value
                elif key == "version":
                    meta.version = value
                elif key == "author":
                    meta.author = value

        if not name or name == "unknown":
            first_heading = next(
                (l.lstrip("#").strip() for l in body_lines if l.startswith("# ")), None
            )
            if first_heading:
                name = first_heading.lower().replace(" ", "-")
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
