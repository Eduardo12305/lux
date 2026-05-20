# lux/tools/toolsets.py
# Módulo: Tools
# Dependências: nenhuma
# Status: IMPLEMENTADO

from __future__ import annotations

from dataclasses import dataclass, field

from lux.agent.state import UserRole


@dataclass
class Toolset:
    name: str
    description: str
    tools: list[str]
    requires_approval: bool = False
    min_role: UserRole = UserRole.USER


TOOLSETS: dict[str, Toolset] = {
    "terminal": Toolset(
        name="terminal",
        description="Execucao de comandos shell e operacoes de filesystem",
        tools=["shell_run", "file_read", "file_write", "file_append",
               "file_delete", "directory_list", "directory_create",
               "search_files", "patch_file"],
        requires_approval=True,
        min_role=UserRole.ADMIN,
    ),
    "web": Toolset(
        name="web",
        description="Busca web e extracao de conteudo de URLs",
        tools=["web_search", "web_fetch", "web_summarize"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "email": Toolset(
        name="email",
        description="Leitura e envio de e-mails via IMAP/SMTP",
        tools=["email_list", "email_read", "email_compose",
               "email_send", "email_reply", "email_search"],
        requires_approval=True,
        min_role=UserRole.USER,
    ),
    "calendar": Toolset(
        name="calendar",
        description="Calendario e lembretes",
        tools=["calendar_read", "calendar_create", "reminder_set",
               "reminder_list", "reminder_cancel"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "tasks": Toolset(
        name="tasks",
        description="Gestao de tarefas em markdown local",
        tools=["task_create", "task_list", "task_complete", "task_update"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "memory_tools": Toolset(
        name="memory_tools",
        description="Gestao explicita de memoria",
        tools=["memory", "session_search", "semantic_recall"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "skills": Toolset(
        name="skills",
        description="Gerenciamento de skills",
        tools=["skills_list", "skill_view", "skill_create", "skill_update"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "git": Toolset(
        name="git",
        description="Operacoes Git",
        tools=["git_status", "git_diff", "git_commit", "git_push",
               "git_pull", "git_log", "git_branch"],
        requires_approval=True,
        min_role=UserRole.USER,
    ),
    "system": Toolset(
        name="system",
        description="Status do sistema Lux",
        tools=["status_check", "vram_status", "session_info",
               "profile_switch", "settings_update"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
    "subagent": Toolset(
        name="subagent",
        description="Delegacao de tarefas para subagentes paralelos",
        tools=["delegate_task", "todo"],
        requires_approval=False,
        min_role=UserRole.USER,
    ),
}
