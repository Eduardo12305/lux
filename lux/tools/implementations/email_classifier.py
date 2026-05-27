# lux/tools/implementations/email_classifier.py
# Módulo: Tools — Classificador Inteligente de E-mails
# Dependências: config.py, memory/manager.py
# Status: IMPLEMENTADO
# Notas: Categoriza e resume e-mails com base em interesses do usuário.
#   Integra com o plano_agente_inteligente.md — Módulo 2.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from lux.config import get_config
from lux.constants import LUX_HOME

logger = logging.getLogger(__name__)

EMAIL_INDEX_PATH = LUX_HOME / "email_index.json"


@dataclass
class EmailEntry:
    id: str
    subject: str
    sender: str
    date: str
    category: str = "geral"
    summary: str = ""
    priority: str = "normal"
    read: bool = False
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "sender": self.sender,
            "date": self.date,
            "category": self.category,
            "summary": self.summary,
            "priority": self.priority,
            "read": self.read,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EmailEntry:
        return cls(
            id=d.get("id", ""),
            subject=d.get("subject", ""),
            sender=d.get("sender", ""),
            date=d.get("date", ""),
            category=d.get("category", "geral"),
            summary=d.get("summary", ""),
            priority=d.get("priority", "normal"),
            read=d.get("read", False),
            fetched_at=d.get("fetched_at", ""),
        )


@dataclass
class EmailIndex:
    entries: list[EmailEntry] = field(default_factory=list)
    last_fetch: str = ""
    categories: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "last_fetch": self.last_fetch,
            "categories": self.categories,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EmailIndex:
        entries = [EmailEntry.from_dict(e) for e in d.get("entries", [])]
        return cls(
            entries=entries,
            last_fetch=d.get("last_fetch", ""),
            categories=d.get("categories", {}),
        )


class InterestParser:
    """Parser da configuração EMAIL_INTERESTS: nome1:kw1,kw2; nome2:kw3"""

    @staticmethod
    def parse(raw: str) -> dict[str, list[str]]:
        categories: dict[str, list[str]] = {}
        if not raw.strip():
            return categories
        for segment in raw.split(";"):
            segment = segment.strip()
            if ":" not in segment:
                continue
            name, _, keywords = segment.partition(":")
            name = name.strip().lower()
            categories[name] = [
                kw.strip().lower()
                for kw in keywords.split(",")
                if kw.strip()
            ]
        return categories


class EmailClassifier:
    """Classifica e resume e-mails por categoria de interesse."""

    def __init__(self):
        config = get_config()
        self._enabled = config.email_classifier_enabled
        self._fetch_limit = config.email_fetch_limit
        self._interests = InterestParser.parse(config.email_interests)
        self._index: Optional[EmailIndex] = None

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def interests(self) -> dict[str, list[str]]:
        return self._interests

    @property
    def index(self) -> EmailIndex:
        if self._index is None:
            self._index = self._load_index()
        return self._index

    def classify(self, subject: str, body: str = "", sender: str = "") -> str:
        text = f"{subject} {body} {sender}".lower()
        best_category = "geral"
        best_score = 0

        for category, keywords in self._interests.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    def determine_priority(self, subject: str, body: str = "", sender: str = "") -> str:
        text = f"{subject} {body}".lower()
        urgent_keywords = {
            "urgente", "asap", "prazo", "hoje", "atenção",
            "importante", "alerta", "crítico",
        }
        if any(kw in text for kw in urgent_keywords):
            return "alta"
        return "normal"

    def index_emails(self, emails: list[dict]) -> EmailIndex:
        index = EmailIndex(
            last_fetch=datetime.now(timezone.utc).isoformat(),
        )

        for email in emails[:self._fetch_limit]:
            subject = email.get("subject", "")
            body = email.get("body", "")
            sender = email.get("from", "")
            category = self.classify(subject, body, sender)
            priority = self.determine_priority(subject, body, sender)

            entry = EmailEntry(
                id=email.get("id", ""),
                subject=subject,
                sender=sender,
                date=email.get("date", ""),
                category=category,
                summary=self._summarize(subject, body),
                priority=priority,
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )
            index.entries.append(entry)

        for cat in self._interests:
            index.categories[cat] = [
                e.id for e in index.entries if e.category == cat
            ]

        self._index = index
        self._save_index(index)
        logger.info(
            "Classificação concluída: %d e-mails em %d categorias",
            len(index.entries), len(self._interests),
        )
        return index

    def get_by_category(self, category: str) -> list[EmailEntry]:
        cat = category.lower()
        return [e for e in self.index.entries if e.category == cat]

    def get_high_priority(self) -> list[EmailEntry]:
        return [e for e in self.index.entries if e.priority == "alta"]

    def get_unread(self) -> list[EmailEntry]:
        return [e for e in self.index.entries if not e.read]

    def query(self, text: str) -> list[EmailEntry]:
        q = text.lower()
        results = []
        for e in self.index.entries:
            if (q in e.subject.lower() or
                q in e.sender.lower() or
                q in e.summary.lower() or
                q in e.category.lower()):
                results.append(e)
        return results

    def _summarize(self, subject: str, body: str) -> str:
        if not body:
            return subject[:200]
        clean = body.replace("\r", " ").replace("\n", " ").strip()
        if len(clean) <= 200:
            return clean
        return clean[:197] + "..."

    def _load_index(self) -> EmailIndex:
        if EMAIL_INDEX_PATH.exists():
            try:
                data = json.loads(EMAIL_INDEX_PATH.read_text())
                return EmailIndex.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                logger.warning("Índice de e-mails corrompido, recriando")
        return EmailIndex()

    def _save_index(self, index: EmailIndex):
        EMAIL_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        EMAIL_INDEX_PATH.write_text(
            json.dumps(index.to_dict(), ensure_ascii=False, indent=2)
        )


class EmailQueryTool:
    """Ferramenta para consultar e-mails classificados."""

    name = "email_query"
    description = (
        "Consulta e-mails classificados por categoria, prioridade ou termo de busca. "
        "Útil para perguntas como 'tem alguma vaga nova?', 'e-mails importantes?', "
        "'resumo dos e-mails de hoje'."
    )

    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termo de busca ou pergunta sobre e-mails",
            },
            "category": {
                "type": "string",
                "description": "Filtrar por categoria (ex: vagas de emprego, tecnologia)",
            },
            "only_unread": {
                "type": "boolean",
                "description": "Apenas e-mails não lidos",
            },
            "only_high_priority": {
                "type": "boolean",
                "description": "Apenas e-mails de alta prioridade",
            },
        },
        "required": [],
    }

    def __init__(self, classifier: Optional[EmailClassifier] = None):
        self._classifier = classifier or EmailClassifier()

    def execute(self, args: dict, state) -> "ToolResult":
        from lux.agent.state import ToolResult

        if not self._classifier.is_enabled:
            return ToolResult.ok(
                "Classificador de e-mails não está habilitado. "
                "Configure EMAIL_CLASSIFIER_ENABLED=true e EMAIL_INTERESTS no .env"
            )

        query = args.get("query", "").strip()
        category = args.get("category", "").strip()
        only_unread = args.get("only_unread", False)
        only_high = args.get("only_high_priority", False)

        entries = self._classifier.index.entries

        if category:
            entries = [e for e in entries if e.category == category.lower()]
        if query:
            entries = self._classifier.query(query)
        if only_unread:
            entries = [e for e in entries if not e.read]
        if only_high:
            entries = [e for e in entries if e.priority == "alta"]

        if not entries:
            return ToolResult.ok("Nenhum e-mail encontrado com esses filtros.")

        lines = [f"E-mails ({len(entries)}):"]
        for e in entries[:15]:
            priority_mark = "⚠️ " if e.priority == "alta" else ""
            unread_mark = "📩 " if not e.read else ""
            lines.append(
                f"  {priority_mark}{unread_mark}[{e.category}] {e.subject[:80]}"
            )
            lines.append(f"     {e.sender} — {e.date[:10]}")

        return ToolResult.ok("\n".join(lines))
