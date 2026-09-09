"""Runtime /api/chat persistence (no real LLM; isolated conversation store)."""

from __future__ import annotations

from pathlib import Path

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.conversation_store import ConversationStore, reset_default_conversation_store_for_tests


class FakeArchitect:
    def __init__(self):
        self.calls = []

    def chat(self, message, context="general"):
        self.calls.append((message, context))
        return {"response": f"architect says: {message}", "context": context, "source": "fake"}


@pytest.fixture(autouse=True)
def _reset_default_store():
    reset_default_conversation_store_for_tests()
    yield
    reset_default_conversation_store_for_tests()


def _client(tmp_path: Path):
    store = ConversationStore(tmp_path / "conv")
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        architect=FakeArchitect(),
        conversation_store=store,
    )
    return server._app.test_client(), store


def test_chat_returns_conversation_id(tmp_path):
    client, _store = _client(tmp_path)
    r = client.post("/api/chat", json={"message": "hello", "context": "general"})
    assert r.status_code == 200
    body = r.get_json()
    assert "conversation_id" in body
    assert body["response"].startswith("architect says:")


def test_chat_persists_user_and_assistant(tmp_path):
    client, store = _client(tmp_path)
    cid = "myconv"
    r = client.post("/api/chat", json={"message": "first", "context": "general", "conversation_id": cid})
    assert r.status_code == 200
    rows = store.list_messages(cid, limit=20)
    roles = [x["role"] for x in rows]
    assert roles == ["user", "assistant"]


def test_chat_without_conversation_id_still_works(tmp_path):
    client, _store = _client(tmp_path)
    r = client.post("/api/chat", json={"message": "solo", "context": "general"})
    assert r.status_code == 200
    assert r.get_json()["response"]


def test_conversations_list(tmp_path):
    client, store = _client(tmp_path)
    store.append_message("z1", role="user", content="x")
    r = client.get("/api/conversations")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    ids = {c["conversation_id"] for c in data["conversations"]}
    assert "z1" in ids


def test_conversation_get_sanitized(tmp_path):
    client, store = _client(tmp_path)
    store.append_message("safe", role="user", content="Authorization: Bearer supersecretvalue")
    r = client.get("/api/conversations/safe")
    assert r.status_code == 200
    msgs = r.get_json()["messages"]
    assert "supersecretvalue" not in msgs[0]["content"]
    assert "REDACTED" in msgs[0]["content"]


def test_conversations_delete_removes_file(tmp_path):
    client, store = _client(tmp_path)
    store.append_message("gone", role="user", content="x")
    path = store._path("gone")
    assert path.exists()
    r = client.delete("/api/conversations/gone")
    assert r.status_code == 200
    assert r.get_json()["success"] is True
    assert not path.exists()
    assert store.list_messages("gone", limit=5) == []


def test_chat_history_get_matches_store(tmp_path):
    client, _store = _client(tmp_path)
    cid = "hist_a"
    r1 = client.post("/api/chat", json={"message": "one", "context": "general", "conversation_id": cid})
    assert r1.status_code == 200
    r2 = client.get(f"/api/chat/history?conversation_id={cid}")
    assert r2.status_code == 200
    data = r2.get_json()
    assert data["success"] is True
    assert data["conversation_id"] == cid
    assert len(data["history"]) >= 2
    roles = [h["role"] for h in data["history"]]
    assert "user" in roles and "assistant" in roles


def test_chat_history_delete_clears(tmp_path):
    client, store = _client(tmp_path)
    cid = "hist_b"
    client.post("/api/chat", json={"message": "m", "context": "general", "conversation_id": cid})
    r = client.delete("/api/chat/history", json={"conversation_id": cid})
    assert r.status_code == 200
    assert r.get_json()["success"] is True
    assert store.list_messages(cid, limit=5) == []


def test_brain_meta_for_storage_strips_sensitive_keys():
    from elysia.api.server import RuntimeAPIServer

    raw = {
        "brain_trace_enabled": True,
        "brain_trace_id": "abc",
        "brain_trace_path": "/data/runtime/brain_trace.json",
        "think_decide_act_trace": {"n": 1},
        "brain_transition_count": 3,
    }
    out = RuntimeAPIServer._brain_meta_for_storage(raw)
    assert out.get("brain_trace_enabled") is True
    assert out.get("brain_trace_id") == "abc"
    assert "brain_trace_path" not in out
    assert "think_decide_act_trace" not in out
    assert out.get("brain_transition_count") == 3
