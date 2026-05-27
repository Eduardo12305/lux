# lux/gateway/runner.py
# Módulo: Gateway
# Dependências: agent/agent.py, gateway/auth.py, gateway/pairing.py, memory/session_db.py
# Status: IMPLEMENTADO
# Notas: Fluxo completo com _authorize() conforme secao 15.1 da arquitetura.

from __future__ import annotations

import logging
from typing import Optional

from lux.agent.agent import AIAgent
from lux.agent.state import Channel, UserProfile
from lux.gateway.auth import AuthManager
from lux.gateway.pairing import DMPairingService
from lux.gateway.session_store import SessionStore
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)


class GatewayRunner:
    """
    Processo de longa duracao que recebe mensagens de multiplas plataformas
    e despacha para AIAgent. Inspirado no gateway/run.py do Hermes.

    Fluxo (secao 15.1):
      1. _authorize() → verifica DM pairing / whitelist / JWT
      2. Resolve sessao por user_id + channel
      3. Carrega historico do SQLite
      4. Cria AIAgent com contexto da sessao
      5. Executa run_conversation()
      6. Entrega resposta pela plataforma
      7. Salva sessao atualizada
    """

    def __init__(
        self,
        auth: Optional[AuthManager] = None,
        session_db: Optional[SessionDB] = None,
    ):
        self._auth = auth or AuthManager()
        self._session_db = session_db or SessionDB()
        self._pairing = DMPairingService(self._auth)
        self._session_store = SessionStore()

    async def _authorize(
        self,
        platform: str,
        platform_user_id: str,
        token: Optional[str] = None,
    ) -> Optional[UserProfile]:
        return await self._auth.authorize(platform, platform_user_id, token)

    async def handle_message(
        self,
        content: str,
        platform: str,
        platform_user_id: str,
        channel: Channel,
        token: Optional[str] = None,
    ) -> Optional[str]:
        user = await self._authorize(platform, platform_user_id, token)
        if not user:
            logger.warning("Mensagem rejeitada: platform=%s user=%s", platform, platform_user_id)
            return None

        user.last_seen = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await self._auth.update_profile(user)

        session_id = await self._session_store.get_or_create(
            user_id=user.user_id,
            channel=channel,
        )

        history = await self._session_db.load_history(session_id, limit=50)

        agent = AIAgent(
            user_id=user.user_id,
            session_id=session_id,
            user_profile=user,
            channel=channel,
            compression_threshold=0.85,
            max_iterations=30,
        )

        result = await agent.run_conversation(
            user_message=content,
            conversation_history=history,
        )

        await self._session_db.save_messages(result.messages)
        await agent.close()

        return result.final_response

    async def start(self):
        logger.info("Gateway iniciado")

    async def stop(self):
        logger.info("Gateway parado")
        await self._auth.close()

    async def create_pairing_code(self, user_id: str, platform: str) -> str:
        return await self._pairing.initiate_pairing(user_id, platform)

    async def confirm_pairing(self, code: str) -> Optional[str]:
        return await self._pairing.confirm_pairing(code)
