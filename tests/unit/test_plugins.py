# tests/unit/test_plugins.py

from __future__ import annotations

import pytest
from pathlib import Path

from lux.agent.state import AgentState, ToolResult
from lux.plugins.base import LuxPlugin
from lux.plugins.manager import PluginManager


class AuditPlugin(LuxPlugin):
    name = "audit_logger"
    version = "1.0.0"
    description = "Loga tool calls em arquivo"

    def __init__(self):
        self.calls: list[dict] = []

    def post_tool_call(self, tool_name, args, result, state):
        self.calls.append({
            "tool": tool_name,
            "args": args,
            "success": result.success,
        })


class InterceptPlugin(LuxPlugin):
    name = "interceptor"
    version = "1.0.0"

    def pre_tool_call(self, tool_name, args, state):
        if tool_name == "blocked_tool":
            return ToolResult.failure("Bloqueado pelo plugin interceptor")
        return None


class MemoryHookPlugin(LuxPlugin):
    name = "memory_hook"
    version = "1.0.0"

    def __init__(self):
        self.writes: list[dict] = []

    def on_memory_write(self, action, target, content, user_id):
        self.writes.append({"action": action, "content": content})


def test_plugin_manager_discovery_empty(tmp_path):
    mgr = PluginManager(plugins_dir=tmp_path)
    count = mgr.discover_and_load()
    assert count == 0


def test_plugin_manager_discovery_with_plugin(tmp_path):
    plugin_dir = tmp_path / "audit_logger"
    plugin_dir.mkdir()

    plugin_code = """
class LuxPlugin:
    name = "audit_logger"
    version = "1.0.0"
    description = "Loga tool calls"
    
    def post_tool_call(self, tool_name, args, result, state):
        pass
"""
    (plugin_dir / "plugin.py").write_text(plugin_code)

    mgr = PluginManager(plugins_dir=tmp_path)
    count = mgr.discover_and_load()
    assert count == 1
    assert mgr.count == 1


def test_plugin_fire_pre_tool_intercept():
    mgr = PluginManager()
    mgr._plugins = [InterceptPlugin()]

    result = mgr.fire_pre_tool("blocked_tool", {}, AgentState())
    assert result is not None
    assert result.success is False
    assert "Bloqueado" in result.error_message


def test_plugin_fire_pre_tool_no_intercept():
    mgr = PluginManager()
    mgr._plugins = [InterceptPlugin()]

    result = mgr.fire_pre_tool("normal_tool", {}, AgentState())
    assert result is None


def test_plugin_fire_post_tool():
    mgr = PluginManager()
    plugin = AuditPlugin()
    mgr._plugins = [plugin]

    mgr.fire_post_tool("test", {}, ToolResult.ok("feito"), AgentState())
    assert len(plugin.calls) == 1
    assert plugin.calls[0]["tool"] == "test"
    assert plugin.calls[0]["success"] is True


def test_plugin_fire_memory_write():
    mgr = PluginManager()
    plugin = MemoryHookPlugin()
    mgr._plugins = [plugin]

    mgr.fire_memory_write("add", "memory", "fato importante", "u1")
    assert len(plugin.writes) == 1
    assert plugin.writes[0]["action"] == "add"


def test_plugin_fire_session_start():
    mgr = PluginManager()
    started = []

    class SessionPlugin(LuxPlugin):
        name = "session_test"
        def on_session_start(self, state):
            started.append(True)

    mgr._plugins = [SessionPlugin()]
    mgr.fire_session_start(AgentState())
    assert len(started) == 1


def test_plugin_fire_session_end():
    mgr = PluginManager()
    ended = []

    class SessionPlugin(LuxPlugin):
        name = "session_test"
        def on_session_end(self, state):
            ended.append(True)

    mgr._plugins = [SessionPlugin()]
    mgr.fire_session_end(AgentState())
    assert len(ended) == 1


def test_plugin_list():
    mgr = PluginManager()
    mgr._plugins = [AuditPlugin(), InterceptPlugin()]
    info = mgr.list_plugins()
    assert len(info) == 2
    names = {p["name"] for p in info}
    assert "audit_logger" in names
    assert "interceptor" in names


def test_plugin_base_defaults():
    plugin = LuxPlugin()
    state = AgentState()
    assert plugin.pre_tool_call("x", {}, state) is None
    plugin.post_tool_call("x", {}, ToolResult.ok("ok"), state)
    assert plugin.pre_llm_call([], state) is None
    plugin.post_llm_call({}, state)
    plugin.on_session_start(state)
    plugin.on_session_end(state)
    plugin.on_memory_write("add", "memory", "test", "u1")
