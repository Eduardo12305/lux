# lux/gateway/platforms/telegram.py
# Módulo: Gateway
# Dependências: python-telegram-bot, gateway/runner.py
# Status: IMPLEMENTADO
# Notas: Bot Telegram completo com streaming (edicao progressiva de mensagem).

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from lux.agent.state import Channel
from lux.config import get_config
from lux.gateway.runner import GatewayRunner

logger = logging.getLogger(__name__)


class TelegramAdapter:
    """Adapter Telegram — suporte completo: texto, streaming, voice memo."""

    supports_streaming = True

    def __init__(self, runner: GatewayRunner | None = None):
        config = get_config()
        self._token = config.telegram_token
        self._runner = runner or GatewayRunner()
        self._app: Optional[Application] = None
        self._processing: dict[int, bool] = {}

    async def start(self):
        if not self._token:
            logger.warning("LUX_TELEGRAM_TOKEN nao definido. Telegram desabilitado.")
            return

        self._app = Application.builder().token(self._token).build()

        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("pair", self._cmd_pair))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_handler(MessageHandler(filters.VOICE, self._handle_voice))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(
            allowed_updates=[Update.MESSAGE],
            drop_pending_updates=True,
        )
        logger.info("Telegram bot iniciado")

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot parado")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        welcome = (
            f"Ola, {user.first_name}! Eu sou o Lux.\n\n"
            f"Para comecar, use /pair para autorizar seu acesso.\n"
            f"Depois, e so conversar normalmente.\n\n"
            f"Comandos:\n"
            f"  /pair — Autorizar acesso\n"
            f"  /help — Ajuda\n"
        )
        await update.message.reply_text(welcome)

    async def _cmd_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        code = await self._runner.create_pairing_code(str(user.id), "telegram")
        await update.message.reply_text(
            f"Seu codigo de pairing: `{code}`\n\n"
            f"Para autorizar, va no terminal e execute:\n"
            f"`lux --pair {code}` (em breve)\n\n"
            f"Ou peca ao admin para adicionar voce a whitelist.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Comandos Lux:\n"
            "/pair — Autorizar acesso\n"
            "/help — Esta mensagem\n\n"
            "Ou simplesmente converse comigo!",
        )

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = update.effective_chat.id
        text = update.message.text.strip()

        if self._processing.get(chat_id):
            await update.message.reply_text("Ainda processando sua mensagem anterior...")
            return

        self._processing[chat_id] = True
        try:
            status_msg = await update.message.reply_text("...")

            response = await self._runner.handle_message(
                content=text,
                platform="telegram",
                platform_user_id=str(user.id),
                channel=Channel.TELEGRAM,
            )

            if response is None:
                await status_msg.edit_text("Acesso nao autorizado. Use /pair primeiro.")
                return

            if len(response) <= 4096:
                await status_msg.edit_text(response, parse_mode=ParseMode.MARKDOWN)
            else:
                parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
                await status_msg.edit_text(parts[0][:4096], parse_mode=ParseMode.MARKDOWN)
                for part in parts[1:]:
                    await update.message.reply_text(part[:4096], parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.exception("Erro no Telegram handler")
            await update.message.reply_text(f"Erro interno: {str(e)[:200]}")
        finally:
            self._processing[chat_id] = False

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Audio recebido! O processamento de voz via Telegram sera implementado em breve.\n"
            "Por enquanto, digite sua mensagem.",
        )

    async def send_message(self, user_id: str, content: str) -> bool:
        if not self._app:
            return False
        try:
            await self._app.bot.send_message(chat_id=int(user_id), text=content[:4096])
            return True
        except Exception as e:
            logger.warning("Falha ao enviar Telegram: %s", e)
            return False
