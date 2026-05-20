# lux/prompt/context_files.py
# Módulo: Prompt
# Dependências: constants.py
# Status: IMPLEMENTADO

from __future__ import annotations

from pathlib import Path

from lux.constants import GLOBAL_CONTEXT_PATH


class ContextFileLoader:
    """
    Carrega arquivos de contexto de projeto (.lux.md, AGENTS.md).
    Hierarquia: diretorio atual → pai → home.
    """

    CONTEXT_FILENAMES = [".lux.md", "AGENTS.md", ".hermes.md"]

    def load_for_workspace(self, workspace: str) -> dict[str, str]:
        path = Path(workspace).resolve()
        loaded: dict[str, str] = {}

        while path != path.parent:
            for filename in self.CONTEXT_FILENAMES:
                f = path / filename
                if f.exists() and f.is_file():
                    content = f.read_text()[:8192]
                    loaded[str(f)] = content
                    break
            path = path.parent
            if str(path) == str(Path.home()):
                break

        if GLOBAL_CONTEXT_PATH.exists():
            loaded[str(GLOBAL_CONTEXT_PATH)] = GLOBAL_CONTEXT_PATH.read_text()[:8192]

        return loaded
