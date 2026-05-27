# lux/tools/implementations/desktop.py
# Módulo: Desktop Tools
# Dependências: tools/desktop_utils.py, agent/state.py
# Status: IMPLEMENTADO
# Notas: 12 ferramentas de controle de desktop. X11: xdotool/scrot, Wayland: grim/ydotool.

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from lux.agent.state import AgentState, ToolResult
from lux.constants import LUX_HOME
from lux.tools.base import Tool
from lux.tools.desktop_utils import (
    DisplayServerDetector,
    _parse_window_list,
    _run_cmd,
)

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = LUX_HOME / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

MISSING_DEPS_MSG = (
    "Ferramentas de desktop nao instaladas. Execute:\n"
    "  sudo apt-get install xdotool scrot tesseract-ocr wmctrl xclip\n"
    "  ou: scripts/setup_desktop_tools.sh"
)


class ScreenshotTool(Tool):
    name = "screenshot"
    description = "Captura screenshot da tela inteira ou regiao. OCR automatico opcional."
    parameters_schema = {
        "type": "object",
        "properties": {
            "region": {"type": "array", "items": {"type": "integer"}, "description": "[x, y, w, h] — None = tela inteira"},
            "run_ocr": {"type": "boolean", "description": "Executa OCR automatico", "default": True},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        region = tuple(args["region"]) if args.get("region") else None
        run_ocr = args.get("run_ocr", True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"screenshot_{ts}.png"

        cmd = DisplayServerDetector.get_screenshot_cmd(str(path), region)
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)

        code, out, err = await _run_cmd(cmd, timeout=10)
        if code != 0:
            return ToolResult.failure(err or "Falha ao capturar screenshot")

        result = f"Screenshot salvo: {path}"
        if run_ocr and path.exists():
            ocr_text = await self._ocr_file(path)
            if ocr_text:
                result += f"\n\nOCR ({len(ocr_text)} chars):\n{ocr_text[:2000]}"

        return ToolResult.ok(result)

    async def _ocr_file(self, path: Path) -> Optional[str]:
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(path).convert("L")
            text = pytesseract.image_to_string(img, lang="por+eng")
            return text.strip() if text.strip() else None
        except ImportError:
            return None
        except Exception as e:
            logger.debug("OCR falhou: %s", e)
            return None


class ScreenReadTool(Tool):
    name = "screen_read"
    description = "Le texto visivel na tela via OCR (tesseract). Captura + pre-processa + reconhece."
    parameters_schema = {
        "type": "object",
        "properties": {
            "region": {"type": "array", "items": {"type": "integer"}, "description": "[x, y, w, h]"},
            "language": {"type": "string", "description": "Idioma tesseract", "default": "por+eng"},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        region = tuple(args["region"]) if args.get("region") else None
        lang = args.get("language", "por+eng")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        try:
            cmd = DisplayServerDetector.get_screenshot_cmd(tmp_path, region)
            if not cmd:
                return ToolResult.failure(MISSING_DEPS_MSG)

            code, out, err = await _run_cmd(cmd, timeout=10)
            if code != 0:
                return ToolResult.failure(err or "Falha ao capturar")

            try:
                import pytesseract
                from PIL import Image

                img = Image.open(tmp_path).convert("L")
                text = pytesseract.image_to_string(img, lang=lang)
                if text.strip():
                    return ToolResult.ok(text.strip())
                return ToolResult.ok("Nenhum texto detectado na regiao.")
            except ImportError:
                return ToolResult.failure(
                    "pytesseract nao instalado. Execute: pip install pytesseract"
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class MouseClickTool(Tool):
    name = "mouse_click"
    description = "Clica em coordenadas ou posicao de texto encontrado na tela. Requer aprovacao."
    timeout_seconds = 30
    parameters_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "Coordenada X"},
            "y": {"type": "integer", "description": "Coordenada Y"},
            "text_target": {"type": "string", "description": "Texto a encontrar na tela para clicar"},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
            "double": {"type": "boolean", "description": "Duplo clique", "default": False},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        x = args.get("x")
        y = args.get("y")
        text = args.get("text_target")
        button = args.get("button", "left")
        double = args.get("double", False)

        if text and (x is None or y is None):
            return ToolResult.failure("text_target: combine com find_on_screen primeiro para obter coordenadas")

        if x is None or y is None:
            return ToolResult.failure("x e y obrigatorios")

        cmd = DisplayServerDetector.get_mouse_cmd(x, y, button, double)
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)

        code, out, err = await _run_cmd(cmd, timeout=5)
        if code != 0:
            return ToolResult.failure(err or "Falha ao clicar")

        action = "duplo clique" if double else "clique"
        return ToolResult.ok(f"{action} {button} em ({x}, {y})")


class MouseMoveTool(Tool):
    name = "mouse_move"
    description = "Move mouse para coordenadas"
    parameters_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
        "required": ["x", "y"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        x, y = args["x"], args["y"]
        if not shutil.which("xdotool"):
            return ToolResult.failure(MISSING_DEPS_MSG)
        code, out, err = await _run_cmd(["xdotool", "mousemove", str(x), str(y)], timeout=5)
        return ToolResult.ok(f"Mouse movido para ({x}, {y})")


class KeyboardTypeTool(Tool):
    name = "keyboard_type"
    description = "Digita texto na janela ativa com delay entre teclas"
    timeout_seconds = 60
    parameters_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Texto a digitar (max 10000 chars)"},
            "delay_ms": {"type": "integer", "description": "Delay entre teclas em ms", "default": 50},
            "clear_first": {"type": "boolean", "description": "Ctrl+A antes de digitar", "default": False},
        },
        "required": ["text"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        text = args["text"][:10000]
        delay = args.get("delay_ms", 50)
        clear = args.get("clear_first", False)

        cmd = DisplayServerDetector.get_keyboard_cmd(text, delay, clear)
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)

        code, out, err = await _run_cmd(cmd, timeout=max(10, len(text) * delay // 500))
        if code != 0:
            return ToolResult.failure(err or "Falha ao digitar")
        return ToolResult.ok(f"Texto digitado ({len(text)} chars)")


class KeyboardPressTool(Tool):
    name = "keyboard_press"
    description = "Pressiona tecla ou atalho (ex: ctrl+c, alt+tab, super)"
    parameters_schema = {
        "type": "object",
        "properties": {
            "keys": {"type": "string", "description": "Tecla/atalho: ctrl+c, alt+tab, super, Return, Escape"},
        },
        "required": ["keys"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        keys = args["keys"]
        cmd = DisplayServerDetector.get_keypress_cmd(keys)
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)
        code, out, err = await _run_cmd(cmd, timeout=5)
        return ToolResult.ok(f"Tecla pressionada: {keys}")


class WindowListTool(Tool):
    name = "window_list"
    description = "Lista todas as janelas abertas com titulo e geometria"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute())

    async def _async_execute(self) -> ToolResult:
        cmd = DisplayServerDetector.get_window_list_cmd()
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)

        code, out, err = await _run_cmd(cmd, timeout=5)
        if code != 0:
            return ToolResult.failure(err or "Falha ao listar janelas")

        windows = _parse_window_list(out)
        if not windows:
            return ToolResult.ok("Nenhuma janela encontrada.")

        lines = [f"Janelas ({len(windows)}):"]
        for w in windows:
            lines.append(f"  [{w.id}] {w.title[:80]}")
            if w.geometry:
                lines.append(f"       geometria: {w.geometry}")
        return ToolResult.ok("\n".join(lines))


class WindowFocusTool(Tool):
    name = "window_focus"
    description = "Foca janela por titulo parcial ou ID"
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Parte do titulo da janela"},
            "id": {"type": "string", "description": "ID da janela (do window_list)"},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        title = args.get("title", "")
        wm_id = args.get("id", "")
        cmd = DisplayServerDetector.get_window_focus_cmd(title, wm_id)
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)
        code, out, err = await _run_cmd(cmd, timeout=5)
        if code != 0:
            return ToolResult.failure(err or "Falha ao focar janela")
        return ToolResult.ok(f"Janela focada: {title or wm_id}")


class ClipboardReadTool(Tool):
    name = "clipboard_read"
    description = "Le conteudo do clipboard"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute())

    async def _async_execute(self) -> ToolResult:
        cmd = DisplayServerDetector.get_clipboard_read_cmd()
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)
        code, out, err = await _run_cmd(cmd, timeout=5)
        if code != 0:
            return ToolResult.failure(err or "Clipboard vazio ou inacessivel")
        return ToolResult.ok(out.strip()[:5000] if out.strip() else "Clipboard vazio")


class ClipboardWriteTool(Tool):
    name = "clipboard_write"
    description = "Escreve texto no clipboard"
    parameters_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Texto para o clipboard"},
        },
        "required": ["text"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        text = args["text"]
        cmd = DisplayServerDetector.get_clipboard_write_cmd()
        if not cmd:
            return ToolResult.failure(MISSING_DEPS_MSG)
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate(input=text.encode())
        if proc.returncode != 0:
            return ToolResult.failure(err.decode() if err else "Falha ao escrever no clipboard")
        return ToolResult.ok(f"{len(text)} chars copiados para o clipboard")


class FindOnScreenTool(Tool):
    name = "find_on_screen"
    description = "Busca texto na tela via OCR e retorna coordenadas"
    parameters_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Texto a buscar na tela"},
            "confidence": {"type": "number", "description": "Confianca minima 0-1", "default": 0.6},
        },
        "required": ["text"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self._async_execute(args))

    async def _async_execute(self, args: dict) -> ToolResult:
        search_text = args["text"]
        confidence = args.get("confidence", 0.6)

        try:
            import pytesseract
            from PIL import Image

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                tmp_path = f.name

            cmd = DisplayServerDetector.get_screenshot_cmd(tmp_path, None)
            if not cmd:
                return ToolResult.failure(MISSING_DEPS_MSG)

            code, out, err = await _run_cmd(cmd, timeout=10)
            if code != 0:
                return ToolResult.failure(err or "Falha ao capturar")

            img = Image.open(tmp_path)
            data = pytesseract.image_to_data(img, lang="por+eng", output_type=pytesseract.Output.DICT)

            for i, text in enumerate(data["text"]):
                if search_text.lower() in text.lower() and int(data["conf"][i]) >= confidence * 100:
                    x = data["left"][i] + data["width"][i] // 2
                    y = data["top"][i] + data["height"][i] // 2
                    Path(tmp_path).unlink(missing_ok=True)
                    return ToolResult.ok(
                        f"'{text}' encontrado em ({x}, {y}) — confianca: {data['conf'][i]}%"
                    )

            Path(tmp_path).unlink(missing_ok=True)
            return ToolResult.ok(f"'{search_text}' nao encontrado na tela")

        except ImportError:
            return ToolResult.failure("pytesseract nao instalado")
        except Exception as e:
            return ToolResult.failure(f"Erro na busca: {e}")


import shutil
