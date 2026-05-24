# project_guardian/tests/test_control_panel_legacy_history_retirement.py
"""Legacy control_panel_chat_history.json is import-only; ConversationStore is canonical."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from project_guardian.conversation_store import (
    ConversationStore,
    legacy_import_marker_path,
)
from project_guardian.tests.test_control_panel_chat_memory import _panel


def _legacy_payload(session_id: str = "control_panel", *, secret: str = "hello") -> dict:
    return {
        "sessions": {
            session_id: [
                {
                    "role": "user",
                    "content": secret,
                    "timestamp": "2020-01-01T00:00:00Z",
                },
                {"role": "assistant", "content": "ack", "created_at": "2020-01-01T00:00:01Z"},
            ]
        }
    }


def test_new_chat_writes_canonical_not_legacy(tmp_path: Path):
    conv_dir = tmp_path / "conversations"
    legacy = tmp_path / "control_panel_chat_history.json"
    panel, _orch = _panel(conv_dir)
    panel._legacy_chat_history_path = legacy

    with panel.app.test_client() as client:
        r = client.post("/api/chat", json={"message": "persist me"})
    assert r.status_code == 200
    assert (conv_dir / "control_panel.jsonl").exists()
    assert not legacy.exists()


def test_history_reload_uses_conversation_store(tmp_path: Path):
    conv_dir = tmp_path / "conversations"
    panel, _orch = _panel(conv_dir)

    with panel.app.test_client() as client:
        client.post("/api/chat", json={"message": "note for reload"})
        panel2, _ = _panel(conv_dir)
        resp = panel2.app.test_client().get("/api/chat/history")

    body = resp.get_json()
    assert body["success"] is True
    assert body["history"][0]["content"] == "note for reload"


def test_legacy_json_imported_once(tmp_path: Path):
    conv_dir = tmp_path / "conversations"
    legacy = tmp_path / "legacy_chat_history.json"
    legacy.write_text(json.dumps(_legacy_payload()), encoding="utf-8")
    before = legacy.read_bytes()

    panel, _ = _panel(conv_dir)
    panel._legacy_chat_history_path = legacy
    with panel.app.test_client() as client:
        client.get("/api/chat/history")

    assert legacy.read_bytes() == before
    assert legacy_import_marker_path(conv_dir).exists()
    rows = ConversationStore(conv_dir).list_messages("control_panel", limit=10)
    assert len(rows) >= 2
    assert rows[0]["content"] == "hello"


def test_import_marker_prevents_repeat_import(tmp_path: Path):
    conv_dir = tmp_path / "conversations"
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(_legacy_payload(secret="first")), encoding="utf-8")
    store = ConversationStore(conv_dir)
    assert store.import_legacy_control_panel_json(legacy) >= 1

    legacy.write_text(json.dumps(_legacy_payload(secret="second-wave")), encoding="utf-8")
    assert store.import_legacy_control_panel_json(legacy) == 0
    rows = store.list_messages("control_panel", limit=10)
    assert all("second-wave" not in r["content"] for r in rows)


def test_legacy_import_redacts_secrets(tmp_path: Path):
    conv_dir = tmp_path / "conversations"
    legacy = tmp_path / "legacy.json"
    secret = "api_key=supersecret1234567890"
    legacy.write_text(json.dumps(_legacy_payload(secret=secret)), encoding="utf-8")
    store = ConversationStore(conv_dir)
    store.import_legacy_control_panel_json(legacy)
    raw = (conv_dir / "control_panel.jsonl").read_text(encoding="utf-8")
    assert "supersecret1234567890" not in raw
    assert "[REDACTED]" in raw


def test_legacy_import_preserves_timestamps(tmp_path: Path):
    conv_dir = tmp_path / "conversations"
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(_legacy_payload()), encoding="utf-8")
    store = ConversationStore(conv_dir)
    store.import_legacy_control_panel_json(legacy)
    rows = store.list_messages("control_panel", limit=10)
    assert rows[0]["created_at"] == "2020-01-01T00:00:00Z"
    assert rows[1]["created_at"] == "2020-01-01T00:00:01Z"


def test_chat_history_for_response_uses_store(tmp_path: Path):
    conv_dir = tmp_path / "conversations"
    panel, _ = _panel(conv_dir)
    store = ConversationStore(conv_dir)
    store.append_message("control_panel", role="user", content="from store")
    hist = panel._chat_history_for_response("control_panel")
    assert hist and hist[0]["content"] == "from store"


def test_legacy_not_reread_after_marker(tmp_path: Path, monkeypatch):
    conv_dir = tmp_path / "conversations"
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(_legacy_payload()), encoding="utf-8")
    panel, _ = _panel(conv_dir)
    panel._legacy_chat_history_path = legacy

    reads = {"n": 0}
    real_read = Path.read_text

    def counting_read(self, *a, **k):
        if self == legacy:
            reads["n"] += 1
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", counting_read)
    with panel.app.test_client() as client:
        client.get("/api/chat/history")
        client.get("/api/chat/history")
    assert reads["n"] == 1


def test_no_subprocess_on_chat(tmp_path: Path, monkeypatch):
    conv_dir = tmp_path / "conversations"
    panel, _ = _panel(conv_dir)

    def boom(*a, **k):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr("subprocess.run", boom)
    with panel.app.test_client() as client:
        client.post("/api/chat", json={"message": "safe"})


def test_diagnostic_reports_legacy_and_import_state(tmp_path: Path, monkeypatch):
    conv_dir = tmp_path / "conversations"
    legacy = tmp_path / "control_panel_chat_history.json"
    legacy.write_text(json.dumps(_legacy_payload()), encoding="utf-8")
    monkeypatch.setattr(
        "project_guardian.conversation_store.DEFAULT_CONVERSATIONS_DIR",
        conv_dir,
    )
    diag_path = Path(__file__).resolve().parents[2] / "scripts" / "control_panel_conversation_diagnostic.py"
    spec = importlib.util.spec_from_file_location("cp_conv_diag", diag_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(
        "project_guardian.ui_control_panel.CONTROL_PANEL_CHAT_HISTORY_PATH",
        legacy,
    )
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "CONTROL_PANEL_CHAT_HISTORY_PATH", legacy)
    monkeypatch.setattr(mod, "DEFAULT_CONVERSATIONS_DIR", conv_dir)
    monkeypatch.setattr(
        "project_guardian.conversation_store.DEFAULT_CONVERSATIONS_DIR",
        conv_dir,
    )
    assert mod.main() == 0
    out = buf.getvalue()
    assert "Legacy file exists: True" in out
    assert "Legacy import completed: False" in out
