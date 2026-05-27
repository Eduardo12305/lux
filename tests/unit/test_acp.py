# tests/unit/test_acp.py

from __future__ import annotations

import json
import pytest

from lux.acp.protocol import (
    ACPDiagnostic,
    ACPFileContext,
    ACPMessageType,
    ACPRequest,
    ACPResponse,
)


def test_acp_request_from_json_basic():
    data = {
        "id": "req_001",
        "type": "request",
        "user_id": "u1",
        "message": "explique esta funcao",
    }
    req = ACPRequest.from_json(data)
    assert req.id == "req_001"
    assert req.message == "explique esta funcao"
    assert req.type == ACPMessageType.REQUEST


def test_acp_request_from_json_with_file():
    data = {
        "id": "req_002",
        "message": "analise",
        "user_id": "u1",
        "open_file": {
            "path": "src/main.rs",
            "language": "rust",
            "content": "fn main() {}",
            "selection": "main()",
            "cursor_line": 1,
            "cursor_column": 4,
        },
    }
    req = ACPRequest.from_json(data)
    assert req.open_file is not None
    assert req.open_file.path == "src/main.rs"
    assert req.open_file.language == "rust"
    assert req.open_file.selection == "main()"


def test_acp_request_from_json_with_diagnostics():
    data = {
        "id": "req_003",
        "message": "corrija erros",
        "user_id": "u1",
        "diagnostics": [
            {
                "severity": "error",
                "message": "unused variable: x",
                "line": 15,
                "column": 5,
                "source": "rustc",
            },
            {
                "severity": "warning",
                "message": "deprecated function",
                "line": 22,
                "column": 1,
            },
        ],
    }
    req = ACPRequest.from_json(data)
    assert len(req.diagnostics) == 2
    assert req.diagnostics[0].severity == "error"
    assert req.diagnostics[0].message == "unused variable: x"
    assert req.diagnostics[1].severity == "warning"


def test_acp_request_from_json_with_workspace():
    data = {
        "id": "req_004",
        "message": "status",
        "user_id": "u1",
        "workspace_path": "/home/user/projeto",
        "conversation_history": [
            {"role": "user", "content": "ola"},
            {"role": "assistant", "content": "oi"},
        ],
    }
    req = ACPRequest.from_json(data)
    assert req.workspace_path == "/home/user/projeto"
    assert len(req.conversation_history) == 2


def test_acp_request_from_json_empty():
    req = ACPRequest.from_json({})
    assert req.id
    assert req.message == ""
    assert req.open_file is None
    assert len(req.diagnostics) == 0


def test_acp_response_to_json():
    resp = ACPResponse(
        id="resp_001",
        type=ACPMessageType.RESPONSE,
        message="resultado",
        status="done",
        tokens_used=150,
    )
    data = resp.to_json()
    assert data["id"] == "resp_001"
    assert data["type"] == "response"
    assert data["message"] == "resultado"
    assert data["status"] == "done"
    assert data["tokens_used"] == 150


def test_acp_response_error():
    resp = ACPResponse(
        id="err_001",
        type=ACPMessageType.ERROR,
        error="falha interna",
    )
    data = resp.to_json()
    assert data["type"] == "error"
    assert data["error"] == "falha interna"


def test_acp_response_with_tool_calls():
    resp = ACPResponse(
        id="resp_tools",
        message="",
        tool_calls=[
            {"id": "tc1", "name": "web_search", "arguments": {"query": "rust"}},
        ],
    )
    data = resp.to_json()
    assert len(data["tool_calls"]) == 1
    assert data["tool_calls"][0]["name"] == "web_search"


def test_acp_file_context_defaults():
    fc = ACPFileContext()
    assert fc.path == ""
    assert fc.language == ""
    assert fc.cursor_line == 0


def test_acp_diagnostic_defaults():
    d = ACPDiagnostic()
    assert d.severity == "error"
    assert d.line == 0


def test_acp_message_types():
    assert ACPMessageType.REQUEST.value == "request"
    assert ACPMessageType.STREAM_CHUNK.value == "stream_chunk"
    assert ACPMessageType.ERROR.value == "error"
