# lux/skills/manager.py
# Módulo: Skills
# Dependências: skills/loader.py, agent/state.py, constants.py
# Status: IMPLEMENTADO
# Notas: SkillManager com version store, progressive disclosure L0/L1/L2, validacao (GAP 8).

from __future__ import annotations

import logging
import platform
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from lux.agent.state import Channel, Skill, SkillSummary, UserProfile
from lux.constants import (
    SKILL_CREATION_THRESHOLD,
    SKILL_MAX_BACKUPS,
    SKILLS_BACKUPS_DIR,
    SKILLS_DIR,
)
from lux.skills.loader import SkillLoader

logger = logging.getLogger(__name__)

BUNDLED_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


class SkillVersionStore:
    """Backup e rollback de skills (GAP 8)."""

    MAX_BACKUPS = SKILL_MAX_BACKUPS

    def __init__(self, backups_dir: Optional[Path] = None):
        self._backups_dir = backups_dir or SKILLS_BACKUPS_DIR
        self._backups_dir.mkdir(parents=True, exist_ok=True)

    def backup(self, skill_name: str, content: str):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self._backups_dir / f"{skill_name}.{ts}.md.bak"
        backup_path.write_text(content)
        self._rotate(skill_name)

    def list_backups(self, skill_name: str) -> list[Path]:
        pattern = f"{skill_name}.*.md.bak"
        files = sorted(
            self._backups_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files

    def restore(self, skill_name: str, backup_file: Path) -> str:
        content = backup_file.read_text()
        skill_path = SKILLS_DIR / f"{skill_name}.md"
        skill_path.write_text(content)
        return content

    def _rotate(self, skill_name: str):
        files = sorted(
            self._backups_dir.glob(f"{skill_name}.*.md.bak"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(files) > self.MAX_BACKUPS:
            oldest = files.pop(0)
            oldest.unlink(missing_ok=True)


class SkillManager:
    """
    Gerencia ciclo de vida de skills: descoberta, carregamento L0/L1/L2,
    criacao autonoma, versionamento.
    """

    def __init__(self):
        self._loader = SkillLoader()
        self._version_store = SkillVersionStore()
        self._metadata_cache: dict[str, SkillSummary] = {}
        self._last_cache_refresh = 0.0

    # ── Level 0 ──────────────────────────────────────────────────────────

    def get_skills_list_l0(
        self, user: UserProfile, channel: Channel
    ) -> list[SkillSummary]:
        all_skills = self._load_all_metadata()
        return [s for s in all_skills if self._is_available(s, user)]

    # ── Level 1 ──────────────────────────────────────────────────────────

    def get_skill_content_l1(self, skill_name: str) -> str:
        skill_path = self._resolve_skill_path(skill_name)
        if skill_path and skill_path.exists():
            return skill_path.read_text()
        raise FileNotFoundError(f"Skill '{skill_name}' nao encontrada")

    # ── Level 2 ──────────────────────────────────────────────────────────

    def get_skill_section_l2(self, skill_name: str, section: str) -> str:
        content = self.get_skill_content_l1(skill_name)
        return self._loader.extract_section(content, section)

    # ── Criacao Autonoma ─────────────────────────────────────────────────

    async def create_skill_from_task(
        self,
        skill_content: str,
        skill_name: str,
    ) -> Skill:
        skill = Skill.from_markdown(skill_content)
        skill.metadata.author = "lux-agent"

        skill_path = SKILLS_DIR / f"{skill_name}.md"
        if skill_path.exists():
            self._version_store.backup(skill_name, skill_path.read_text())

        skill_path.write_text(skill_content)
        logger.info("Skill criada: %s", skill_name)

        self._metadata_cache.clear()
        return skill

    def should_suggest_skill(self, tool_calls_count: int) -> bool:
        if tool_calls_count < SKILL_CREATION_THRESHOLD:
            return False
        return True

    # ── Internals ────────────────────────────────────────────────────────

    def _load_all_metadata(self) -> list[SkillSummary]:
        now = time.monotonic()
        if self._metadata_cache and (now - self._last_cache_refresh) < 60:
            return list(self._metadata_cache.values())

        results: dict[str, SkillSummary] = {}

        for skills_dir in [BUNDLED_SKILLS_DIR, SKILLS_DIR]:
            if not skills_dir.exists():
                continue
            for md_file in skills_dir.glob("*.md"):
                try:
                    content = md_file.read_text()
                    skill = Skill.from_markdown(content, source_path=md_file)
                    summary = SkillSummary.from_metadata(skill.metadata)
                    if summary.name in results:
                        pass
                    results[summary.name] = summary
                except Exception as e:
                    logger.warning("Falha ao carregar skill %s: %s", md_file, e)

        self._metadata_cache = results
        self._last_cache_refresh = now
        return list(results.values())

    def _resolve_skill_path(self, skill_name: str) -> Optional[Path]:
        for skills_dir in [BUNDLED_SKILLS_DIR, SKILLS_DIR]:
            path = skills_dir / f"{skill_name}.md"
            if path.exists():
                return path
        return None

    def _is_available(
        self, skill: SkillSummary, user: UserProfile
    ) -> bool:
        if skill.name in user.disabled_skills:
            return False
        if skill.platforms and platform.system().lower() not in [
            p.lower() for p in skill.platforms
        ]:
            return False
        if skill.requires_toolsets:
            if not all(t in user.enabled_toolsets for t in skill.requires_toolsets):
                return False
        if skill.fallback_for_toolsets:
            if any(t in user.enabled_toolsets for t in skill.fallback_for_toolsets):
                return False
        return True
