# lux/memory/manager.py
# Módulo: Memory
# Dependências: agent/state.py, memory/session_db.py, memory/semantic.py, models/embedder.py
# Status: IMPLEMENTADO
# Notas: MemoryManager com frozen snapshot, FTS5, e merge RRF (GAP 5).

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from lux.agent.state import (
    MemoryAction,
    MemoryChunk,
    MemoryDelta,
    MemoryResult,
    MemoryTarget,
    MergedResult,
    SessionSearchResult,
    UserProfile,
)
from lux.constants import (
    MEMORIES_DIR,
    MEMORY_ENTRY_SEPARATOR,
    MEMORY_MD_LIMIT_CHARS,
    USER_MD_LIMIT_CHARS,
)
from lux.memory.semantic import SemanticSearch, merge_search_results_rrf
from lux.memory.session_db import SessionDB

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Ponto central de acesso a todas as camadas de memoria.
    Implementa frozen snapshot, FTS5, Qdrant semantico, e escritas.
    """

    MEMORY_MD_LIMIT = MEMORY_MD_LIMIT_CHARS
    USER_MD_LIMIT = USER_MD_LIMIT_CHARS
    ENTRY_SEPARATOR = MEMORY_ENTRY_SEPARATOR

    def __init__(
        self,
        memories_dir: Optional[Path] = None,
        session_db: Optional[SessionDB] = None,
        semantic: Optional[SemanticSearch] = None,
    ):
        self.memories_dir = memories_dir or MEMORIES_DIR
        self.memories_dir.mkdir(parents=True, exist_ok=True)
        self._session_db = session_db or SessionDB()
        self._semantic = semantic or SemanticSearch()
        self._write_locks: dict[tuple[str, str], asyncio.Lock] = {}

    @property
    def session_db(self) -> SessionDB:
        return self._session_db

    @property
    def semantic(self) -> SemanticSearch:
        return self._semantic

    # ── Frozen Snapshot ─────────────────────────────────────────────────

    async def load_frozen_snapshot(self, user_id: str) -> tuple[str, str]:
        memory_path = self._memory_path(user_id, "MEMORY.md")
        user_path = self._memory_path(user_id, "USER.md")

        memory_content = memory_path.read_text() if memory_path.exists() else ""
        user_content = user_path.read_text() if user_path.exists() else ""

        return (
            self._format_memory_block("MEMORY (suas notas pessoais)", memory_content,
                                       len(memory_content), self.MEMORY_MD_LIMIT),
            self._format_memory_block("USER PROFILE", user_content,
                                       len(user_content), self.USER_MD_LIMIT),
        )

    def _format_memory_block(
        self, title: str, content: str, used: int, limit: int
    ) -> str:
        pct = int(used / limit * 100) if limit > 0 else 0
        sep = "\u2550" * 46
        header = f"{sep}\n{title} [{pct}% \u2014 {used}/{limit} chars]\n{sep}"
        return f"{header}\n{content}" if content else f"{header}\n(empty)"

    # ── Memory Actions ──────────────────────────────────────────────────

    async def apply_memory_action(
        self,
        action: MemoryAction,
        target: MemoryTarget,
        content: Optional[str] = None,
        old_text: Optional[str] = None,
        user_id: str = "",
    ) -> MemoryResult:
        lock_key = (user_id, target.value)
        if lock_key not in self._write_locks:
            self._write_locks[lock_key] = asyncio.Lock()

        async with self._write_locks[lock_key]:
            return await self._apply_action_locked(
                action, target, content, old_text, user_id
            )

    async def _apply_action_locked(
        self,
        action: MemoryAction,
        target: MemoryTarget,
        content: Optional[str],
        old_text: Optional[str],
        user_id: str,
    ) -> MemoryResult:
        filename = "MEMORY.md" if target == MemoryTarget.MEMORY else "USER.md"
        path = self._memory_path(user_id, filename)
        limit = self.MEMORY_MD_LIMIT if target == MemoryTarget.MEMORY else self.USER_MD_LIMIT
        current = path.read_text() if path.exists() else ""

        match action:
            case MemoryAction.ADD:
                return self._do_add(path, current, content or "", limit)
            case MemoryAction.REPLACE:
                return self._do_replace(path, current, content or "", old_text or "", limit)
            case MemoryAction.REMOVE:
                return self._do_remove(path, current, old_text or "", limit)
            case _:
                return MemoryResult.failure(f"Acao desconhecida: {action}")

    def _do_add(self, path: Path, current: str, new_entry: str, limit: int) -> MemoryResult:
        if not new_entry.strip():
            return MemoryResult.failure("Conteudo vazio — nada a adicionar.")

        if current:
            new_content = f"{current}\n{self.ENTRY_SEPARATOR}\n{new_entry.strip()}"
        else:
            new_content = new_entry.strip()

        if len(new_content) > limit:
            return MemoryResult.failure(
                f"Memoria cheia ({len(current)}/{limit} chars). "
                f"Consolide ou remova entradas antigas antes de adicionar.",
                chars_used=len(current),
                chars_limit=limit,
            )

        path.write_text(new_content)
        return MemoryResult.ok(
            f"Entrada adicionada ({len(new_entry)} chars).",
            chars_used=len(new_content),
            chars_limit=limit,
        )

    def _do_replace(
        self, path: Path, current: str, new_content: str, old_text: str, limit: int
    ) -> MemoryResult:
        if old_text not in current:
            return MemoryResult.failure(f"Substring '{old_text[:80]}...' nao encontrada.")

        entries = current.split(self.ENTRY_SEPARATOR)
        matches = [e for e in entries if old_text in e]

        if len(matches) > 1:
            return MemoryResult.failure(
                f"Substring ambigua: encontrada em {len(matches)} entradas. "
                f"Use um trecho mais especifico para identificar qual entrada substituir."
            )

        updated = current.replace(matches[0], new_content.strip(), 1)
        if len(updated) > limit:
            return MemoryResult.failure(
                f"Conteudo novo excede limite de {limit} chars.",
                chars_used=len(updated),
                chars_limit=limit,
            )

        path.write_text(updated)
        return MemoryResult.ok(
            "Entrada substituida.",
            chars_used=len(updated),
            chars_limit=limit,
        )

    def _do_remove(
        self, path: Path, current: str, old_text: str, limit: int
    ) -> MemoryResult:
        if old_text not in current:
            return MemoryResult.failure(f"Substring '{old_text[:80]}...' nao encontrada.")

        entries = current.split(self.ENTRY_SEPARATOR)
        matches = [e for e in entries if old_text in e]

        if len(matches) > 1:
            return MemoryResult.failure(
                f"Substring ambigua: encontrada em {len(matches)} entradas."
            )

        updated = current.replace(matches[0], "", 1)
        updated = self.ENTRY_SEPARATOR.join(
            e.strip() for e in updated.split(self.ENTRY_SEPARATOR) if e.strip()
        )

        path.write_text(updated)
        return MemoryResult.ok(
            "Entrada removida.",
            chars_used=len(updated),
            chars_limit=limit,
        )

    # ── Search ───────────────────────────────────────────────────────────

    async def session_search(
        self, query: str, user_id: str, limit: int = 5
    ) -> list[SessionSearchResult]:
        return await self._session_db.fts_search(query, user_id, limit)

    async def semantic_recall(
        self, query: str, user_id: str, top_k: int = 5
    ) -> list[MemoryChunk]:
        return await self._semantic.search(query, user_id, top_k)

    async def combined_search(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
        fts5_weight: float = 0.6,
    ) -> list[MergedResult]:
        fts5_results = await self.session_search(query, user_id, limit)
        qdrant_results = await self.semantic_recall(query, user_id, limit)
        return merge_search_results_rrf(
            fts5_results, qdrant_results, fts5_weight
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _memory_path(self, user_id: str, filename: str) -> Path:
        d = self.memories_dir / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d / filename

    def _memory_dir(self, user_id: str) -> Path:
        d = self.memories_dir / user_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def close(self):
        await self._session_db.close()

    # ── Namespace-aware Operations (Módulo 4 - Memória Unificada) ─────────

    async def get_namespace(self, namespace: str, user_id: str = "system") -> dict:
        """Retorna todos os dados de um namespace de memória."""
        ns_dir = self.memories_dir / user_id / "namespaces" / namespace
        result: dict = {}
        if not ns_dir.exists():
            return result
        for f in ns_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                result[f.stem] = data
            except (json.JSONDecodeError, OSError):
                continue
        return result

    async def search_namespace(
        self, query: str, user_id: str = "system", limit: int = 10
    ) -> list[dict]:
        """Busca textual em todos os namespaces de memória."""
        results = []
        base = self.memories_dir / user_id / "namespaces"
        if not base.exists():
            return results
        query_lower = query.lower()
        for ns_dir in sorted(base.iterdir()):
            if not ns_dir.is_dir():
                continue
            for f in ns_dir.glob("*.json"):
                try:
                    content = f.read_text().lower()
                    if query_lower in content:
                        data = json.loads(f.read_text())
                        results.append({
                            "namespace": ns_dir.name,
                            "key": f.stem,
                            "data": data,
                        })
                except (json.JSONDecodeError, OSError):
                    continue
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        return results

    async def store_namespace(
        self, namespace: str, key: str, data: dict, user_id: str = "system"
    ):
        """Armazena dados em um namespace específico."""
        ns_dir = self.memories_dir / user_id / "namespaces" / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        (ns_dir / f"{key}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    async def delete_namespace_key(
        self, namespace: str, key: str, user_id: str = "system"
    ):
        """Remove uma chave de um namespace."""
        path = self.memories_dir / user_id / "namespaces" / namespace / f"{key}.json"
        if path.exists():
            path.unlink()

    async def cross_namespace_query(
        self, query: str, namespaces: list[str], user_id: str = "system"
    ) -> str:
        """Consulta cruzada entre múltiplos namespaces.
        Ex: projetos + emails para 'tem vaga de Python?'"""
        results_parts: list[str] = []
        for ns in namespaces:
            ns_data = await self.get_namespace(ns, user_id)
            query_lower = query.lower()
            matches = []
            for key, data in ns_data.items():
                data_str = json.dumps(data, ensure_ascii=False).lower()
                if query_lower in data_str:
                    matches.append(data)
            if matches:
                results_parts.append(
                    f"### {ns} ({len(matches)} resultados)\n"
                    + "\n".join(
                        json.dumps(m, ensure_ascii=False, indent=2)[:500]
                        for m in matches[:5]
                    )
                )
        return "\n\n".join(results_parts) if results_parts else "Nenhum resultado."
        await self._semantic.close()
