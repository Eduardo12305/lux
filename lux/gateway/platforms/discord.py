# lux/gateway/platforms/discord.py
# Módulo: Gateway
# Dependências: discord.py, gateway/runner.py
# Status: IMPLEMENTADO
# Notas: Bot Discord completo com slash commands, streaming, thread por conversa.

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

from lux.agent.state import Channel
from lux.config import get_config
from lux.gateway.runner import GatewayRunner

logger = logging.getLogger(__name__)


class DiscordAdapter:
    """Adapter Discord — slash commands, embeds, thread por conversa."""

    supports_streaming = True

    def __init__(self, runner: GatewayRunner | None = None):
        config = get_config()
        self._token = config.discord_token
        self._runner = runner or GatewayRunner()
        self._bot: Optional[commands.Bot] = None
        self._processing: dict[int, bool] = {}
        self._threads: dict[int, int] = {}

    async def start(self):
        if not self._token:
            logger.warning("LUX_DISCORD_TOKEN nao definido. Discord desabilitado.")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True

        self._bot = commands.Bot(command_prefix="!", intents=intents)

        @self._bot.event
        async def on_ready():
            logger.info("Discord bot conectado como %s", self._bot.user.name)
            try:
                synced = await self._bot.tree.sync()
                logger.info("Slash commands sincronizados: %d", len(synced))
            except Exception as e:
                logger.warning("Falha ao sincronizar slash commands: %s", e)

        @self._bot.tree.command(name="pair", description="Gerar codigo de pairing para autorizar acesso")
        async def pair_cmd(interaction: discord.Interaction):
            code = await self._runner.create_pairing_code(str(interaction.user.id), "discord")
            await interaction.response.send_message(
                f"Seu codigo de pairing: `{code}`\n\n"
                f"Para autorizar, peca ao admin para adicionar voce a whitelist.",
                ephemeral=True,
            )

        @self._bot.tree.command(name="ask", description="Perguntar ao Lux")
        async def ask_cmd(interaction: discord.Interaction, pergunta: str):
            await interaction.response.defer()
            response = await self._get_response(str(interaction.user.id), pergunta, Channel.DISCORD)
            if response is None:
                await interaction.followup.send("Acesso nao autorizado. Use /pair primeiro.", ephemeral=True)
                return
            await interaction.followup.send(response[:2000])
            if len(response) > 2000:
                for i in range(2000, len(response), 2000):
                    await interaction.followup.send(response[i:i+2000])

        @self._bot.event
        async def on_message(message: discord.Message):
            if message.author.bot:
                return
            if not message.guild and not message.content.startswith("!"):
                await self._handle_dm(message)

        await self._bot.start(self._token)

    async def stop(self):
        if self._bot:
            await self._bot.close()
            logger.info("Discord bot parado")

    async def _handle_dm(self, message: discord.Message):
        user_id = str(message.author.id)
        if self._processing.get(message.author.id):
            await message.channel.send("Ainda processando sua mensagem anterior...")
            return

        self._processing[message.author.id] = True
        try:
            async with message.channel.typing():
                response = await self._get_response(user_id, message.content, Channel.DISCORD)

            if response is None:
                await message.channel.send(
                    f"Ola {message.author.display_name}! Acesso nao autorizado.\n"
                    f"Use `!pair` para gerar um codigo de autorizacao."
                )
                return

            await message.channel.send(response[:2000])
            for i in range(2000, len(response), 2000):
                await message.channel.send(response[i:i+2000])

        except Exception as e:
            logger.exception("Erro no Discord handler")
            await message.channel.send(f"Erro interno: {str(e)[:200]}")
        finally:
            self._processing[message.author.id] = False

    async def _get_response(self, user_id: str, text: str, channel: Channel) -> Optional[str]:
        return await self._runner.handle_message(
            content=text,
            platform="discord",
            platform_user_id=user_id,
            channel=channel,
        )

    async def send_message(self, user_id: str, content: str) -> bool:
        if not self._bot:
            return False
        try:
            user = await self._bot.fetch_user(int(user_id))
            await user.send(content[:2000])
            return True
        except Exception as e:
            logger.warning("Falha ao enviar Discord DM: %s", e)
            return False
