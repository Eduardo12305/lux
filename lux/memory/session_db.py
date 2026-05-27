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
    ApprovalPattern,
    Channel,
    Formality,
    ListeningMode,
    Message,
    ResponseStyle,
    Role,
    SessionSearchResult,
    ToolCall,
    UserProfile,
    UserRole,
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

    # ── User Profiles ────────────────────────────────────────────────────

    async def create_profile(self, profile: UserProfile) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT INTO user_profiles
               (user_id, username, display_name, role, preferred_lang,
                response_style, formality, voice_enabled, listening_mode,
                preferred_voice, preferred_channel, enabled_toolsets,
                approval_patterns, disabled_skills, work_hours_start,
                work_hours_end, timezone, total_sessions, total_tokens,
                created_at, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile.user_id,
                profile.username,
                profile.display_name,
                profile.role.value,
                profile.preferred_language,
                profile.response_style.value,
                profile.formality.value,
                int(profile.voice_enabled),
                profile.listening_mode.value,
                profile.preferred_voice,
                profile.preferred_channel.value,
                json.dumps(profile.enabled_toolsets),
                json.dumps(
                    [
                        {"label": p.label, "regex": p.regex, "toolset": p.toolset,
                         "always_allow": p.always_allow}
                        for p in profile.approval_patterns
                    ]
                ),
                json.dumps(profile.disabled_skills),
                profile.work_hours[0].isoformat() if profile.work_hours[0] else None,
                profile.work_hours[1].isoformat() if profile.work_hours[1] else None,
                profile.timezone,
                profile.total_sessions,
                profile.total_tokens_used,
                profile.created_at.isoformat(),
                profile.last_seen.isoformat() if profile.last_seen else None,
            ),
        )
        await conn.commit()

    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        from datetime import time as dt_time
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        row = dict(row)
        return self._row_to_profile(row)

    async def get_profile_by_username(self, username: str) -> Optional[UserProfile]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM user_profiles WHERE username = ?", (username,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_profile(dict(row))

    async def update_profile(self, profile: UserProfile) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """UPDATE user_profiles SET
               display_name=?, role=?, preferred_lang=?, response_style=?,
               formality=?, voice_enabled=?, listening_mode=?, preferred_voice=?,
               preferred_channel=?, enabled_toolsets=?, approval_patterns=?,
               disabled_skills=?, work_hours_start=?, work_hours_end=?,
               timezone=?, total_sessions=?, total_tokens=?, last_seen=?
               WHERE user_id=?""",
            (
                profile.display_name,
                profile.role.value,
                profile.preferred_language,
                profile.response_style.value,
                profile.formality.value,
                int(profile.voice_enabled),
                profile.listening_mode.value,
                profile.preferred_voice,
                profile.preferred_channel.value,
                json.dumps(profile.enabled_toolsets),
                json.dumps(
                    [
                        {"label": p.label, "regex": p.regex, "toolset": p.toolset,
                         "always_allow": p.always_allow}
                        for p in profile.approval_patterns
                    ]
                ),
                json.dumps(profile.disabled_skills),
                profile.work_hours[0].isoformat() if profile.work_hours[0] else None,
                profile.work_hours[1].isoformat() if profile.work_hours[1] else None,
                profile.timezone,
                profile.total_sessions,
                profile.total_tokens_used,
                profile.last_seen.isoformat() if profile.last_seen else None,
                profile.user_id,
            ),
        )
        await conn.commit()

    async def delete_profile(self, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
        await conn.commit()

    async def list_profiles(self) -> list[UserProfile]:
        conn = await self._get_conn()
        cursor = await conn.execute("SELECT * FROM user_profiles")
        rows = await cursor.fetchall()
        return [self._row_to_profile(dict(row)) for row in rows]

    def _row_to_profile(self, row: dict) -> UserProfile:
        from datetime import datetime as dt_datetime, time as dt_time_

        return UserProfile(
            user_id=row.get("user_id", ""),
            username=row.get("username", ""),
            display_name=row.get("display_name", ""),
            role=UserRole(row.get("role", "user")),
            preferred_language=row.get("preferred_lang", "pt-BR"),
            response_style=ResponseStyle(row.get("response_style", "balanced")),
            formality=Formality(row.get("formality", "casual")),
            voice_enabled=bool(row.get("voice_enabled", False)),
            listening_mode=ListeningMode(row.get("listening_mode", "push_to_talk")),
            preferred_voice=row.get("preferred_voice", "pt_BR-faber-medium"),
            preferred_channel=Channel(row.get("preferred_channel", "cli")),
            enabled_toolsets=_safe_json_list(row.get("enabled_toolsets", "[]")),
            approval_patterns=[
                ApprovalPattern(
                    label=p.get("label", ""),
                    regex=p.get("regex", ""),
                    toolset=p.get("toolset", ""),
                    always_allow=p.get("always_allow", False),
                )
                for p in _safe_json_list(row.get("approval_patterns", "[]"))
            ],
            disabled_skills=_safe_json_list(row.get("disabled_skills", "[]")),
            work_hours=(
                _parse_time(row.get("work_hours_start")),
                _parse_time(row.get("work_hours_end")),
            ),
            timezone=row.get("timezone", "America/Sao_Paulo"),
            total_sessions=row.get("total_sessions", 0),
            total_tokens_used=row.get("total_tokens", 0),
            created_at=_parse_datetime(row.get("created_at")),
            last_seen=_parse_datetime(row.get("last_seen")),
        )

    # ── Whitelist ─────────────────────────────────────────────────────────

    async def add_to_whitelist(self, platform: str, user_id: str, label: str = "") -> None:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO whitelist (platform, user_id, label, added_at)
               VALUES (?, ?, ?, ?)""",
            (platform, user_id, label, datetime.now().isoformat()),
        )
        await conn.commit()

    async def remove_from_whitelist(self, platform: str, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "DELETE FROM whitelist WHERE platform = ? AND user_id = ?",
            (platform, user_id),
        )
        await conn.commit()

    async def is_whitelisted(self, platform: str, user_id: str) -> bool:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT 1 FROM whitelist WHERE platform = ? AND user_id = ?",
            (platform, user_id),
        )
        row = await cursor.fetchone()
        return row is not None

    async def get_whitelist(self, platform: str) -> list[str]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT user_id FROM whitelist WHERE platform = ?", (platform,)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    # ── Pairing Codes ─────────────────────────────────────────────────────

    async def save_pairing_code(self, code: str, user_id: str, platform: str,
                                  expires_at: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO pairing_codes (code, user_id, platform, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (code, user_id, platform, datetime.now().isoformat(), expires_at),
        )
        await conn.commit()

    async def get_pairing_code(self, code: str) -> Optional[dict]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM pairing_codes WHERE code = ?", (code,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_pairing_code(self, code: str) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM pairing_codes WHERE code = ?", (code,))
        await conn.commit()

    async def cleanup_expired_pairing_codes(self) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "DELETE FROM pairing_codes WHERE expires_at < ?",
            (datetime.now().isoformat(),),
        )
        await conn.commit()
        return cursor.rowcount

    # ── Password Hashes ────────────────────────────────────────────────────

    async def _store_password_hash(self, user_id: str, password_hash: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO password_hashes (user_id, hash, updated_at)
               VALUES (?, ?, ?)""",
            (user_id, password_hash, datetime.now().isoformat()),
        )
        await conn.commit()

    async def _get_password_hash(self, user_id: str) -> str:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT hash FROM password_hashes WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else ""

    async def _delete_password_hash(self, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM password_hashes WHERE user_id = ?", (user_id,))
        await conn.commit()

    async def _store_pin_hash(self, user_id: str, pin_hash: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE password_hashes SET pin_hash = ?, updated_at = ? WHERE user_id = ?",
            (pin_hash, datetime.now().isoformat(), user_id),
        )
        await conn.commit()

    async def _get_pin_hash(self, user_id: str) -> str:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT pin_hash FROM password_hashes WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else ""

    async def _increment_failed_attempts(self, user_id: str) -> int:
        conn = await self._get_conn()
        now = datetime.now().isoformat()
        await conn.execute(
            """INSERT INTO password_hashes (user_id, hash, pin_hash, failed_attempts, locked_until, password_changed_at, updated_at)
               VALUES (?, '', '', 1, NULL, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET failed_attempts = failed_attempts + 1, updated_at = ?""",
            (user_id, now, now, now),
        )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT failed_attempts FROM password_hashes WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def _reset_failed_attempts(self, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE password_hashes SET failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
            (user_id,),
        )
        await conn.commit()

    async def _set_locked_until(self, user_id: str, locked_until) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE password_hashes SET locked_until = ? WHERE user_id = ?",
            (locked_until.isoformat(), user_id),
        )
        await conn.commit()

    async def _get_locked_until(self, user_id: str):
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT locked_until FROM password_hashes WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return None

    # ── Auth Sessions ──────────────────────────────────────────────────────

    async def _store_auth_session(self, session) -> None:
        from lux.auth.models import AuthSession
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO auth_sessions
               (session_id, user_id, role, auth_method, voice_confidence,
                channel, created_at, expires_at, last_activity, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                session.session_id,
                session.user_id,
                session.role.value,
                session.auth_method.value,
                session.voice_confidence,
                session.channel.value,
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                session.last_activity.isoformat(),
            ),
        )
        await conn.commit()

    async def _get_auth_session(self, session_id: str) -> Optional[object]:
        from lux.auth.models import AuthMethod, AuthSession
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM auth_sessions WHERE session_id = ? AND is_active = 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        row = dict(row)
        return AuthSession(
            session_id=row.get("session_id", ""),
            user_id=row.get("user_id", ""),
            role=UserRole(row.get("role", "user")),
            auth_method=AuthMethod(row.get("auth_method", "password")),
            voice_confidence=row.get("voice_confidence"),
            channel=Channel(row.get("channel", "cli")),
            created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else datetime.now(),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row.get("expires_at") else datetime.now(),
            last_activity=datetime.fromisoformat(row["last_activity"]) if row.get("last_activity") else datetime.now(),
        )

    async def _update_auth_session_activity(self, session_id: str, last_activity: datetime) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE auth_sessions SET last_activity = ? WHERE session_id = ?",
            (last_activity.isoformat(), session_id),
        )
        await conn.commit()

    async def _deactivate_auth_session(self, session_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE auth_sessions SET is_active = 0 WHERE session_id = ?",
            (session_id,),
        )
        await conn.commit()

    async def _revoke_auth_session(self, session_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute(
            "UPDATE auth_sessions SET is_active = 0, revoked_at = ? WHERE session_id = ?",
            (datetime.now().isoformat(), session_id),
        )
        await conn.commit()

    async def _list_active_sessions(self, user_id: str) -> list:
        from lux.auth.models import AuthMethod, AuthSession
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT * FROM auth_sessions WHERE user_id = ? AND is_active = 1",
            (user_id,),
        )
        rows = await cursor.fetchall()
        sessions = []
        for row in rows:
            row = dict(row)
            sessions.append(AuthSession(
                session_id=row.get("session_id", ""),
                user_id=row.get("user_id", ""),
                role=UserRole(row.get("role", "user")),
                auth_method=AuthMethod(row.get("auth_method", "password")),
                voice_confidence=row.get("voice_confidence"),
                channel=Channel(row.get("channel", "cli")),
                created_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else datetime.now(),
                expires_at=datetime.fromisoformat(row["expires_at"]) if row.get("expires_at") else datetime.now(),
                last_activity=datetime.fromisoformat(row["last_activity"]) if row.get("last_activity") else datetime.now(),
            ))
        return sessions

    async def _cleanup_expired_auth_sessions(self) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "DELETE FROM auth_sessions WHERE expires_at < ? AND is_active = 1",
            (datetime.now().isoformat(),),
        )
        await conn.commit()
        return cursor.rowcount

    # ── Audit Log ───────────────────────────────────────────────────────────

    async def _write_audit_log(
        self, id: str, user_id: str, event_type: str,
        channel: str, details: str, source: str = "",
    ) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT INTO audit_log (id, user_id, event_type, channel, details, ip_or_source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id, user_id, event_type, channel, details, source, datetime.now().isoformat()),
        )
        await conn.commit()

    async def _get_audit_log(
        self, user_id: str | None = None, event_type: str | None = None, limit: int = 50
    ) -> list[dict]:
        conn = await self._get_conn()
        where = []
        params: list = []
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        clause = " AND ".join(where) if where else "1=1"
        sql = f"SELECT * FROM audit_log WHERE {clause} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = await conn.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ── Voice Profiles ─────────────────────────────────────────────────────

    async def _get_voice_centroid(self, user_id: str):
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT centroid FROM voice_profiles WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row if row else None

    async def _set_voice_centroid(self, user_id: str, centroid: str, n_samples: int,
                                    estimated_eer: float, quality: str) -> None:
        conn = await self._get_conn()
        now = datetime.now().isoformat()
        await conn.execute(
            """INSERT OR REPLACE INTO voice_profiles
               (user_id, centroid, n_samples, estimated_eer, quality, enrolled_at, last_updated, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (user_id, centroid, n_samples, estimated_eer, quality, now, now),
        )
        await conn.commit()

    async def _get_voice_sample_count(self, user_id: str) -> int:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM voice_samples WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def _store_voice_sample(self, user_id: str, embedding: str,
                                    snr_db: float, duration_s: float) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT INTO voice_samples (id, user_id, embedding, snr_db, duration_s, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (f"vs_{__import__('uuid').uuid4().hex[:12]}", user_id, embedding,
             snr_db, duration_s, datetime.now().isoformat()),
        )
        await conn.commit()

    async def _list_voice_profiles(self) -> list[dict]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT user_id, centroid FROM voice_profiles WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def _delete_voice_profile(self, user_id: str) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM voice_profiles WHERE user_id = ?", (user_id,))
        await conn.execute("DELETE FROM voice_samples WHERE user_id = ?", (user_id,))
        await conn.commit()

    # ── Platform Links (unified memory) ────────────────────────────────────

    async def _get_platform_link(self, platform: str, platform_user_id: str) -> Optional[str]:
        conn = await self._get_conn()
        cursor = await conn.execute(
            "SELECT lux_user_id FROM platform_links WHERE platform = ? AND platform_user_id = ?",
            (platform, platform_user_id),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def _link_platform(
        self, platform: str, platform_user_id: str, lux_user_id: str
    ) -> None:
        conn = await self._get_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO platform_links (platform, platform_user_id, lux_user_id, linked_at)
               VALUES (?, ?, ?, ?)""",
            (platform, platform_user_id, lux_user_id, datetime.now().isoformat()),
        )
        await conn.commit()

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


def _safe_json_list(raw: str | list) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        from datetime import time as dt_time
        parts = value.split(":")
        return dt_time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def _parse_datetime(value: str | None):
    if not value:
        return None
    try:
        from datetime import datetime as dt_datetime
        return dt_datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
