# lux/acp/server.py
# Módulo: ACP
# Dependências: acp/protocol.py, agent/agent.py, websockets
# Status: IMPLEMENTADO
# Notas: Servidor WebSocket ACP para integração com IDEs (VS Code, Zed, JetBrains).

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import websockets
from websockets.asyncio.server import ServerConnection

from lux.acp.protocol import ACPRequest, ACPResponse, ACPMessageType
from lux.agent.agent import AIAgent
from lux.agent.state import Channel
from lux.config import get_config
from lux.prompt.context_files import ContextFileLoader

logger = logging.getLogger(__name__)


class ACPServer:
    """
    Servidor ACP (Agent Communication Protocol).
    Expõe WebSocket em ws://127.0.0.1:3284 para comunicação com IDEs.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
    ):
        config = get_config()
        self._host = host
        self._port = port or config.acp_port
        self._server = None
        self._running = False

    async def start(self):
        self._server = await websockets.serve(
            self._handle_connection,
            self._host,
            self._port,
        )
        self._running = True
        logger.info(
            "ACP Server iniciado em ws://%s:%d",
            self._host, self._port,
        )

    async def stop(self):
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("ACP Server parado")

    async def _handle_connection(self, websocket: ServerConnection):
        logger.info("ACP: conexao recebida de %s", websocket.remote_address)
        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                    response = await self._process_request(data)
                    await websocket.send(json.dumps(response.to_json()))
                except json.JSONDecodeError:
                    error = ACPResponse(
                        type=ACPMessageType.ERROR,
                        error="JSON invalido",
                    )
                    await websocket.send(json.dumps(error.to_json()))
                except Exception as e:
                    logger.exception("Erro no processamento ACP")
                    error = ACPResponse(
                        type=ACPMessageType.ERROR,
                        error=str(e),
                    )
                    await websocket.send(json.dumps(error.to_json()))
        except websockets.ConnectionClosed:
            logger.info("ACP: conexao fechada")
        except Exception:
            logger.exception("Erro na conexao ACP")

    async def _process_request(self, data: dict) -> ACPResponse:
        request = ACPRequest.from_json(data)
        logger.debug(
            "ACP request: user=%s msg=%s",
            request.user_id, request.message[:80],
        )

        ide_context = self._build_ide_context(request)

        agent = AIAgent(
            user_id=request.user_id or "acp_user",
            session_id=request.session_id,
            channel=Channel.ACP,
        )

        try:
            result = await agent.run_conversation(
                user_message=request.message,
                conversation_history=request.conversation_history,
            )

            tool_calls = []
            if result.messages:
                last = result.messages[-1]
                if last.tool_calls:
                    tool_calls = [
                        {
                            "id": tc.id,
                            "name": tc.function_name,
                            "arguments": tc.arguments,
                        }
                        for tc in last.tool_calls
                    ]

            return ACPResponse(
                id=request.id,
                type=ACPMessageType.RESPONSE,
                message=result.final_response,
                tool_calls=tool_calls,
                status=result.status.value,
                tokens_used=result.tokens_used,
            )
        except Exception as e:
            return ACPResponse(
                id=request.id,
                type=ACPMessageType.ERROR,
                error=str(e),
            )
        finally:
            await agent.close()

    def _build_ide_context(self, request: ACPRequest) -> str:
        parts: list[str] = []

        if request.open_file:
            fc = request.open_file
            parts.append(f"Arquivo aberto: {fc.path}")
            if fc.content:
                parts.append(
                    f"Conteudo do arquivo:\n```{fc.language or ''}\n"
                    f"{fc.content[:3000]}\n```"
                )
            if fc.selection:
                parts.append(f"Selecao:\n```\n{fc.selection[:2000]}\n```")

        if request.diagnostics:
            diag_lines = []
            for d in request.diagnostics:
                icon = {"error": "✗", "warning": "⚠", "info": "ℹ"}.get(
                    d.severity, "?"
                )
                diag_lines.append(
                    f"  {icon} [{d.severity}] {d.message} "
                    f"(linha {d.line}:{d.column})"
                )
            parts.append("Diagnostics LSP:\n" + "\n".join(diag_lines))

        if request.workspace_path:
            loader = ContextFileLoader()
            context = loader.load_for_workspace(request.workspace_path)
            for path, content in context.items():
                parts.append(f"### Context: {path}\n{content[:2000]}")

        return "\n\n".join(parts)

    @property
    def is_running(self) -> bool:
        return self._running
