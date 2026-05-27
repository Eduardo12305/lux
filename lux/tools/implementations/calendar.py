# lux/tools/implementations/calendar.py
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from lux.agent.state import AgentState, ToolResult
from lux.constants import LUX_HOME
from lux.tools.base import Tool

CALENDAR_DIR = LUX_HOME / "calendar"


def _calendar_path(user_id: str) -> Path:
    CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
    return CALENDAR_DIR / f"{user_id}.json"


def _load(user_id: str) -> dict:
    path = _calendar_path(user_id)
    if not path.exists():
        return {"events": [], "reminders": []}
    return json.loads(path.read_text())


def _save(user_id: str, data: dict):
    _calendar_path(user_id).write_text(json.dumps(data, ensure_ascii=False, indent=2))


class CalendarReadTool(Tool):
    name = "calendar_read"
    description = "Le eventos do calendario em um periodo"
    parameters_schema = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Dias a frente (7 = proxima semana)", "default": 7},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        days = args.get("days", 7)
        data = _load(state.user_id)
        events = data.get("events", [])
        now = datetime.now()
        end = now + timedelta(days=days)

        upcoming = [
            e for e in events
            if now.isoformat() <= e.get("start", "") <= end.isoformat()
        ]
        if not upcoming:
            return ToolResult.ok(f"Nenhum evento nos proximos {days} dias.")

        lines = [f"Eventos ({len(upcoming)}):"]
        for e in sorted(upcoming, key=lambda x: x.get("start", "")):
            start = e.get("start", "")[:16]
            lines.append(f"  {start} — {e.get('title', 'sem titulo')}")
            if e.get("location"):
                lines.append(f"    Local: {e['location']}")
        return ToolResult.ok("\n".join(lines))


class CalendarCreateTool(Tool):
    name = "calendar_create"
    description = "Cria um evento no calendario"
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titulo do evento"},
            "start": {"type": "string", "description": "Data/hora inicio (YYYY-MM-DD HH:MM)"},
            "end": {"type": "string", "description": "Data/hora fim (opcional)"},
            "location": {"type": "string", "description": "Local"},
            "notes": {"type": "string", "description": "Notas"},
        },
        "required": ["title", "start"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        title = args.get("title", "").strip()
        start_str = args.get("start", "").strip()
        if not title or not start_str:
            return ToolResult.failure("Titulo e data de inicio obrigatorios.")

        try:
            start = datetime.strptime(start_str, "%Y-%m-%d %H:%M").isoformat()
        except ValueError:
            return ToolResult.failure("Formato de data invalido. Use: YYYY-MM-DD HH:MM")

        end_str = args.get("end", "")
        end = None
        if end_str:
            try:
                end = datetime.strptime(end_str, "%Y-%m-%d %H:%M").isoformat()
            except ValueError:
                pass

        data = _load(state.user_id)
        event = {
            "id": uuid4().hex[:12],
            "title": title,
            "start": start,
            "end": end or start,
            "location": args.get("location", ""),
            "notes": args.get("notes", ""),
        }
        data.setdefault("events", []).append(event)
        _save(state.user_id, data)
        return ToolResult.ok(f"Evento criado: {title} em {start_str}")


class ReminderSetTool(Tool):
    name = "reminder_set"
    description = "Cria um lembrete"
    parameters_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Conteudo do lembrete"},
            "fire_at": {"type": "string", "description": "Quando disparar (YYYY-MM-DD HH:MM)"},
        },
        "required": ["content", "fire_at"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        content = args.get("content", "").strip()
        fire_str = args.get("fire_at", "").strip()
        if not content:
            return ToolResult.failure("Conteudo do lembrete vazio.")
        try:
            fire_at = datetime.strptime(fire_str, "%Y-%m-%d %H:%M").isoformat()
        except ValueError:
            return ToolResult.failure("Formato de data invalido.")

        data = _load(state.user_id)
        reminder = {
            "id": uuid4().hex[:12],
            "content": content,
            "fire_at": fire_at,
            "fired": False,
            "snoozed_count": 0,
        }
        data.setdefault("reminders", []).append(reminder)
        _save(state.user_id, data)
        return ToolResult.ok(f"Lembrete criado: {content[:80]}")


class ReminderListTool(Tool):
    name = "reminder_list"
    description = "Lista lembretes pendentes"
    parameters_schema = {"type": "object", "properties": {}}

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        data = _load(state.user_id)
        reminders = [r for r in data.get("reminders", []) if not r.get("fired")]
        if not reminders:
            return ToolResult.ok("Nenhum lembrete pendente.")
        lines = ["Lembretes:"]
        now = datetime.now()
        for r in sorted(reminders, key=lambda x: x.get("fire_at", "")):
            fire = r.get("fire_at", "")[:16]
            overdue = " ⚠️ ATRASADO" if r.get("fire_at", "") < now.isoformat() else ""
            lines.append(f"  [{r['id'][:8]}] {fire} — {r['content'][:100]}{overdue}")
        return ToolResult.ok("\n".join(lines))


class ReminderCancelTool(Tool):
    name = "reminder_cancel"
    description = "Cancela um lembrete"
    parameters_schema = {
        "type": "object",
        "properties": {
            "reminder_id": {"type": "string", "description": "ID do lembrete (8 primeiros caracteres)"},
        },
        "required": ["reminder_id"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        rid = args.get("reminder_id", "")
        data = _load(state.user_id)
        reminders = data.get("reminders", [])
        found = None
        for r in reminders:
            if r["id"].startswith(rid):
                found = r
                break
        if not found:
            return ToolResult.failure(f"Lembrete '{rid}' nao encontrado.")
        reminders.remove(found)
        _save(state.user_id, data)
        return ToolResult.ok(f"Lembrete '{found['content'][:80]}' cancelado.")
