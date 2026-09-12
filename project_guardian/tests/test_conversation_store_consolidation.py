from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.conversation_store import ConversationStore, reset_default_conversation_store_for_tests


class FakeArchitect:
    def __init__(self):
        self.calls = []

    def chat(self, message, context="general"):
        self.calls.append((message, context))
        return {"response": f"ok:{message}", "context": context, "source": "fake"}


@pytest.fixture(autouse=True)
def _reset_store():
    reset_default_conversation_store_for_tests()
    yield
    reset_default_conversation_store_for_tests()


@pytest.fixture
def disabled_brain(monkeypatch, tmp_path: Path):
    cfg = BrainPipelineConfig(
        enabled=False,
        dry_run=True,
        use_think_decide_act=True,
        trace_path=tmp_path / "brain_trace.json",
        entrypoints={
            "operator_chat": False,
            "operator_chat_live_execution": False,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": False,
        },
    )
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda: cfg)


def _server(tmp_path: Path, *, architect=None):
    store = ConversationStore(tmp_path / "conversations")
    arch = architect or FakeArchitect()
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        architect=arch,
        conversation_store=store,
    )
    return server, arch, store


def test_canonical_import_works():
    from project_guardian.conversation_store import ConversationStore

    assert ConversationStore.__name__ == "ConversationStore"


def test_elysia_api_conversation_store_is_shim_only_and_same_identity():
    import elysia.api.conversation_store as shim
    import project_guardian.conversation_store as canonical

    assert shim.ConversationStore is canonical.ConversationStore
    assert shim.redact_chat_text is canonical.redact_chat_text
    assert shim.sanitize_conversation_id is canonical.sanitize_conversation_id

    source = Path(shim.__file__).read_text(encoding="utf-8")
    assert "class ConversationStore" not in source
    assert "def append_message" not in source
    assert "project_guardian.conversation_store" in source


def test_runtime_api_server_uses_canonical_store_import():
    import elysia.api.server as server_module

    source = inspect.getsource(server_module)
    assert "project_guardian.conversation_store" in source
    assert "elysia.api.conversation_store" not in source


def test_api_chat_returns_conversation_id(disabled_brain, tmp_path: Path):
    server, _arch, _store = _server(tmp_path)

    response = server._app.test_client().post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200
    assert response.get_json()["conversation_id"]


def test_api_chat_appends_to_existing_conversation_id(disabled_brain, tmp_path: Path):
    server, arch, store = _server(tmp_path)
    client = server._app.test_client()

    client.post("/api/chat", json={"conversation_id": "same", "message": "first"})
    response = client.post("/api/chat", json={"conversation_id": "same", "message": "second"})

    assert response.status_code == 200
    assert response.get_json()["conversation_id"] == "same"
    rows = store.list_messages("same", limit=20)
    assert [row["role"] for row in rows] == ["user", "assistant", "user", "assistant"]
    assert rows[0]["content"] == "first"
    assert rows[2]["content"] == "second"
    assert "Recent operator conversation" in arch.calls[-1][0]
    assert "User: first" in arch.calls[-1][0]


def test_new_store_instance_reloads_previous_jsonl_messages(tmp_path: Path):
    first = ConversationStore(tmp_path / "conversations")
    first.append_message("reload", role="user", content="persist me")

    second = ConversationStore(tmp_path / "conversations")
    rows = second.list_messages("reload", limit=10)

    assert len(rows) == 1
    assert rows[0]["content"] == "persist me"


def test_api_conversations_list_returns_metadata_not_raw_dump(disabled_brain, tmp_path: Path):
    server, _arch, store = _server(tmp_path)
    store.append_message("metadata", role="user", content="raw content that should not be dumped")

    response = server._app.test_client().get("/api/conversations")

    assert response.status_code == 200
    item = response.get_json()["conversations"][0]
    assert item["conversation_id"] == "metadata"
    assert "message_count" in item
    assert "content" not in item
    assert "raw content that should not be dumped" not in json.dumps(item)


def test_api_conversation_get_returns_sanitized_messages(disabled_brain, tmp_path: Path):
    server, _arch, store = _server(tmp_path)
    store.append_message("safe", role="user", content="token=abc123 Authorization: Bearer bearer-secret")

    response = server._app.test_client().get("/api/conversations/safe")

    assert response.status_code == 200
    body = response.get_json()
    text = json.dumps(body)
    assert body["messages"][0]["content"].count("[REDACTED]") >= 2
    assert "abc123" not in text
    assert "bearer-secret" not in text


def test_api_conversation_delete_removes_conversation(disabled_brain, tmp_path: Path):
    server, _arch, store = _server(tmp_path)
    store.append_message("delete-me", role="user", content="temporary")

    response = server._app.test_client().delete("/api/conversations/delete-me")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert store.list_messages("delete-me", limit=10) == []


def test_secrets_and_full_brain_tda_trace_fields_are_not_persisted(disabled_brain, tmp_path: Path):
    server, _arch, store = _server(tmp_path)
    server._maybe_run_brain_operator_chat_trace = lambda _message, _context: {
        "brain_trace_enabled": True,
        "brain_trace_id": "trace-ok",
        "brain_raw_trace": {"secret": "raw brain trace"},
        "think_decide_act_trace": {"secret": "raw tda trace"},
        "unified_export": {"secret": "raw export"},
    }

    response = server._app.test_client().post(
        "/api/chat",
        json={
            "conversation_id": "redacted",
            "message": "api_key=abc123 password=hunter2 sk-12345678901234567890",
        },
    )

    assert response.status_code == 200
    raw = (store.base_dir / "redacted.jsonl").read_text(encoding="utf-8")
    for secret in (
        "abc123",
        "hunter2",
        "sk-12345678901234567890",
        "raw brain trace",
        "raw tda trace",
        "raw export",
    ):
        assert secret not in raw
    assert "trace-ok" in raw


def test_control_panel_template_has_conversation_id_localstorage_and_history_reload():
    from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE

    assert "elysia_control_panel_conversation_id" in CONTROL_PANEL_TEMPLATE
    assert "getApiChatConversationId" in CONTROL_PANEL_TEMPLATE
    assert "setApiChatConversationId" in CONTROL_PANEL_TEMPLATE
    assert "refreshApiChatHistory" in CONTROL_PANEL_TEMPLATE
    assert "conversation_id" in CONTROL_PANEL_TEMPLATE
