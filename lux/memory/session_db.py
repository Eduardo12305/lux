# lux/memory/session_db.py
# Módulo: Memory
# Dependências: config.py, constants.py, agent/state.py
# Status: IMPLEMENTADO
# Notas: SQLite + FTS5 com lineage tracking (GAP 1). SchemaVersionManager (GAP 10).

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import aiosqlite

from lux.agent.state import (
    Channel,
    Message,
    Role,
    SessionSearchResult,
    ToolCall,
)
from lux.config import get_config
from lux.constants import SESSIONS_DB_PATH

logger = logging.getLogger(__name__)


class SchemaVersionManager:
    """Gerencia migracoes de schema do SQLite (GAP 10)."""

    MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

    async def ensure_latest(self, db: aiosqlite.Connection):
        current = await self._get_current_version(db)
        migrations = sorted(self.MIGRATIONS_DIR.glob("*.sql"))
        for migration in migrations:
            version = int(migration.name.split("_")[0])
            if version > current:
                logger.info("Aplicando migration %s", migration.name)
                sql = migration.read_text()
                await db.executescript(sql)
                current = version
        logger.info("Schema na versao %d", current)

    async def _get_current_version(self, db: aiosqlite.Connection) -> int:
        try:
            cursor = await db.execute("SELECT MAX(version) FROM schema_version")
            row = await cursor.fetchone()
            return row[0] if row[0] is not None else 0
        except aiosqlite.OperationalError:
            return 0


class SessionDB:
    """Armazenamento de sessoes com FTS5 e lineage tracking."""

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path) if db_path else SESSIONS_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._init_schema()
        return self._conn

    async def _init_schema(self):
        conn = await self._get_conn()
        migrator = SchemaVersionManager()
        await migrator.ensure_latest(conn)

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── Sessions ─────────────────────────────────────────────────────────

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        channel: Channel,
        parent_id: Optional[str] = None,
    ) -> None:
        conn = await self._get_conn()
        lineage_root = None
        if parent_id:
            row = await conn.execute_fetchall(
                "SELECT lineage_root FROM sessions WHERE id = ?", (parent_id,)
            )
            if row:
                lineage_root = row[0][0] or parent_id

        await conn.execute(
            """INSERT INTO sessions (id, user_id, channel, parent_id, lineage_root, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, user_id, channel.value, parent_id, lineage_root, datetime.now().isoformat()),
        )
        await conn.commit()

    async def create_child_session(
        self,
        parent_session_id: str,
        compression_summary: str,
        messages_compressed: int,
    ) -> str:
        conn = await self._get_conn()
        parent = await self.get_session(parent_session_id)
        if not parent:
            raise ValueError(f"Sessao pai {parent_session_id} nao encontrada")

        child_id = uuid4().hex
        lineage_root = parent.get("lineage_root") or parent_session_id

        await conn.execute(
            """INSERT INTO sessions (id, user_id, channel, parent_id, lineage_root,
                                     started_at, compressed, compression_count, summary)
               VALUES (?, ?, ?, ?, ?, ?, TRUE, ?, ?)""",
            (
                child_id,
                parent["user_id"],
                parent["channel"],
                parent_session_id,
                lineage_root,
                datetime.now().isoformat(),
                (parent.get("compression_count", 0) + 1),
                compression_summary,
            ),
        )
        await conn.execute(
            "UPDATE sessions SET ended_at = ?, compressed = TRUE WHERE id = ?",
            (datetime.now().isoformat(), parent_session_id),
        )
        await conn.commit()
        logger.info("Sessao filha %s criada a partir de %s", child_id, parent_session_id)
        return child_id

    async def get_session(self, session_id: str) -> Optional[dict]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def end_session(self, session_id: str, tokens_used: int = 0):
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE sessions SET ended_at = ?, tokens_used = ? WHERE id = ?",
            (datetime.now().isoformat(), tokens_used, session_id),
        )
        await conn.commit()

    async def load_history(
        self, session_id: str, limit: int = 50
    ) -> list[Message]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            """SELECT * FROM messages
               WHERE session_id = ?
               ORDER BY timestamp ASC
               LIMIT ?""",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_message(dict(r)) for r in rows]

    # ── Messages ──────────────────────────────────────────────────────────

    async def save_message(self, message: Message):
        conn = await self._get_conn()
        tool_calls_json = (
            json.dumps([tc.to_openai_dict() for tc in message.tool_calls])
            if message.tool_calls
            else None
        )
        await conn.execute(
            """INSERT INTO messages
               (id, session_id, user_id, role, content, thinking, tool_calls,
                tool_call_id, model_used, tokens_prompt, tokens_completion,
                latency_ms, timestamp, iteration, task_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message.id,
                message.session_id,
                message.user_id,
                message.role.value,
                message.content,
                message.thinking_content,
                tool_calls_json,
                message.tool_call_id,
                message.model_used,
                message.tokens_prompt,
                message.tokens_completion,
                message.latency_ms,
                message.timestamp.isoformat(),
                message.iteration,
                message.task_id,
            ),
        )
        await conn.commit()

    async def save_messages(self, messages: list[Message]):
        conn = await self._get_conn()
        for msg in messages:
            tool_calls_json = (
                json.dumps([tc.to_openai_dict() for tc in msg.tool_calls])
                if msg.tool_calls
                else None
            )
            await conn.execute(
                """INSERT OR REPLACE INTO messages
                   (id, session_id, user_id, role, content, thinking, tool_calls,
                    tool_call_id, model_used, tokens_prompt, tokens_completion,
                    latency_ms, timestamp, iteration, task_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg.id,
                    msg.session_id,
                    msg.user_id,
                    msg.role.value,
                    msg.content,
                    msg.thinking_content,
                    tool_calls_json,
                    msg.tool_call_id,
                    msg.model_used,
                    msg.tokens_prompt,
                    msg.tokens_completion,
                    msg.latency_ms,
                    msg.timestamp.isoformat(),
                    msg.iteration,
                    msg.task_id,
                ),
            )
        await conn.commit()

    # ── FTS5 Search ───────────────────────────────────────────────────────

    async def fts_search(
        self,
        query: str,
        user_id: str,
        limit: int = 5,
    ) -> list[SessionSearchResult]:
        conn = await self._get_conn()
        sql = """
        SELECT
            m.id,
            m.session_id,
            m.timestamp,
            m.role,
            snippet(messages_fts, 0, '<b>', '</b>', '...', 15) AS snippet,
            bm25(messages_fts) AS score
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH ?
          AND s.user_id = ?
          AND m.role IN ('user', 'assistant')
        ORDER BY score
        LIMIT ?
        """
        cursor = await conn.execute(sql, (query, user_id, limit))
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            results.append(SessionSearchResult(
                id=row[0],
                session_id=row[1],
                timestamp=str(row[2]),
                role=row[3],
                snippet=row[4],
                score=float(row[5]),
            ))
        return results

    # ── Helpers ───────────────────────────────────────────────────────────

    def _row_to_message(self, row: dict) -> Message:
        tool_calls = []
        if row.get("tool_calls"):
            try:
                raw = json.loads(row["tool_calls"])
                tool_calls = [
                    ToolCall(
                        id=tc.get("id", ""),
                        function_name=tc.get("function", {}).get("name", ""),
                        arguments=tc.get("function", {}).get("arguments", {}),
                    )
                    for tc in raw
                ]
            except (json.JSONDecodeError, KeyError):
                pass

        return Message(
            id=row.get("id", ""),
            session_id=row.get("session_id", ""),
            user_id=row.get("user_id", ""),
            role=Role(row.get("role", "user")),
            content=row.get("content", ""),
            thinking_content=row.get("thinking"),
            tool_calls=tool_calls,
            tool_call_id=row.get("tool_call_id"),
            model_used=row.get("model_used", ""),
            tokens_prompt=row.get("tokens_prompt", 0),
            tokens_completion=row.get("tokens_completion", 0),
            latency_ms=row.get("latency_ms", 0),
            timestamp=datetime.fromisoformat(row["timestamp"]) if row.get("timestamp") else datetime.now(),
            iteration=row.get("iteration", 0),
            task_id=row.get("task_id", ""),
        )
