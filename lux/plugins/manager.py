# lux/plugins/manager.py
# Módulo: Plugins
# Dependências: plugins/base.py, agent/state.py
# Status: IMPLEMENTADO
# Notas: Discovery automático em ~/.lux/plugins/, dispatch de hooks.

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Optional

from lux.agent.state import AgentState, ToolResult
from lux.constants import PLUGINS_DIR

logger = logging.getLogger(__name__)

MANIFEST_FILE = "plugin.json"
ENTRY_FILE = "plugin.py"
CLASS_NAME = "LuxPlugin"


class PluginManager:
    """Gerencia ciclo de vida de plugins: discovery, load, hooks dispatch."""

    def __init__(self, plugins_dir: Optional[Path] = None):
        self._plugins_dir = plugins_dir or PLUGINS_DIR
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: list = []
        self._loaded = False

    def discover_and_load(self) -> int:
        """Escaneia ~/.lux/plugins/ e carrega todos os plugins encontrados."""
        if self._loaded:
            return len(self._plugins)

        self._plugins.clear()
        count = 0

        for plugin_dir in self._plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue

            plugin_file = plugin_dir / ENTRY_FILE
            if not plugin_file.exists():
                continue

            try:
                plugin = self._load_plugin(plugin_file)
                if plugin is not None:
                    self._plugins.append(plugin)
                    count += 1
                    logger.info(
                        "Plugin carregado: %s v%s — %s",
                        plugin.name, plugin.version, plugin.description,
                    )
            except Exception as e:
                logger.error("Falha ao carregar plugin %s: %s", plugin_dir.name, e)

        self._loaded = True
        logger.info("%d plugin(s) carregados", count)
        return count

    def _load_plugin(self, plugin_file: Path):
        spec = importlib.util.spec_from_file_location(
            plugin_file.parent.name, str(plugin_file)
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Nao foi possivel carregar spec de {plugin_file}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, CLASS_NAME):
            plugin_cls = getattr(module, CLASS_NAME)
            plugin = plugin_cls()
            return plugin

        raise ImportError(
            f"Classe '{CLASS_NAME}' nao encontrada em {plugin_file}"
        )

    # ── Hook Dispatch ────────────────────────────────────────────────────

    def fire_pre_tool(
        self, tool_name: str, args: dict, state: AgentState
    ) -> Optional[ToolResult]:
        for plugin in self._plugins:
            try:
                result = plugin.pre_tool_call(tool_name, args, state)
                if result is not None:
                    logger.debug(
                        "Tool '%s' interceptada pelo plugin '%s'",
                        tool_name, plugin.name,
                    )
                    return result
            except Exception:
                logger.exception(
                    "Erro no pre_tool_call do plugin %s", plugin.name
                )
        return None

    def fire_post_tool(
        self, tool_name: str, args: dict, result: ToolResult, state: AgentState
    ) -> None:
        for plugin in self._plugins:
            try:
                plugin.post_tool_call(tool_name, args, result, state)
            except Exception:
                logger.exception(
                    "Erro no post_tool_call do plugin %s", plugin.name
                )

    def fire_pre_llm(
        self, messages: list[dict], state: AgentState
    ) -> Optional[list[dict]]:
        for plugin in self._plugins:
            try:
                modified = plugin.pre_llm_call(messages, state)
                if modified is not None:
                    return modified
            except Exception:
                logger.exception("Erro no pre_llm_call do plugin %s", plugin.name)
        return None

    def fire_post_llm(
        self, response: dict, state: AgentState
    ) -> None:
        for plugin in self._plugins:
            try:
                plugin.post_llm_call(response, state)
            except Exception:
                logger.exception("Erro no post_llm_call do plugin %s", plugin.name)

    def fire_session_start(self, state: AgentState) -> None:
        for plugin in self._plugins:
            try:
                plugin.on_session_start(state)
            except Exception:
                logger.exception("Erro no on_session_start do plugin %s", plugin.name)

    def fire_session_end(self, state: AgentState) -> None:
        for plugin in self._plugins:
            try:
                plugin.on_session_end(state)
            except Exception:
                logger.exception("Erro no on_session_end do plugin %s", plugin.name)

    def fire_memory_write(
        self, action: str, target: str, content: str, user_id: str
    ) -> None:
        for plugin in self._plugins:
            try:
                plugin.on_memory_write(action, target, content, user_id)
            except Exception:
                logger.exception("Erro no on_memory_write do plugin %s", plugin.name)

    # ── Info ─────────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._plugins)

    def list_plugins(self) -> list[dict]:
        return [
            {"name": p.name, "version": p.version, "description": p.description}
            for p in self._plugins
        ]

    def get_plugin_dir(self, plugin_name: str) -> Path:
        return self._plugins_dir / plugin_name
