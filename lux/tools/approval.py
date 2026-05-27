# lux/tools/approval.py
# Módulo: Tools
# Dependências: agent/state.py, tools/toolsets.py
# Status: IMPLEMENTADO

from __future__ import annotations

import logging
import re
from typing import Optional

from lux.agent.state import (
    AgentState,
    ApprovalPattern,
    ApprovalRequest,
    ApprovalResult,
    UserRole,
)
from lux.auth.admin_gate import AdminPasswordGate
from lux.tools.toolsets import TOOLSETS

logger = logging.getLogger(__name__)


class ApprovalSystem:
    """
    Detecta comandos perigosos e gerencia aprovacao do usuario.
    ALWAYS_DANGEROUS: bloqueados sempre.
    WARN_PATTERNS: pedem aprovacao mas nao bloqueiam.
    AdminPasswordGate: protecao extra para comandos perigosos (admin).
    """

class ApprovalSystem:
    """
    Detecta comandos perigosos e gerencia aprovacao do usuario.
    ALWAYS_DANGEROUS: bloqueados sempre.
    WARN_PATTERNS: pedem aprovacao mas nao bloqueiam.
    AdminPasswordGate: protecao extra para comandos perigosos (admin).
    """

    ALWAYS_DANGEROUS = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+~",
        r"dd\s+if=",
        r"mkfs\.",
        r">\s*/dev/(sd|nvme|hd)",
        r"curl\s+.*\|\s*(sudo\s+)?ba?sh",
        r"wget\s+.*\|\s*(sudo\s+)?ba?sh",
        r"chmod\s+777\s+/",
        r":\(\)\s*\{ :\|:& \};:",
        r"sudo\s+rm\s+-rf",
    ]

    WARN_PATTERNS = [
        r"\bsudo\b",
        r"\bdrop\s+table\b",
        r"\bdelete\s+from\b",
        r"\btruncate\b",
        r"\bgit\s+push\s+--force\b",
        r"\bgit\s+reset\s+--hard\b",
        r"pkill\s+-9",
        r"kill\s+-9",
    ]

    def __init__(self, admin_gate: AdminPasswordGate | None = None):
        self._admin_gate = admin_gate or AdminPasswordGate()

    def requires_approval(
        self,
        tool_name: str,
        args: dict,
        state: AgentState,
    ) -> bool:
        command = args.get("command", "") if tool_name == "shell_run" else ""

        for pattern in state.user_profile.approval_patterns:
            if re.search(pattern.regex, command or tool_name):
                return False

        for pattern in self.ALWAYS_DANGEROUS:
            if re.search(pattern, command, re.IGNORECASE):
                return True

        toolset = self._get_toolset_for_tool(tool_name)
        if toolset and toolset.requires_approval:
            for allow in state.user_profile.approval_patterns:
                if allow.toolset == toolset.name and allow.always_allow:
                    return False
            return True

        for pattern in self.WARN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True

        return False

    def check_dangerous_for_role(
        self, command: str, role: UserRole
    ) -> str:
        """Retorna BLOCKED, ADMIN_PASSWORD_REQUIRED, ou APPROVAL_REQUIRED."""
        if self._admin_gate.is_dangerous(command):
            if role != UserRole.ADMIN:
                return "BLOCKED"
            return "ADMIN_PASSWORD_REQUIRED"
        return "APPROVAL_REQUIRED"

    def request_approval(
        self,
        tool_name: str,
        args: dict,
        state: AgentState,
        callback: Optional[callable] = None,
    ) -> ApprovalResult:
        preview = self._format_command_preview(tool_name, args)

        if callback:
            return callback(preview, tool_name, args)

        print(f"\n⚠️  Aprovacao necessaria:\n{preview}\n")
        choice = input("[s]im / [n]ao / [a]uto-aprovar sempre: ").strip().lower()
        match choice:
            case "s" | "sim" | "y" | "yes":
                return ApprovalResult(approved=True)
            case "a" | "auto":
                if tool_name == "shell_run":
                    cmd = args.get("command", "")
                    if cmd:
                        pattern = ApprovalPattern(
                            label=f"auto: {cmd[:60]}",
                            regex=re.escape(cmd),
                            toolset=self._get_toolset_name(tool_name),
                            always_allow=True,
                        )
                        state.user_profile.approval_patterns.append(pattern)
                return ApprovalResult(approved=True, added_to_allowlist=True)
            case _:
                return ApprovalResult(approved=False)

    def _get_toolset_for_tool(self, tool_name: str):
        for ts in TOOLSETS.values():
            if tool_name in ts.tools:
                return ts
        return None

    def _get_toolset_name(self, tool_name: str) -> str:
        ts = self._get_toolset_for_tool(tool_name)
        return ts.name if ts else ""

    def _format_command_preview(self, tool_name: str, args: dict) -> str:
        if tool_name == "shell_run":
            cmd = args.get("command", "")
            wd = args.get("working_dir", "")
            return f"Comando: {cmd}\nDiretorio: {wd or '(atual)'}"
        return f"Tool: {tool_name}\nArgs: {args}"
