# tests/unit/test_desktop_tools.py
# Módulo: Testes de Desktop Tools
# Status: IMPLEMENTADO

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lux.tools.desktop_utils import (
    DisplayServer,
    DisplayServerDetector,
    _button_map,
    _parse_window_list,
)


def test_display_server_detect_x11(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert DisplayServerDetector.detect() == DisplayServer.X11


def test_display_server_detect_wayland(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert DisplayServerDetector.detect() == DisplayServer.WAYLAND


def test_display_server_detect_none(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert DisplayServerDetector.detect() is None


def test_button_map():
    assert _button_map("left") == 1
    assert _button_map("middle") == 2
    assert _button_map("right") == 3
    assert _button_map("invalid") == 1


def test_parse_window_list_wmctrl():
    output = (
        "0x02a00001  0 1234  0    0    1920 1080  meupc Terminal — bash\n"
        "0x03c00002  0 5678  100  200  800  600   meupc Google Chrome\n"
    )
    windows = _parse_window_list(output)
    assert len(windows) == 2
    assert windows[0].id == "0x02a00001"
    assert "Terminal" in windows[0].title
    assert "Chrome" in windows[1].title


def test_parse_window_list_empty():
    windows = _parse_window_list("")
    assert len(windows) == 0


def test_parse_window_list_partial():
    output = "0x02a00001 algum texto sem geometria completa"
    windows = _parse_window_list(output)
    assert len(windows) >= 1


# ── Tool Instantiation ──────────────────────────────────────────────────


def test_screenshot_tool_instantiation():
    from lux.tools.implementations.desktop import ScreenshotTool
    tool = ScreenshotTool()
    assert tool.name == "screenshot"
    assert "screenshot" in tool.description.lower()


def test_screen_read_tool():
    from lux.tools.implementations.desktop import ScreenReadTool
    tool = ScreenReadTool()
    assert tool.name == "screen_read"
    assert "ocr" in tool.description.lower()


def test_mouse_click_tool():
    from lux.tools.implementations.desktop import MouseClickTool
    tool = MouseClickTool()
    assert tool.name == "mouse_click"


def test_keyboard_type_tool():
    from lux.tools.implementations.desktop import KeyboardTypeTool
    tool = KeyboardTypeTool()
    assert tool.name == "keyboard_type"


def test_window_list_tool():
    from lux.tools.implementations.desktop import WindowListTool
    tool = WindowListTool()
    assert tool.name == "window_list"


def test_clipboard_read_tool():
    from lux.tools.implementations.desktop import ClipboardReadTool
    tool = ClipboardReadTool()
    assert tool.name == "clipboard_read"


def test_find_on_screen_tool():
    from lux.tools.implementations.desktop import FindOnScreenTool
    tool = FindOnScreenTool()
    assert tool.name == "find_on_screen"


# ── Toolset Registration ────────────────────────────────────────────────


def test_desktop_toolset_exists():
    from lux.tools.toolsets import TOOLSETS
    assert "desktop" in TOOLSETS
    ts = TOOLSETS["desktop"]
    assert ts.requires_approval is True
    assert ts.min_role.value == "admin"
    tools = ts.tools
    assert "screenshot" in tools
    assert "mouse_click" in tools
    assert "keyboard_type" in tools
    assert "keyboard_press" in tools


def test_desktop_permission_admin_only():
    from lux.tools.registry import _has_permission
    from lux.agent.state import UserRole
    assert _has_permission("screenshot", UserRole.ADMIN) is True
    assert _has_permission("screenshot", UserRole.USER) is False
    assert _has_permission("mouse_click", UserRole.GUEST) is False


# ── Commands (fallback when system tools missing) ────────────────────────


def test_get_screenshot_cmd_missing_tools(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda x: None)
    cmd = DisplayServerDetector.get_screenshot_cmd("/tmp/test.png")
    assert cmd is None


def test_get_mouse_cmd_missing_tools(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda x: None)
    cmd = DisplayServerDetector.get_mouse_cmd(100, 200)
    assert cmd is None


def test_get_window_list_cmd_missing_tools(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda x: None)
    cmd = DisplayServerDetector.get_window_list_cmd()
    assert cmd is None


def test_get_clipboard_cmd_missing_tools(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda x: None)
    assert DisplayServerDetector.get_clipboard_read_cmd() is None
    assert DisplayServerDetector.get_clipboard_write_cmd() is None
