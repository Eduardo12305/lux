# lux/interfaces/voice_ui.py
# Módulo: Interfaces
# Dependências: rich (opcional)
# Status: IMPLEMENTADO
# Notas: Interface retrowave/HUD para modo voz com VU meter, waveform, animações.
#   Fallback para modo texto puro se rich não disponível.

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from enum import Enum, auto
from pathlib import Path

from lux.voice.pipeline import VoicePipelineState

logger = logging.getLogger(__name__)

_RICH = False
try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import Progress, BarColumn, TextColumn
    from rich.table import Table
    from rich.style import Style
    _RICH = True
except ImportError:
    pass


class VoiceUI:
    """
    Interface retrowave para modo voz.
    
    ┌──────────────────────────────────────────────────┐
    │  ████▓▓▓▓▒▒▒▒░░░░  ● LUX VOICE  ●  ░░░░▒▒▒▒▓▓▓▓████  │
    │──────────────────────────────────────────────────│
    │  🎤  OUVINDO...                                   │
    │  VU [████████░░░░░░░░] -12dB                      │
    │  ═══════════════════════════════════════          │
    │  "Lux, qual o status do build?"                  │
    │──────────────────────────────────────────────────│
    │  🤖  PROCESSANDO...                               │
    │  ░░▒▒▓▓████████████████▓▓▒▒░░                    │
    │──────────────────────────────────────────────────│
    │  🔊  FALANDO                                     │
    │  "Build concluído, todos os testes passando."    │
    │  ═══╗ ▓▓░░                                       │
    └──────────────────────────────────────────────────┘
    
    [Enter] push-to-talk  [Esc] sair  [Space] pausar
    """

    def __init__(self):
        if _RICH:
            self._console = Console()
        self._state = VoicePipelineState.IDLE
        self._transcript_buffer: list[str] = []
        self._tts_buffer: list[str] = []
        self._vu_level = 0.0
        self._elapsed = 0.0
        self._start_time = time.monotonic()

    def _waveform(self, width: int = 40, level: float = 0.3) -> str:
        chars = "▁▂▃▄▅▆▇█"
        segments = []
        for i in range(width):
            s = (i * 0.15 + level * 2.0 + self._elapsed * 3.0)
            idx = int((abs(pow(s % 1.0, 2) - 0.01) * 0.5 + level * 0.5) * 7)
            segments.append(chars[min(idx, 7)])
        return "".join(segments)

    def _vu_meter(self, level: float, width: int = 20) -> tuple[str, str]:
        filled = int(level * width)
        bar = "█" * filled + "░" * (width - filled)
        db = -48 + int(level * 48) if level > 0 else -48
        color = "green" if db < -12 else ("yellow" if db < -6 else "red")
        return bar, f"{db}dB"

    def status_indicator(self, state: VoicePipelineState) -> str:
        icons = {
            VoicePipelineState.IDLE: "⏸",
            VoicePipelineState.LISTENING: "🎤",
            VoicePipelineState.PROCESSING: "🤖",
            VoicePipelineState.SPEAKING: "🔊",
            VoicePipelineState.STOPPED: "⏹",
        }
        labels = {
            VoicePipelineState.IDLE: "PRONTO",
            VoicePipelineState.LISTENING: "OUVINDO",
            VoicePipelineState.PROCESSING: "PROCESSANDO",
            VoicePipelineState.SPEAKING: "FALANDO",
            VoicePipelineState.STOPPED: "PARADO",
        }
        return f"{icons.get(state, '?')}  {labels.get(state, '?')}"

    def render(self, transcript: str = "", tts_text: str = "",
               vu_level: float = 0.0) -> str:
        self._vu_level = vu_level
        self._elapsed = time.monotonic() - self._start_time

        wave = self._waveform()
        vu_bar, vu_db = self._vu_meter(vu_level)
        indicator = self.status_indicator(self._state)

        if _RICH:
            return ""  # renderizado via Live

        terminal_width = os.get_terminal_size().columns
        w = min(terminal_width - 4, 64)

        top = "█" * ((w - 8) // 4) + "  ● LUX VOICE ●  " + "█" * ((w - 8) // 4)
        top = top[:w]

        lines = [
            "┌" + "─" * (w - 2) + "┐",
            "│ " + top.ljust(w - 4) + " │",
            "│" + "─" * (w - 2) + "│",
            f"│ {indicator:<{w-4}} │",
        ]

        if self._state == VoicePipelineState.LISTENING:
            lines.append(f"│ VU [{vu_bar}] {vu_db:<8}│")
            lines.append(f"│ {wave[:w-4]:<{w-4}} │")
        if transcript:
            display = f'"{transcript}"'[:w-4]
            lines.append(f"│ {display:<{w-4}} │")

        lines.append(f"│{'─' * (w-2)}│")
        if tts_text:
            display = f'"{tts_text}"'[:w-4]
            lines.append(f"│ {display:<{w-4}} │")

        remaining = self._waveform(width=w//2)[:w-4]
        lines.append(f"│ {remaining:<{w-4}} │")

        lines.append("└" + "─" * (w - 2) + "┘")
        lines.append("[Enter] push-to-talk  [Esc] sair  [Espaco] pausar")
        return "\n".join(lines)

    async def rich_render_loop(self, pipeline, stop_event: asyncio.Event):
        """Render loop com Live do rich."""
        if not _RICH:
            return

        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        header = Panel(
            Text("● LUX VOICE ●", style="bold cyan"),
            style="bright_black",
            subtitle="[dim]push-to-talk[/dim]",
        )

        def _make_layout():
            state = pipeline.state
            indicator = self.status_indicator(state)
            wave = self._waveform(width=60)
            vu_bar, vu_db = self._vu_meter(self._vu_level)

            body_content = Table.grid()
            body_content.add_row(Text(indicator, style="bold yellow"))
            body_content.add_row(Text(f"VU [{vu_bar}] {vu_db}", style="dim"))
            body_content.add_row(Text(wave[:60], style="cyan"))
            body_content.add_row(Text("─" * 60, style="dim"))

            if self._transcript_buffer:
                last = "".join(self._transcript_buffer[-3:])[:60]
                body_content.add_row(Text(f'"{last}"', style="green"))

            if self._tts_buffer:
                last = "".join(self._tts_buffer[-1:])[:60]
                body_content.add_row(Text(f'"{last}"', style="magenta"))

            layout["header"].update(header)
            layout["body"].update(Panel(body_content, border_style="bright_black"))
            layout["footer"].update(Panel(
                "[Enter] push-to-talk  [Esc] sair  [Espaco] pausar",
                style="dim",
            ))
            return layout

        with Live(_make_layout(), refresh_per_second=10, screen=True) as live:
            while not stop_event.is_set():
                self._elapsed = time.monotonic() - self._start_time
                live.update(_make_layout())
                await asyncio.sleep(0.1)

    def on_transcript(self, text: str):
        self._transcript_buffer.append(text)

    def on_tts(self, text: str):
        self._tts_buffer.append(text)

    def set_state(self, state: VoicePipelineState):
        self._state = state

    def clear(self):
        if _RICH:
            self._console.clear()
        else:
            os.system("clear" if os.name != "nt" else "cls")
