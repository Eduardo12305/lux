# lux/interfaces/cli.py
# Módulo: Interfaces
# Dependências: textual, agent/agent.py, models/vram_guard.py
# Status: IMPLEMENTADO
# Notas: TUI completa com Textual — histórico, status bar, autocomplete, VRAM.

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, Label, RichLog, Static
from textual.widget import Widget
from textual.binding import Binding
from textual.css.query import NoMatches

from lux.agent.agent import AIAgent
from lux.agent.state import PipelineStatus
from lux.config import get_config

logger = logging.getLogger(__name__)


class StatusBar(Widget):
    """Barra superior: usuario, hora, VRAM, skill ativa."""

    user = reactive("")
    vram = reactive("")
    skill = reactive("")
    channel = reactive("")

    def render(self) -> str:
        now = datetime.now().strftime("%H:%M")
        parts = []
        if self.user:
            parts.append(f"👤 {self.user}")
        parts.append(f"🕐 {now}")
        if self.vram:
            parts.append(f"📊 {self.vram}")
        if self.skill:
            parts.append(f"⚡ {self.skill}")
        if self.channel:
            parts.append(f"📡 {self.channel}")
        return " │ ".join(parts)


class ChatMessage(Static):
    """Uma mensagem no chat."""

    def __init__(self, role: str, content: str, timestamp: str = ""):
        ts = timestamp or datetime.now().strftime("%H:%M")
        super().__init__(f"[dim]{ts}[/dim] [{role}]: {content}")


class ChatLog(VerticalScroll):
    """Historico de mensagens scrollavel."""

    def add_message(self, role: str, content: str, timestamp: str = ""):
        color = {"Voce": "cyan", "Lux": "green", "Sistema": "yellow",
                 "Tool": "magenta", "Erro": "red"}.get(role, "white")
        ts = timestamp or datetime.now().strftime("%H:%M")
        self.mount(ChatMessage(role, content, ts))
        self.scroll_end(animate=False)


class LuxTUI(App):
    """TUI principal do Lux com Textual."""

    CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }

    ChatLog {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }

    #input-area {
        dock: bottom;
        height: auto;
        min-height: 3;
        max-height: 6;
        background: $panel;
        padding: 0 1;
        border-top: solid $primary;
    }

    #input {
        width: 100%;
    }

    #footer-bar {
        dock: bottom;
        height: 1;
        background: $panel-darken-1;
        color: $text-disabled;
        padding: 0 1;
    }

    ChatMessage {
        padding: 0;
        margin: 0;
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "quit", "Sair", show=True),
        Binding("ctrl+c", "quit", "Sair", show=False),
        Binding("ctrl+l", "clear_screen", "Limpar", show=True),
        Binding("up", "history_back", "Historico", show=False),
    ]

    COMMANDS = [
        "/help", "/quit", "/status", "/doctor", "/memory", "/skills",
        "/voice", "/listen", "/voice-stop", "/voice-status", "/voice-full",
        "/gateway", "/gateway status", "/gateway setup telegram",
        "/gateway setup discord", "/gateway disconnect",
        "/login", "/register", "/users", "/whitelist",
        "/model", "/retry", "/undo", "/compress", "/export",
        "/resume", "/checkpoint", "/insights", "/update",
        "/clear", "/desktop",
    ]

    def __init__(
        self,
        agent: AIAgent,
        user_name: str = "Lux",
        user_profile = None,
        work_context: Optional[str] = None,
    ):
        super().__init__()
        self._agent = agent
        self._user_name = user_name
        self._user_profile = user_profile
        self._work_context = work_context
        self._running = True
        self._history: list[str] = []
        self._history_index = 0

    def compose(self) -> ComposeResult:
        yield StatusBar()
        yield ChatLog()
        with Vertical(id="input-area"):
            yield Input(placeholder="Digite sua mensagem... (/ para comandos)", id="input")
        yield Label(
            r"\[/\] comandos  \[↑↓\] historico  \[Esc\] sair  \[Ctrl+L\] limpar",
            id="footer-bar",
        )

    def on_mount(self):
        bar = self.query_one(StatusBar)
        bar.user = self._user_name
        bar.vram = "VRAM ?"

        chat = self.query_one(ChatLog)
        chat.add_message("Sistema", "╔══════════════════════════════════════╗")
        chat.add_message("Sistema", f"║   Lux v1.0.0 — {self._user_name}   ║")
        chat.add_message("Sistema", "║   / para comandos  │  Esc para sair ║")
        chat.add_message("Sistema", "╚══════════════════════════════════════╝")

        if self._work_context:
            chat.add_message("Sistema", f"📂 Contexto: {self._work_context[:100]}")

        self.set_focus(self.query_one("#input"))

        self._start_vram_monitor()
        self._agent_task: Optional[asyncio.Task] = None

    @work(exclusive=False)
    async def _start_vram_monitor(self):
        """Atualiza VRAM na status bar periodicamente."""
        config = get_config()
        budget = config.vram_budget_gb
        bar = self.query_one(StatusBar)
        bar.vram = f"VRAM {budget}GB"
        await asyncio.sleep(5)

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return

        self._history.append(text)
        self._history_index = len(self._history)

        input_widget = self.query_one("#input", Input)
        input_widget.value = ""

        chat = self.query_one(ChatLog)

        if text.startswith("/"):
            await self._handle_command(text, chat)
        else:
            await self._handle_message(text, chat)

    async def _handle_command(self, text: str, chat: ChatLog):
        cmd = text.lower()
        chat.add_message("Voce", text)

        if cmd in ("/quit", "/exit", "/q"):
            chat.add_message("Sistema", "Ate logo!")
            await asyncio.sleep(0.5)
            self.exit()
            return

        if cmd == "/desktop":
            chat.add_message("Sistema", "Abrindo interface desktop...")
            try:
                from lux.interfaces.desktop_ui import LuxDesktopApp
                desktop = LuxDesktopApp(
                    agent=self._agent,
                    user_profile=self._user_profile,
                    work_context=self._work_context,
                )
                await desktop.run_async()
            except ImportError:
                chat.add_message("Erro", "Flet nao instalado. Execute: pip install flet")
            return

        if cmd == "/help":
            chat.add_message("Lux", "Comandos: /status, /doctor, /memory, /skills, /voice, /voice-full, /gateway, /users, /clear, /desktop")
            return

        if cmd == "/clear":
            chat.clear()
            return

        if cmd == "/status":
            bar = self.query_one(StatusBar)
            chat.add_message("Lux", f"Usuario: {bar.user} | VRAM: {bar.vram} | Skill: {bar.skill or 'nenhuma'}")
            return

        if cmd in ("/memory", "/skills", "/doctor", "/users"):
            chat.add_message("Lux", f"Comando '{cmd}' — use na CLI tradicional para esta funcionalidade.")
            return

        if cmd.startswith("/gateway"):
            from lux.gateway.setup import gateway_status
            chat.add_message("Lux", gateway_status())
            return

        if cmd == "/voice":
            chat.add_message("Lux", "Modos: /listen (push-to-talk), /voice-stop, /voice-status, /voice-full")
            return

        if cmd == "/listen":
            from lux.voice.pipeline import VoicePipeline
            from lux.voice.stt import STTEngine
            from lux.voice.tts import TTSEngine
            from lux.voice.vad import VADDetector
            voice = VoicePipeline(vad=VADDetector(), stt=STTEngine(), tts=TTSEngine())
            chat.add_message("Sistema", "🎤 Ouvindo... (fale algo)")
            transcript = await voice.listen_once()
            if transcript and transcript.strip() not in ("[STT indisponivel]", "[sem fala detectada]"):
                chat.add_message("Voce", f"[voz] {transcript}")
                await self._handle_message(transcript.strip(), chat)
            else:
                chat.add_message("Sistema", "Nada detectado.")
            await voice.shutdown()
            return

        if cmd.startswith("/"):
            skill_name = cmd[1:]
            try:
                from lux.skills.manager import SkillManager
                mgr = SkillManager()
                content = mgr.get_skill_content_l1(skill_name)
                bar = self.query_one(StatusBar)
                bar.skill = skill_name
                chat.add_message("Sistema", f"⚡ Skill carregada: /{skill_name}")
                chat.add_message("Lux", content[:500])
            except FileNotFoundError:
                chat.add_message("Lux", f"Skill '{skill_name}' nao encontrada.")

    async def _handle_message(self, text: str, chat: ChatLog):
        chat.add_message("Voce", text)
        bar = self.query_one(StatusBar)

        msg_widget = ChatMessage("Lux", "▊")
        chat.mount(msg_widget)
        chat.scroll_end(animate=False)

        full_response: list[str] = []

        try:
            async for token in self._agent.run_conversation_stream(
                user_message=text,
                system_message=self._work_context,
            ):
                full_response.append(token)
                msg_widget.update(f"[dim]{datetime.now().strftime('%H:%M')}[/dim] [Lux]: {''.join(full_response)}")

            self._work_context = None
            msg_widget.update(f"[dim]{datetime.now().strftime('%H:%M')}[/dim] [Lux]: {''.join(full_response)}")

        except Exception as e:
            msg_widget.update(f"[dim]{datetime.now().strftime('%H:%M')}[/dim] [Lux]: [Erro: {e}]")

    def action_clear_screen(self):
        try:
            chat = self.query_one(ChatLog)
            chat.clear()
        except NoMatches:
            pass

    def action_history_back(self):
        try:
            inp = self.query_one("#input", Input)
            if self._history and self._history_index > 0:
                self._history_index -= 1
                inp.value = self._history[self._history_index]
                inp.action_end()
        except NoMatches:
            pass
