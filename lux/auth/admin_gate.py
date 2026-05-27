# lux/auth/admin_gate.py
# Módulo: Auth
# Dependências: auth/models.py, auth/password.py, memory/session_db.py
# Status: IMPLEMENTADO
# Notas: Protecao extra para ALWAYS_DANGEROUS — senha admin obrigatoria.

from __future__ import annotations

import getpass
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from lux.agent.state import UserRole
from lux.auth.models import AdminConfirmResult, AuthSession
from lux.auth.password import PasswordAuthenticator
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)

MAX_ADMIN_PASSWORD_ATTEMPTS = 3


class AdminPasswordGate:
    """Camada de protecao extra para comandos ALWAYS_DANGEROUS."""

    ALWAYS_DANGEROUS = [
        r"rm\s+-rf",
        r"dd\s+if=",
        r"mkfs\.",
        r">\s*/dev/(sd|nvme|hd)",
        r"chmod\s+777\s+/",
        r":\(\)\s*\{ :\|:& \};:",
        r"sudo\s+rm\s+-rf",
        r"systemctl\s+(stop|disable)\s+",
        r"iptables\s+-F",
        r"passwd\s+root",
    ]

    def __init__(self, session_db: SessionDB | None = None):
        self._db = session_db or SessionDB()
        self._password = PasswordAuthenticator(self._db)

    def is_dangerous(self, command: str) -> bool:
        return any(
            re.search(pattern, command, re.IGNORECASE)
            for pattern in self.ALWAYS_DANGEROUS
        )

    async def request_admin_confirmation(
        self,
        command: str,
        session: AuthSession,
    ) -> AdminConfirmResult:
        if session.role != UserRole.ADMIN:
            await self._audit_log(
                session.user_id, "DANGEROUS_CMD_BLOCKED",
                {"command": command, "role": session.role.value},
            )
            return AdminConfirmResult(
                approved=False, method="BLOCKED_NOT_ADMIN", attempts=0
            )

        print()
        print("⛔ Comando de alto risco detectado:")
        print(f"   $ {command}")
        print()
        print("   Este comando e IRREVERSIVEL.")
        print()

        for attempt in range(1, MAX_ADMIN_PASSWORD_ATTEMPTS + 1):
            pw = getpass.getpass(
                "   Digite sua senha de administrador para confirmar\n"
                "   ou [Enter] para cancelar: "
            )

            if not pw:
                await self._audit_log(
                    session.user_id, "DANGEROUS_CMD_CANCELLED",
                    {"command": command},
                )
                return AdminConfirmResult(
                    approved=False, method="CANCELLED", attempts=attempt
                )

            if await self._password.verify_admin_password(session.user_id, pw):
                await self._audit_log(
                    session.user_id, "DANGEROUS_CMD_APPROVED",
                    {"command": command},
                )
                return AdminConfirmResult(
                    approved=True, method="PASSWORD", attempts=attempt
                )

            remaining = MAX_ADMIN_PASSWORD_ATTEMPTS - attempt
            if remaining > 0:
                print(f"   Senha incorreta. {remaining} tentativa(s) restante(s).")
            else:
                print("   Tentativas esgotadas. Comando bloqueado.")
                await self._audit_log(
                    session.user_id, "DANGEROUS_CMD_DENIED",
                    {"command": command, "attempts": attempt},
                )

        return AdminConfirmResult(
            approved=False, method="CANCELLED", attempts=MAX_ADMIN_PASSWORD_ATTEMPTS
        )

    async def _audit_log(
        self,
        user_id: str,
        event_type: str,
        details: dict,
    ) -> None:
        import json
        await self._db._write_audit_log(
            id=uuid4().hex,
            user_id=user_id,
            event_type=event_type,
            channel="cli",
            details=json.dumps(details, ensure_ascii=False),
            source="cli",
        )
