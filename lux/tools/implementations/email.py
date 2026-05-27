# lux/tools/implementations/email.py
import email as _email_lib
import email.message
import imaplib
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from typing import Optional

from lux.agent.state import AgentState, ToolResult
from lux.config import get_config
from lux.tools.base import Tool

logger = logging.getLogger(__name__)


def _imap_connect() -> Optional[imaplib.IMAP4_SSL]:
    config = get_config()
    if not config.email_imap_host or not config.email_address or not config.email_password:
        return None
    try:
        ctx = ssl.create_default_context()
        conn = imaplib.IMAP4_SSL(config.email_imap_host, 993, ssl_context=ctx)
        conn.login(config.email_address, config.email_password)
        return conn
    except Exception as e:
        logger.warning("Falha ao conectar IMAP: %s", e)
        return None


def _smtp_connect() -> Optional[smtplib.SMTP_SSL]:
    config = get_config()
    if not config.email_smtp_host or not config.email_address or not config.email_password:
        return None
    try:
        ctx = ssl.create_default_context()
        conn = smtplib.SMTP_SSL(config.email_smtp_host, 465, context=ctx)
        conn.login(config.email_address, config.email_password)
        return conn
    except Exception as e:
        logger.warning("Falha ao conectar SMTP: %s", e)
        return None


def _check_email_config() -> Optional[str]:
    config = get_config()
    if not config.email_imap_host:
        return "Email nao configurado. Defina LUX_EMAIL_IMAP_HOST, LUX_EMAIL_ADDRESS e LUX_EMAIL_PASSWORD no .env"
    return None


class EmailListTool(Tool):
    name = "email_list"
    description = "Lista emails da inbox"
    timeout_seconds = 30
    parameters_schema = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Max emails", "default": 10},
            "unread_only": {"type": "boolean", "description": "Apenas nao lidos", "default": True},
        },
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        err = _check_email_config()
        if err:
            return ToolResult.failure(err)

        imap = _imap_connect()
        if not imap:
            return ToolResult.failure("Falha ao conectar ao servidor IMAP.")

        try:
            imap.select("INBOX")
            criteria = "UNSEEN" if args.get("unread_only", True) else "ALL"
            _, data = imap.search(None, criteria)
            ids = data[0].split()
            limit = args.get("limit", 10)
            ids = ids[-limit:]

            results = []
            for mid in reversed(ids):
                _, msg_data = imap.fetch(mid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if msg_data and msg_data[0]:
                    raw = msg_data[0][1]
                    msg = _email_lib.message_from_bytes(raw)
                    results.append({
                        "id": mid.decode(),
                        "from": msg.get("From", "?"),
                        "subject": msg.get("Subject", "(sem assunto)"),
                        "date": msg.get("Date", "?"),
                    })

            if not results:
                return ToolResult.ok("Nenhum email encontrado.")

            lines = [f"Emails ({len(results)}):"]
            for m in results:
                lines.append(f"  [{m['id']}] {m['from'][:40]} — {m['subject'][:60]}")
            return ToolResult.ok("\n".join(lines))
        finally:
            imap.logout()


class EmailReadTool(Tool):
    name = "email_read"
    description = "Le um email especifico"
    timeout_seconds = 30
    parameters_schema = {
        "type": "object",
        "properties": {
            "email_id": {"type": "string", "description": "ID do email"},
        },
        "required": ["email_id"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        err = _check_email_config()
        if err:
            return ToolResult.failure(err)

        imap = _imap_connect()
        if not imap:
            return ToolResult.failure("Falha ao conectar IMAP.")

        try:
            imap.select("INBOX")
            _, msg_data = imap.fetch(args["email_id"].encode(), "(RFC822)")
            if not msg_data or not msg_data[0]:
                return ToolResult.failure("Email nao encontrado.")

            raw = msg_data[0][1]
            msg = _email_lib.message_from_bytes(raw)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(errors="replace")[:2000]
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors="replace")[:2000]

            return ToolResult.ok(
                f"De: {msg.get('From', '?')}\n"
                f"Assunto: {msg.get('Subject', '?')}\n"
                f"Data: {msg.get('Date', '?')}\n"
                f"\n{body or '(corpo vazio)'}"
            )
        finally:
            imap.logout()


class EmailSendTool(Tool):
    name = "email_send"
    description = "Envia um email (requer aprovacao)"
    timeout_seconds = 30
    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Destinatario"},
            "subject": {"type": "string", "description": "Assunto"},
            "body": {"type": "string", "description": "Corpo do email"},
        },
        "required": ["to", "subject", "body"],
    }

    def execute(self, args: dict, state: AgentState) -> ToolResult:
        err = _check_email_config()
        if err:
            return ToolResult.failure(err)

        config = get_config()
        smtp = _smtp_connect()
        if not smtp:
            return ToolResult.failure("Falha ao conectar SMTP.")

        try:
            msg = MIMEText(args["body"], "plain", "utf-8")
            msg["From"] = config.email_address
            msg["To"] = args["to"]
            msg["Subject"] = args["subject"]
            smtp.send_message(msg)
            return ToolResult.ok(f"Email enviado para {args['to']}")
        except Exception as e:
            return ToolResult.failure(f"Falha ao enviar: {e}")
        finally:
            smtp.quit()
