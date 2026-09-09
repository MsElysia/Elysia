"""Control panel backend log tailing should prefer current runtime logs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest


def _imports():
    try:
        from project_guardian import ui_control_panel as panel
    except ImportError:
        pytest.skip("UIControlPanel not available")
    return panel


def test_recent_log_payload_prefers_current_backend_log(tmp_path: Path, monkeypatch):
    panel = _imports()
    current = tmp_path / "elysia_unified.log"
    legacy = tmp_path / "organized_project" / "data" / "logs" / "unified_autonomous_system.log"
    current.write_text("2026 current line\n", encoding="utf-8")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("2025 legacy STATUS UPDATE\n", encoding="utf-8")

    monkeypatch.setattr(panel, "CURRENT_BACKEND_LOG_PATH", current)
    monkeypatch.setattr(panel, "SECONDARY_RUNTIME_LOG_PATH", tmp_path / "missing_runtime.log")
    monkeypatch.setattr(panel, "LEGACY_AUTONOMOUS_LOG_PATH", legacy)

    payload = panel._build_recent_log_payload(max_lines=20)

    assert payload["success"] is True
    assert payload["source"]["role"] == "live_backend"
    assert payload["lines"] == ["2026 current line"]
    assert payload["legacy_source"]["exists"] is True


def test_recent_log_payload_labels_legacy_fallback(tmp_path: Path, monkeypatch):
    panel = _imports()
    legacy = tmp_path / "organized_project" / "data" / "logs" / "unified_autonomous_system.log"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("2025 legacy STATUS UPDATE\n", encoding="utf-8")

    monkeypatch.setattr(panel, "CURRENT_BACKEND_LOG_PATH", tmp_path / "missing_current.log")
    monkeypatch.setattr(panel, "SECONDARY_RUNTIME_LOG_PATH", tmp_path / "missing_runtime.log")
    monkeypatch.setattr(panel, "LEGACY_AUTONOMOUS_LOG_PATH", legacy)

    payload = panel._build_recent_log_payload(max_lines=20)

    assert payload["success"] is True
    assert payload["source"]["role"] == "legacy_trial_history"
    assert "legacy trial history" in payload["message"].lower()


def test_logs_recent_endpoint_returns_live_tail(tmp_path: Path, monkeypatch):
    panel = _imports()
    current = tmp_path / "elysia_unified.log"
    current.write_text("\n".join(f"line {i}" for i in range(12)) + "\n", encoding="utf-8")
    monkeypatch.setattr(panel, "CURRENT_BACKEND_LOG_PATH", current)
    monkeypatch.setattr(panel, "SECONDARY_RUNTIME_LOG_PATH", tmp_path / "missing_runtime.log")
    monkeypatch.setattr(panel, "LEGACY_AUTONOMOUS_LOG_PATH", tmp_path / "missing_legacy.log")

    ui = panel.UIControlPanel(orchestrator=Mock())
    ui.app.config["TESTING"] = True
    client = ui.app.test_client()

    response = client.get("/api/logs/recent?lines=10")
    assert response.status_code == 200
    body = response.get_json()
    assert body["source"]["role"] == "live_backend"
    assert body["lines"] == [f"line {i}" for i in range(2, 12)]
