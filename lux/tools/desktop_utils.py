# lux/tools/desktop_utils.py
# Módulo: Desktop Tools
# Dependências: subprocess, os, shutil
# Status: IMPLEMENTADO
# Notas: DisplayServerDetector, helpers para ferramentas de desktop.
#   Graceful degradation quando ferramentas de sistema ausentes.

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DisplayServer(Enum):
    X11 = auto()
    WAYLAND = auto()


@dataclass
class WindowInfo:
    id: str = ""
    title: str = ""
    pid: int = 0
    geometry: str = ""
    workspace: int = 0


class DisplayServerDetector:
    """Detecta X11 vs Wayland e seleciona as ferramentas corretas."""

    @staticmethod
    def detect() -> Optional[DisplayServer]:
        if os.environ.get("WAYLAND_DISPLAY"):
            return DisplayServer.WAYLAND
        if os.environ.get("DISPLAY"):
            return DisplayServer.X11
        return None

    @staticmethod
    def get_screenshot_cmd(
        output: str, region: Optional[tuple] = None
    ) -> Optional[list[str]]:
        server = DisplayServerDetector.detect()
        if server is None:
            return None

        if server == DisplayServer.WAYLAND:
            if shutil.which("grim"):
                cmd = ["grim"]
                if region:
                    x, y, w, h = region
                    cmd += ["-g", f"{x},{y} {w}x{h}"]
                return cmd + [output]
        elif server == DisplayServer.X11:
            if shutil.which("scrot"):
                cmd = ["scrot", output]
                if region:
                    x, y, w, h = region
                    cmd += ["-a", f"{x},{y},{w},{h}"]
                return cmd
            elif shutil.which("import"):
                cmd = ["import", "-window", "root"]
                if region:
                    x, y, w, h = region
                    cmd += ["-crop", f"{w}x{h}+{x}+{y}"]
                return cmd + [output]
        return None

    @staticmethod
    def get_mouse_cmd(x: int, y: int, button: str = "left", double: bool = False) -> Optional[list[str]]:
        if shutil.which("xdotool"):
            cmd = ["xdotool", "mousemove", str(x), str(y)]
            if double:
                cmd += ["click", "--repeat", "2", str(_button_map(button))]
            else:
                cmd += ["click", str(_button_map(button))]
            return cmd
        return None

    @staticmethod
    def get_keyboard_cmd(text: str, delay_ms: int = 50, clear_first: bool = False) -> Optional[list[str]]:
        if not shutil.which("xdotool"):
            return None
        cmd = ["xdotool"]
        if clear_first:
            cmd += ["key", "ctrl+a", "sleep", "0.05"]
        cmd += ["type", "--delay", str(delay_ms), "--", text]
        return cmd

    @staticmethod
    def get_keypress_cmd(keys: str) -> Optional[list[str]]:
        if not shutil.which("xdotool"):
            return None
        return ["xdotool", "key", "--", keys]

    @staticmethod
    def get_window_list_cmd() -> Optional[list[str]]:
        if shutil.which("wmctrl"):
            return ["wmctrl", "-l", "-G", "-p", "-x"]
        if shutil.which("xdotool"):
            return [
                "xdotool", "search", "--onlyvisible", "--name", "",
                "getwindowpid", "%@", "getwindowname", "%@",
                "getwindowgeometry", "%@",
            ]
        return None

    @staticmethod
    def get_window_focus_cmd(title: str = "", wm_id: str = "") -> Optional[list[str]]:
        if shutil.which("wmctrl"):
            if wm_id:
                return ["wmctrl", "-i", "-a", wm_id]
            if title:
                return ["wmctrl", "-a", title]
        if shutil.which("xdotool"):
            if wm_id:
                return ["xdotool", "windowactivate", wm_id]
            if title:
                return ["xdotool", "search", "--name", title, "windowactivate"]
        return None

    @staticmethod
    def get_clipboard_read_cmd() -> Optional[list[str]]:
        if shutil.which("xclip"):
            return ["xclip", "-o", "-selection", "clipboard"]
        if shutil.which("wl-paste"):
            return ["wl-paste"]
        return None

    @staticmethod
    def get_clipboard_write_cmd() -> Optional[list[str]]:
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard"]
        if shutil.which("wl-copy"):
            return ["wl-copy"]
        return None


def _button_map(button: str) -> int:
    return {"left": 1, "middle": 2, "right": 3}.get(button, 1)


async def _run_cmd(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")
    except FileNotFoundError:
        return -1, "", f"Comando nao encontrado: {cmd[0]}"
    except asyncio.TimeoutError:
        return -1, "", f"Timeout ({timeout}s): {' '.join(cmd)}"
    except Exception as e:
        return -1, "", str(e)


def _parse_window_list(output: str) -> list[WindowInfo]:
    windows = []
    for line in output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(None, 7)
        if len(parts) >= 8:
            windows.append(WindowInfo(
                id=parts[0],
                pid=int(parts[2]) if parts[2].isdigit() else 0,
                geometry=f"{parts[3]}x{parts[4]}+{parts[5]}+{parts[6]}",
                title=parts[7],
            ))
        elif len(parts) >= 4:
            windows.append(WindowInfo(
                id=parts[0],
                title=" ".join(parts[1:]),
            ))
    return windows
