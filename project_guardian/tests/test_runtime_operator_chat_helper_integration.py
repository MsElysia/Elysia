# project_guardian/tests/test_runtime_operator_chat_helper_integration.py
"""RuntimeAPIServer POST /api/chat wired through safe_stack.operator_chat (no real LLMs)."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.conversation_store import ConversationStore


class FakeArchitect:
    def __init__(self):
        self.calls: List[Tuple[str, str]] = []

    def chat(self, message: str, context: str = "general"):
        self.calls.append((message, context))
        return {
            "response": f"architect says: {message[:120]}",
            "context": context,
            "source": "fake_architect",
        }


class FakeProposalSystem:
    def get_proposal(self, proposal_id: str):
        return {
            "proposal_id": proposal_id,
            "title": "Test Proposal",
            "status": "pending",
        }


def _server(
    tmp_path: Path,
    *,
    architect: FakeArchitect | None = None,
    proposal_system: FakeProposalSystem | None = None,
) -> tuple[RuntimeAPIServer, ConversationStore, FakeArchitect | None]:
    store = ConversationStore(tmp_path / "conversations")
    arch = architect if architect is not None else FakeArchitect()
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        architect=arch,
        conversation_store=store,
        proposal_system=proposal_system,
    )
    return server, store, arch


def test_runtime_chat_returns_conversation_id(tmp_path):
    server, _store, _arch = _server(tmp_path)
    client = server._app.test_client()
    resp = client.post("/api/chat", json={"message": "hello", "context": "general"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("conversation_id")
    assert body.get("reply")
    assert body.get("response") == body.get("reply")


def test_runtime_chat_persists_user_and_assistant(tmp_path):
    server, store, _arch = _server(tmp_path)
    client = server._app.test_client()
    cid = "persist-runtime"
    resp = client.post(
        "/api/chat",
        json={"message": "save this", "context": "general", "conversation_id": cid},
    )
    assert resp.status_code == 200
    rows = store.list_messages(cid)
    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "save this"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["content"]


def test_runtime_chat_accepts_existing_conversation_id(tmp_path):
    server, store, _arch = _server(tmp_path)
    cid = "existing-session"
    store.append_message(cid, role="user", content="earlier")
    store.append_message(cid, role="assistant", content="ack")

    client = server._app.test_client()
    resp = client.post(
        "/api/chat",
        json={"message": "follow up", "context": "general", "conversation_id": cid},
    )
    assert resp.status_code == 200
    assert resp.get_json().get("conversation_id") == cid
    rows = store.list_messages(cid)
    assert len(rows) == 4
    assert "earlier" in rows[0]["content"]


def test_runtime_chat_sets_cookie_when_expected(tmp_path):
    server, _store, _arch = _server(tmp_path)
    client = server._app.test_client()
    resp = client.post("/api/chat", json={"message": "cookie please", "context": "general"})
    assert resp.status_code == 200
    cookie = resp.headers.get("Set-Cookie") or ""
    assert "elysia_conversation_id=" in cookie
    body = resp.get_json()
    assert body.get("conversation_id") in cookie


def test_proposal_branch_unchanged_and_not_using_helper(tmp_path, monkeypatch):
    server, store, _arch = _server(tmp_path, proposal_system=FakeProposalSystem())
    helper_calls: list[str] = []

    def _spy(*args, **kwargs):
        helper_calls.append("called")
        raise AssertionError("helper must not run for proposal context")

    monkeypatch.setattr(
        "elysia.api.server.run_operator_chat_turn",
        _spy,
    )
    client = server._app.test_client()
    resp = client.post(
        "/api/chat",
        json={"message": "status?", "context": "proposal:prop-123"},
    )
    assert resp.status_code == 200
    assert not helper_calls
    body = resp.get_json()
    assert "Proposal" in body.get("response", "")
    assert body.get("context") == "proposal:prop-123"
    assert store.list_messages("control_panel") == []


def test_brain_metadata_in_response_when_trace_enabled(tmp_path, monkeypatch):
    server, _store, _arch = _server(tmp_path)

    def _fake_brain(message: str, http_context: str) -> Dict[str, Any]:
        return {
            "brain_trace_enabled": True,
            "brain_trace_id": "dry-run-1",
            "brain_dry_run": True,
            "brain_transition_count": 2,
        }

    monkeypatch.setattr(server, "_maybe_run_brain_operator_chat_trace", _fake_brain)
    client = server._app.test_client()
    resp = client.post("/api/chat", json={"message": "trace me", "context": "general"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("brain_trace_enabled") is True
    assert body.get("brain_trace_id") == "dry-run-1"
    assert body.get("brain_dry_run") is True


def test_brain_trace_failure_does_not_break_chat(tmp_path, monkeypatch):
    server, store, _arch = _server(tmp_path)

    def _boom(_message: str, _ctx: str) -> Dict[str, Any]:
        raise RuntimeError("trace exploded")

    monkeypatch.setattr(server, "_maybe_run_brain_operator_chat_trace", _boom)
    client = server._app.test_client()
    resp = client.post(
        "/api/chat",
        json={"message": "still works", "context": "general", "conversation_id": "brain-fail"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("reply")
    assert body.get("brain_trace_error") == "trace exploded"
    rows = store.list_messages("brain-fail")
    assert len(rows) == 2


def test_runtime_response_compatible_with_architect_delegation(tmp_path):
    architect = FakeArchitect()
    server, _store, _arch = _server(tmp_path, architect=architect)
    client = server._app.test_client()
    resp = client.post(
        "/api/chat",
        json={"message": "let elysia speak", "context": "general"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["response"] == "architect says: let elysia speak"
    assert body["source"] == "fake_architect"
    assert architect.calls == [("let elysia speak", "general")]


def test_composed_prompt_passed_when_history_exists(tmp_path):
    architect = FakeArchitect()
    server, store, _arch = _server(tmp_path, architect=architect)
    cid = "history-compose"
    store.append_message(cid, role="user", content="prior question")
    store.append_message(cid, role="assistant", content="prior answer")

    client = server._app.test_client()
    resp = client.post(
        "/api/chat",
        json={"message": "follow up", "context": "general", "conversation_id": cid},
    )
    assert resp.status_code == 200
    assert architect.calls
    composed, ctx = architect.calls[-1]
    assert ctx == "general"
    assert "prior question" in composed
    assert "Current user message:" in composed
    assert "follow up" in composed


def test_echo_fallback_when_no_architect(tmp_path):
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        architect=None,
        conversation_store=ConversationStore(tmp_path / "conversations"),
    )
    client = server._app.test_client()
    resp = client.post("/api/chat", json={"message": "ping", "context": "general"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("response") == "Echo: ping"
    assert body.get("status") == "accepted"


def test_ui_control_panel_chat_route_uses_helper():
    import project_guardian.ui_control_panel as panel

    src = inspect.getsource(panel.UIControlPanel._handle_control_panel_operator_chat)
    assert "run_operator_chat_turn" in src


def test_no_autonomy_or_live_execution_tokens_in_runtime_chat_handler():
    import elysia.api.server as srv

    src = inspect.getsource(srv.RuntimeAPIServer._handle_runtime_general_chat)
    lowered = src.lower()
    for token in (
        "run_autonomous_cycle",
        "operator_chat_live_execution",
        "subprocess",
        "implementer.run_for_proposal",
    ):
        assert token not in lowered, f"unexpected token in runtime general chat: {token}"
