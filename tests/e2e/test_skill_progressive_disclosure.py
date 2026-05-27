# tests/e2e/test_skill_progressive_disclosure.py
# Cenário: Skill criada autonomamente + Progressive disclosure L0/L1/L2

from __future__ import annotations

import pytest

from lux.agent.state import Channel, UserProfile, UserRole
from lux.skills.manager import SkillManager
from lux.skills.loader import SkillLoader


@pytest.fixture
def skill_manager():
    return SkillManager()


@pytest.fixture
def user():
    return UserProfile(
        user_id="u1", username="test", display_name="Test",
        role=UserRole.ADMIN,
        enabled_toolsets=["terminal", "skills"],
    )


def test_skill_loader_parse(skill_manager):
    """SKILL.md é parseado corretamente."""
    content = """---
name: deploy-docker
description: "Deploy de container Docker"
version: 1.0.0
author: lux-agent
platforms: [linux]
---
# Deploy Docker

## Quando Usar
Deploy de imagens Docker.

## Procedimento

### Build
```bash
docker build -t app .
```
"""
    loader = SkillLoader()
    skill = loader.parse(content)
    assert skill.name == "deploy-docker"
    assert "Deploy de container Docker" in skill.description


def test_skill_loader_extract_section():
    """L2: extrai seção específica."""
    loader = SkillLoader()
    content = """# Deploy Docker

## Quando Usar
Contexto.

## Procedimento

### Build
Faz build.

### Deploy
Faz deploy.
"""
    section = loader.extract_section(content, "Procedimento")
    assert "### Build" in section
    assert "### Deploy" in section

    not_found = loader.extract_section(content, "Inexistente")
    assert not_found == ""


def test_skill_loader_extract_subsection():
    """L2: extrai sub-seção específica."""
    loader = SkillLoader()
    content = """# Skill

## Procedimento

### Passo 1
Faz X.

### Passo 2
Faz Y.

## Verificacao
Verifica Z.
"""
    section = loader.extract_section(content, "Procedimento")
    assert "Faz X" in section
    assert "Faz Y" in section
    assert "Verifica Z" not in section


@pytest.mark.asyncio
async def test_skill_manager_l0_list(skill_manager, user):
    """L0: lista retorna skills disponíveis."""
    skills = skill_manager.get_skills_list_l0(user, Channel.CLI)
    assert isinstance(skills, list)


@pytest.mark.asyncio
async def test_skill_manager_l1_load():
    """L1: conteúdo completo carregado ou FileNotFoundError se não existe."""
    mgr = SkillManager()
    try:
        content = mgr.get_skill_content_l1("plan")
        assert len(content) > 0
    except FileNotFoundError:
        pass


@pytest.mark.asyncio
async def test_skill_manager_l2_section():
    """L2: seção específica extraída."""
    mgr = SkillManager()
    try:
        content = mgr.get_skill_section_l2("plan", "Procedimento")
        assert isinstance(content, str)
    except FileNotFoundError:
        pass


def test_skill_loader_minimal():
    """Skill sem frontmatter usa primeiro heading como nome."""
    loader = SkillLoader()
    skill = loader.parse("# Minha Skill\n\nConteudo.")
    assert skill.name == "minha-skill"


@pytest.mark.asyncio
async def test_skill_disabled_not_in_l0(skill_manager):
    """Skills desabilitadas não aparecem na lista L0."""
    user_with_disabled = UserProfile(
        user_id="u2", username="test2", display_name="Test2",
        role=UserRole.USER,
        disabled_skills=["plan"],
        enabled_toolsets=["skills"],
    )
    skills = skill_manager.get_skills_list_l0(user_with_disabled, Channel.CLI)
    names = [s.name for s in skills]
    assert "plan" not in names


def test_skill_parser_validates_structure():
    """Parser não quebra com frontmatter vazio."""
    loader = SkillLoader()
    skill = loader.parse("---\n---\n# Skill\nConteudo")
    assert skill.name is not None


def test_skill_parser_body_only():
    """Parser funciona sem frontmatter."""
    loader = SkillLoader()
    skill = loader.parse("# Deploy Docker\n\n## Procedimento\nPasso 1")
    assert skill.name == "deploy-docker"
