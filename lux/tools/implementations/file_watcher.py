# lux/tools/implementations/file_watcher.py
# Módulo: Tools — Monitoramento Inteligente de Diretórios
# Dependências: memory/manager.py, config.py, models/llama_client.py
# Status: IMPLEMENTADO
# Notas: Scanner de diretórios + watcher em tempo real + indexação na memória.
#   Integra com o plano_agente_inteligente.md — Módulo 1.

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lux.config import get_config
from lux.constants import LUX_HOME

logger = logging.getLogger(__name__)

INDEX_PATH = LUX_HOME / "file_index.json"
WATCHER_STATE_PATH = LUX_HOME / "watcher_state.json"


@dataclass
class FileEntry:
    path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    summary: str = ""
    indexed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "modified_at": self.modified_at,
            "summary": self.summary,
            "indexed_at": self.indexed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> FileEntry:
        return cls(
            path=d.get("path", ""),
            name=d.get("name", ""),
            extension=d.get("extension", ""),
            size_bytes=d.get("size_bytes", 0),
            modified_at=d.get("modified_at", ""),
            summary=d.get("summary", ""),
            indexed_at=d.get("indexed_at", ""),
        )


@dataclass
class FileIndex:
    entries: dict[str, FileEntry] = field(default_factory=dict)
    scanned_dirs: list[str] = field(default_factory=list)
    last_full_scan: str = ""

    def to_dict(self) -> dict:
        return {
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "scanned_dirs": self.scanned_dirs,
            "last_full_scan": self.last_full_scan,
        }

    @classmethod
    def from_dict(cls, d: dict) -> FileIndex:
        entries = {}
        for k, v in d.get("entries", {}).items():
            entries[k] = FileEntry.from_dict(v)
        return cls(
            entries=entries,
            scanned_dirs=d.get("scanned_dirs", []),
            last_full_scan=d.get("last_full_scan", ""),
        )


class DirectoryScanner:
    """Scanner recursivo de diretórios com geração de índice."""

    def __init__(self):
        config = get_config()
        self._watch_dirs = [
            Path(p.strip()).expanduser().resolve()
            for p in config.watch_dirs.split(",")
            if p.strip()
        ]
        self._accepted = set(
            ext.strip().lower()
            for ext in config.accepted_extensions.split(",")
            if ext.strip()
        )
        self._max_depth = config.dir_max_depth
        self._index: Optional[FileIndex] = None

    @property
    def watch_dirs(self) -> list[Path]:
        return self._watch_dirs

    @property
    def index(self) -> FileIndex:
        if self._index is None:
            self._index = self._load_index()
        return self._index

    def set_watch_dirs(self, dirs: list[str]):
        self._watch_dirs = [
            Path(p.strip()).expanduser().resolve() for p in dirs if p.strip()
        ]

    def full_scan(self) -> FileIndex:
        index = FileIndex(
            scanned_dirs=[str(d) for d in self._watch_dirs],
            last_full_scan=datetime.now(timezone.utc).isoformat(),
        )

        for watch_dir in self._watch_dirs:
            if not watch_dir.exists():
                logger.warning("Diretório não encontrado: %s", watch_dir)
                continue
            self._scan_directory(watch_dir, watch_dir, 0, index)

        self._index = index
        self._save_index(index)
        logger.info(
            "Scan completo: %d arquivos em %d diretórios",
            len(index.entries), len(self._watch_dirs),
        )
        return index

    def scan_single_file(self, file_path: Path) -> Optional[FileEntry]:
        if not file_path.exists() or not file_path.is_file():
            return None
        ext = file_path.suffix.lower()
        if ext not in self._accepted:
            return None
        entry = self._create_entry(file_path)
        if self._index is not None:
            self._index.entries[str(file_path)] = entry
            self._save_index(self._index)
        return entry

    def remove_from_index(self, file_path: Path):
        if self._index is not None:
            key = str(file_path)
            if key in self._index.entries:
                del self._index.entries[key]
                self._save_index(self._index)
                logger.debug("Removido do índice: %s", file_path)

    def _scan_directory(
        self, root: Path, current: Path, depth: int, index: FileIndex
    ):
        if depth > self._max_depth:
            return
        try:
            for entry in sorted(current.iterdir()):
                if entry.name.startswith(".") or entry.name.startswith("__"):
                    continue
                if entry.name in ("node_modules", ".venv", "venv", ".git",
                                   "__pycache__", "target", "build", "dist"):
                    continue
                if entry.is_file():
                    ext = entry.suffix.lower()
                    if ext in self._accepted:
                        file_entry = self._create_entry(entry)
                        index.entries[str(entry)] = file_entry
                elif entry.is_dir() and depth < self._max_depth:
                    self._scan_directory(root, entry, depth + 1, index)
        except PermissionError:
            logger.debug("Sem permissão: %s", current)

    def _create_entry(self, file_path: Path) -> FileEntry:
        stat = file_path.stat()
        return FileEntry(
            path=str(file_path),
            name=file_path.name,
            extension=file_path.suffix.lower(),
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            summary="",
            indexed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _load_index(self) -> FileIndex:
        if INDEX_PATH.exists():
            try:
                data = json.loads(INDEX_PATH.read_text())
                return FileIndex.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                logger.warning("Índice corrompido, recriando")
        return FileIndex()

    def _save_index(self, index: FileIndex):
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(
            json.dumps(index.to_dict(), ensure_ascii=False, indent=2)
        )


class FileSummarizer:
    """Gera resumos de arquivos usando heurísticas ou LLM auxiliar (1.7B)."""

    MAX_PREVIEW_CHARS = 200

    def summarize(self, entry: FileEntry) -> str:
        try:
            path = Path(entry.path)
            if not path.exists():
                return "[arquivo não encontrado]"
            content = path.read_text(errors="replace")[:4096]
            lines = content.strip().split("\n")
            non_empty = [l.strip() for l in lines if l.strip()
                         and not l.strip().startswith(("#", "//", "/*", "*"))]
            if non_empty:
                return non_empty[0][:self.MAX_PREVIEW_CHARS]
            return f"[{entry.extension} - {entry.size_bytes} bytes]"
        except Exception:
            return f"[{entry.extension} - {entry.size_bytes} bytes]"

    async def summarize_with_llm(
        self, entry: FileEntry, llama_client=None
    ) -> str:
        try:
            path = Path(entry.path)
            if not path.exists():
                return "[arquivo não encontrado]"
            content = path.read_text(errors="replace")[:2048]

            if llama_client:
                try:
                    from lux.agent.auxiliary_client import AuxiliaryLLMClient
                    from lux.agent.model_router import ModelRouter
                    aux = AuxiliaryLLMClient(llama_client, ModelRouter())
                    result = await aux.summarize_short(content, max_tokens=100)
                    if result.content and result.content.strip():
                        return result.content.strip()[:self.MAX_PREVIEW_CHARS]
                except Exception:
                    pass

            lines = content.strip().split("\n")
            non_empty = [l.strip() for l in lines if l.strip()
                         and not l.strip().startswith(("#", "//"))]
            if non_empty:
                return non_empty[0][:self.MAX_PREVIEW_CHARS]
            return f"[{entry.extension}]"
        except Exception:
            return f"[{entry.extension}]"


class FileWatcher:
    """Motor de monitoramento de diretórios + indexação na memória.

    Integra com MemoryManager para consultas contextuais cruzadas.
    Usa polling como fallback quando watchdog não está disponível.
    """

    POLL_INTERVAL = 30

    def __init__(
        self,
        scanner: Optional[DirectoryScanner] = None,
        summarizer: Optional[FileSummarizer] = None,
    ):
        config = get_config()
        self._scanner = scanner or DirectoryScanner()
        self._summarizer = summarizer or FileSummarizer()
        self._enabled = config.file_watcher_enabled
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._observer = None
        self._memory_manager = None

    @property
    def is_running(self) -> bool:
        return self._running

    def set_memory_manager(self, memory_manager):
        self._memory_manager = memory_manager

    async def start(self):
        if not self._enabled:
            logger.info("FileWatcher desabilitado")
            return
        if not self._scanner.watch_dirs:
            logger.info("FileWatcher: sem diretórios configurados (WATCH_DIRS)")
            return

        self._running = True
        logger.info(
            "FileWatcher iniciado: %d diretórios",
            len(self._scanner.watch_dirs),
        )

        self._scanner.full_scan()

        if self._memory_manager:
            await self._index_to_memory()

        self._start_watchdog()

        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._stop_watchdog()

    async def _poll_loop(self):
        config = get_config()
        interval = config.reindex_interval * 60
        while self._running:
            await asyncio.sleep(interval)
            try:
                self._scanner.full_scan()
                if self._memory_manager:
                    await self._index_to_memory()
            except Exception:
                logger.exception("Erro no poll do FileWatcher")

    async def reindex_file(self, file_path: Path):
        entry = self._scanner.scan_single_file(file_path)
        if entry and self._memory_manager:
            await self._index_single_to_memory(entry)

    async def _index_to_memory(self):
        index = self._scanner.index
        projects = {}
        for key, entry in index.entries.items():
            path = Path(entry.path)
            for watch_dir in self._scanner.watch_dirs:
                try:
                    rel = path.relative_to(watch_dir)
                    project = str(rel.parts[0]) if rel.parts else "root"
                    break
                except ValueError:
                    project = "outros"

            if project not in projects:
                projects[project] = []
            projects[project].append({
                "file": entry.name,
                "path": entry.path,
                "summary": entry.summary or self._summarizer.summarize(entry),
                "modified": entry.modified_at[:10],
            })

        try:
            await self._memory_manager.add_memory(
                "file_index",
                json.dumps(projects, ensure_ascii=False),
                target="lux/file_watcher",
                user_id="system",
            )
            logger.debug("Índice de arquivos salvo na memória: %d projetos", len(projects))
        except Exception as e:
            logger.debug("Falha ao salvar índice na memória: %s", e)

    async def _index_single_to_memory(self, entry: FileEntry):
        if not self._memory_manager:
            return
        summary = entry.summary or self._summarizer.summarize(entry)
        try:
            await self._memory_manager.add_memory(
                f"file:{entry.name}",
                json.dumps({"file": entry.name, "path": entry.path,
                            "summary": summary, "modified": entry.modified_at[:10]},
                           ensure_ascii=False),
                target="lux/file_watcher",
                user_id="system",
            )
        except Exception as e:
            logger.debug("Falha ao indexar arquivo na memória: %s", e)

    def _start_watchdog(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self, watcher):
                    self._w = watcher

                def on_modified(self, event):
                    if not event.is_directory:
                        asyncio.ensure_future(
                            self._w.reindex_file(Path(event.src_path))
                        )

                def on_created(self, event):
                    if not event.is_directory:
                        asyncio.ensure_future(
                            self._w.reindex_file(Path(event.src_path))
                        )

                def on_deleted(self, event):
                    if not event.is_directory:
                        self._w._scanner.remove_from_index(
                            Path(event.src_path)
                        )

            self._observer = Observer()
            for watch_dir in self._scanner.watch_dirs:
                if watch_dir.exists():
                    self._observer.schedule(
                        _Handler(self), str(watch_dir), recursive=True
                    )
            self._observer.start()
            logger.info("Watchdog iniciado em %d diretórios",
                         len(self._scanner.watch_dirs))
        except ImportError:
            logger.info("Watchdog não instalado — usando polling (%ds)",
                         self.POLL_INTERVAL)
        except Exception as e:
            logger.warning("Watchdog falhou, usando polling: %s", e)

    def _stop_watchdog(self):
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
            self._observer = None


class FileQueryTool:
    """Ferramenta para consultar o índice de arquivos monitorados."""

    name = "file_query"
    description = (
        "Consulta o índice de arquivos monitorados. "
        "Busca por nome, conteúdo ou projeto."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termo de busca (nome de arquivo, palavra-chave ou projeto)",
            },
            "project": {
                "type": "string",
                "description": "Filtrar por projeto/diretório específico",
            },
        },
        "required": ["query"],
    }

    def __init__(self, scanner: Optional[DirectoryScanner] = None):
        self._scanner = scanner or DirectoryScanner()

    def execute(self, args: dict, state) -> "ToolResult":
        from lux.agent.state import ToolResult

        query = args.get("query", "").lower()
        project_filter = args.get("project", "").lower()

        index = self._scanner.index
        results = []

        for key, entry in index.entries.items():
            path = Path(entry.path)
            name_lower = entry.name.lower()

            if project_filter and project_filter not in str(path).lower():
                continue

            if query in name_lower or query in str(path).lower():
                results.append(
                    f"  {entry.name} ({entry.extension}) — "
                    f"{entry.modified_at[:10]} — {entry.size_bytes}B"
                )
            elif entry.summary and query in entry.summary.lower():
                results.append(
                    f"  {entry.name} — {entry.summary[:80]}..."
                )

        if not results:
            return ToolResult.ok(
                f"Nenhum arquivo encontrado para '{query}'"
                + (f" no projeto '{project_filter}'" if project_filter else "")
            )

        header = f"Arquivos encontrados ({len(results)}):"
        return ToolResult.ok(header + "\n" + "\n".join(results[:20]))
