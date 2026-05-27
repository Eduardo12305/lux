# lux/gateway/pairing.py
# Módulo: Gateway
# Dependências: gateway/auth.py
# Status: IMPLEMENTADO
# Notas: DM pairing persistente com TTL via AuthManager.

from __future__ import annotations

import logging

from lux.gateway.auth import AuthManager

logger = logging.getLogger(__name__)


class DMPairingService:
    """
    Servico de DM pairing para autorizacao de usuarios no gateway.
    Usa AuthManager para persistencia e TTL automático.
    """

    def __init__(self, auth: AuthManager):
        self._auth = auth

    async def initiate_pairing(self, user_id: str, platform: str) -> str:
        code = await self._auth.create_pairing_code(user_id, platform)
        logger.info("Pairing iniciado: code=%s platform=%s user=%s", code, platform, user_id)
        return code

    async def confirm_pairing(self, code: str) -> str | None:
        user_id = await self._auth.verify_pairing_code(code)
        if user_id:
            logger.info("Pairing confirmado: code=%s user=%s", code, user_id)
        else:
            logger.warning("Pairing invalido ou expirado: code=%s", code)
        return user_id

    async def is_authorized(self, platform: str, user_id: str) -> bool:
        return await self._auth.is_whitelisted(platform, user_id)
