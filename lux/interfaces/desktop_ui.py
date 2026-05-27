# lux/interfaces/gradio_ui.py → lux/interfaces/desktop_ui.py
# Módulo: Interfaces
# Dependências: flet, agent/agent.py
# Status: IMPLEMENTADO
# Notas: Desktop app estilo Jarvis com tema Lux. Streaming de texto + voz simultaneos.

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Optional

import flet as ft

from lux.agent.agent import AIAgent
from lux.agent.state import Channel, UserProfile
from lux.config import get_config
from lux.voice.tts import SentenceSplitter, TTSEngine

logger = logging.getLogger(__name__)


class LuxDesktopApp:
    """Desktop app estilo Jarvis com tema Lux escuro."""

    def __init__(
        self,
        agent: AIAgent,
        user_profile: UserProfile,
        work_context: Optional[str] = None,
    ):
        self._agent = agent
        self._user = user_profile
        self._work_context = work_context
        self._tts = TTSEngine()
        self._splitter = SentenceSplitter()
        self._voice_active = False

    async def run_async(self):
        await ft.app_async(target=self._main, name="Lux")

    async def _main(self, page: ft.Page):
        page.title = "Lux — Assistente Pessoal"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = "#0a0e17"
        page.window.width = 900
        page.window.height = 700
        page.window.min_width = 600
        page.window.min_height = 400
        page.padding = 0
        page.fonts = {"Roboto": "Roboto"}

        chat = ft.ListView(
            expand=True,
            spacing=8,
            padding=15,
            auto_scroll=True,
        )

        status = ft.Text(
            "● Online",
            size=12,
            color="#4ade80",
            weight=ft.FontWeight.W_500,
        )
        vram_text = ft.Text(
            f"VRAM {get_config().vram_budget_gb}GB",
            size=11,
            color="#64748b",
        )

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Text("LUX", size=20, weight=ft.FontWeight.BOLD,
                            color="#4ade80", font_family="monospace"),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Row([status, ft.Text(" │ ", color="#334155"), vram_text]),
                    ),
                    ft.Text(
                        self._user.display_name or self._user.username,
                        size=13, color="#94a3b8",
                    ),
                    ft.Text("  ", size=13),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.padding.Padding(left=20, top=12, right=20, bottom=12),
            bgcolor="#0f172a",
            border=ft.border.Border(bottom=ft.border.BorderSide(1, "#1e293b")),
        )

        input_field = ft.TextField(
            hint_text="Mensagem... (/ para comandos)",
            border_color="#1e293b",
            focused_border_color="#4ade80",
            bgcolor="#0f172a",
            text_size=14,
            multiline=False,
            shift_enter=True,
            min_lines=1,
            max_lines=4,
            cursor_color="#4ade80",
            content_padding=ft.padding.Padding(left=15, top=15, right=15, bottom=15),
            border_radius=12,
        )

        voice_btn = ft.IconButton(
            icon=ft.Icons.MIC,
            icon_color="#64748b",
            tooltip="Push-to-talk",
        )
        send_btn = ft.IconButton(
            icon=ft.Icons.SEND,
            icon_color="#4ade80",
            tooltip="Enviar",
        )

        input_row = ft.Container(
            content=ft.Row(
                [voice_btn, input_field, send_btn],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.padding.Padding(left=20, top=10, right=20, bottom=15),
            bgcolor="#0f172a",
            border=ft.border.Border(top=ft.border.BorderSide(1, "#1e293b")),
        )

        page.add(header)
        page.add(chat)
        page.add(input_row)
        page.update()

        await self._add_system_message(
            chat, page,
            "╔══════════════════════════════════╗\n"
            "║   Lux v1.0.0 — Desktop           ║\n"
            "║   Seu assistente pessoal local   ║\n"
            "╚══════════════════════════════════╝"
        )

        if self._work_context:
            await self._add_system_message(chat, page, f"📂 {self._work_context}")

        async def send_message(e):
            text = input_field.value.strip()
            if not text:
                return
            input_field.value = ""
            page.update()

            if text.startswith("/"):
                await self._handle_command(text, chat, page)
                return

            await self._add_user_message(chat, page, text)

            msg = await self._add_assistant_placeholder(chat, page)
            full_response = []
            needs_flush = True

            try:
                async for token in self._agent.run_conversation_stream(
                    user_message=text,
                    system_message=self._work_context,
                ):
                    full_response.append(token)
                    self._work_context = None
                    msg.value = "".join(full_response)
                    msg.update()

                    if self._voice_active:
                        sentence = self._splitter.feed(token)
                        if sentence:
                            await self._speak_async(sentence)
            except Exception as e:
                msg.value = f"[Erro: {e}]"
                msg.update()
            finally:
                if self._voice_active:
                    remaining = self._splitter.flush()
                    if remaining:
                        await self._speak_async(remaining)

        async def voice_handler(e):
            from lux.voice.pipeline import VoicePipeline
            from lux.voice.stt import STTEngine
            from lux.voice.vad import VADDetector

            voice_btn.icon = ft.Icons.MIC
            voice_btn.icon_color = "#ef4444"
            voice_btn.update()

            voice = VoicePipeline(vad=VADDetector(), stt=STTEngine(), tts=self._tts)
            transcript = await voice.listen_once()

            voice_btn.icon = ft.Icons.MIC
            voice_btn.icon_color = "#64748b"
            voice_btn.update()

            if transcript and transcript.strip() not in ("[STT indisponivel]", "[sem fala detectada]"):
                input_field.value = transcript.strip()
                input_field.update()
                await send_message(None)
            await voice.shutdown()

        send_btn.on_click = send_message
        voice_btn.on_click = voice_handler

        async def on_keyboard(e: ft.KeyboardEvent):
            if e.key == "Enter" and not e.shift:
                await send_message(None)

        page.on_keyboard_event = on_keyboard

    async def _add_user_message(self, chat, page, text: str):
        container = ft.Container(
            content=ft.Column([
                ft.Text("Você", size=11, weight=ft.FontWeight.BOLD, color="#4ade80"),
                ft.Text(text, size=14, color="#e2e8f0"),
                ft.Text(datetime.now().strftime("%H:%M"), size=10, color="#475569"),
            ]),
            bgcolor="#0f172a",
            border_radius=12,
            padding=15,
            margin=ft.margin.Margin(left=0, top=0, right=0, bottom=4),
            alignment=ft.alignment.Alignment(1, 0),
        )
        chat.controls.append(container)
        page.update()

    async def _add_system_message(self, chat, page, text: str):
        chat.controls.append(
            ft.Container(
                content=ft.Text(text, size=12, color="#64748b", font_family="monospace"),
                bgcolor="#0f172a",
                border_radius=12,
                padding=15,
                margin=ft.margin.Margin(left=0, top=0, right=0, bottom=4),
            )
        )
        page.update()

    async def _handle_command(self, text: str, chat, page):
        cmd = text.lower()
        if cmd in ("/quit", "/exit"):
            await self._add_system_message(chat, page, "Encerrando...")
            page.window.close()
            return
        if cmd == "/help":
            await self._add_system_message(
                chat, page,
                "Comandos: /status /skills /voice /gateway /clear /quit\n"
                "Skills: /plan /git-workflow /deploy-docker /debug-error /code-review"
            )
            return
        if cmd == "/clear":
            chat.controls.clear()
            page.update()
            return
        if cmd.startswith("/gateway"):
            from lux.gateway.setup import gateway_status
            await self._add_system_message(chat, page, gateway_status())
            return
        if cmd == "/voice":
            self._voice_active = not self._voice_active
            state = "ON" if self._voice_active else "OFF"
            await self._add_system_message(chat, page, f"Voz: {state}")
            return
        skill_name = cmd[1:]
        try:
            from lux.skills.manager import SkillManager
            mgr = SkillManager()
            content = mgr.get_skill_content_l1(skill_name)
            await self._add_system_message(chat, page, f"⚡ Skill: {skill_name}")
            await self._add_system_message(chat, page, content[:500])
        except FileNotFoundError:
            await self._add_system_message(chat, page, f"Skill '{skill_name}' nao encontrada.")

    async def _speak_async(self, text: str):
        try:
            audio = await self._tts.synthesize(text)
            if audio:
                import pyaudio
                p = pyaudio.PyAudio()
                stream = p.open(
                    format=pyaudio.paInt16, channels=1, rate=22050, output=True,
                )
                stream.write(audio)
                stream.stop_stream()
                stream.close()
                p.terminate()
        except Exception:
            pass
