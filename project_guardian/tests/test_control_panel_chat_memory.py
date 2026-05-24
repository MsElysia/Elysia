from __future__ import annotations

import json
from pathlib import Path

import pytest


class FakeUnifiedSystem:
    def __init__(self):
        self.calls = []

    def chat_with_llm(self, message):
        self.calls.append(message)
        return f"reply-{len(self.calls)}", ""


class FakeMemory:
    def __init__(self):
        self.calls = []

    def remember(self, thought, category="general", priority=0.5, metadata=None):
        self.calls.append(
            {
                "thought": thought,
                "category": category,
                "priority": priority,
                "metadata": metadata or {},
            }
        )


class FakeOrchestrator:
    def __init__(self, conversation_dir: Path):
        self._unified_system = FakeUnifiedSystem()
        self.memory = FakeMemory()
        self.control_panel_chat_history_path = conversation_dir.parent / "legacy_chat_history.json"
        self.conversation_store_dir = conversation_dir


def _panel(conversation_dir: Path):
    try:
        from project_guardian.ui_control_panel import UIControlPanel
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    orch = FakeOrchestrator(conversation_dir)
    return UIControlPanel(orch), orch


def test_control_panel_chat_remembers_prior_turns_in_prompt(tmp_path: Path):
    panel, orch = _panel(tmp_path / "conversations")

    with panel.app.test_client() as client:
        first = client.post("/api/chat", json={"message": "My preferred launch color is teal."})
        second = client.post("/api/chat", json={"message": "What launch color did I mention?"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert orch._unified_system.calls[0] == "My preferred launch color is teal."
    assert "Recent operator conversation" in orch._unified_system.calls[1]
    assert "User: My preferred launch color is teal." in orch._unified_system.calls[1]
    assert "Assistant: reply-1" in orch._unified_system.calls[1]
    assert "Current user message:" in orch._unified_system.calls[1]

    body = second.get_json()
    assert body["success"] is True
    assert body["conversation_id"] == "control_panel"
    assert [row["role"] for row in body["history"]] == ["user", "assistant", "user", "assistant"]
    assert len(orch.memory.calls) == 2
    assert orch.memory.calls[-1]["category"] == "conversation"


def test_control_panel_chat_history_is_persisted_and_reloaded(tmp_path: Path):
    conversation_dir = tmp_path / "conversations"
    panel, _orch = _panel(conversation_dir)

    with panel.app.test_client() as client:
        client.post("/api/chat", json={"message": "Remember this dashboard note."})

    assert (conversation_dir / "control_panel.jsonl").exists()

    reloaded_panel, _reloaded = _panel(conversation_dir)
    with reloaded_panel.app.test_client() as client:
        response = client.get("/api/chat/history")

    body = response.get_json()
    assert body["success"] is True
    assert body["history"][0]["content"] == "Remember this dashboard note."
    assert body["history"][1]["content"] == "reply-1"


def test_control_panel_chat_history_redacts_persisted_secrets(tmp_path: Path):
    conversation_dir = tmp_path / "conversations"
    panel, orch = _panel(conversation_dir)

    def secret_reply(_message):
        orch._unified_system.calls.append(_message)
        return "Authorization: Bearer server-token token=reply-token", ""

    orch._unified_system.chat_with_llm = secret_reply

    with panel.app.test_client() as client:
        response = client.post(
            "/api/chat",
            json={
                "message": (
                    "api_key=abc123 password=hunter2 sk-12345678901234567890 "
                    "Authorization: Bearer user-token"
                )
            },
        )

    assert response.status_code == 200
    raw_path = conversation_dir / "control_panel.jsonl"
    raw = raw_path.read_text(encoding="utf-8")
    for secret in ("abc123", "hunter2", "sk-12345678901234567890", "user-token", "server-token", "reply-token"):
        assert secret not in raw

    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert rows[0]["content"].count("[REDACTED]") >= 3
    assert "[REDACTED]" in rows[1]["content"]


def test_control_panel_template_loads_and_renders_chat_history():
    try:
        from project_guardian.ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    assert "renderApiChatHistory" in CONTROL_PANEL_TEMPLATE
    assert "refreshApiChatHistory" in CONTROL_PANEL_TEMPLATE
    assert "/api/chat/history" in CONTROL_PANEL_TEMPLATE
