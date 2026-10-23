"""Regression tests for truthful dashboard status, ping, models, and chat errors."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PANEL_PATH = PROJECT_ROOT / "project_guardian" / "ui_control_panel.py"


def _load_panel_module():
    """Load ui_control_panel.py without importing project_guardian.__init__."""
    name = "ui_control_panel_status_truth"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, PANEL_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def panel_mod():
    try:
        import flask  # noqa: F401
        import flask_socketio  # noqa: F401
    except ImportError:
        pytest.skip("Flask/Flask-SocketIO not installed")
    return _load_panel_module()


@pytest.fixture
def client_no_orch(panel_mod):
    panel_mod.reset_dashboard_guard()
    panel = panel_mod.UIControlPanel(orchestrator=None, host="127.0.0.1", port=5000)
    return panel, panel.app.test_client()


def test_ping_identifies_control_panel(client_no_orch):
    panel, client = client_no_orch
    response = client.get("/api/ping")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["service"] == "elysia-control-panel"
    assert data["orchestrator"] is False
    assert response.headers.get("X-Elysia-Service") == "elysia-control-panel"
    assert response.headers.get("X-Elysia-Panel") == panel._instance_id


def test_status_no_orchestrator_returns_json_not_running(client_no_orch):
    """PR #149 datetime UnboundLocalError must not 500 or claim Running."""
    _panel, client = client_no_orch
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data["system"]["running"] is False
    assert data["system"]["initialized"] is False
    assert data["system"].get("error") == "Orchestrator not available"
    assert data["loop"]["running"] is False
    assert "timestamp" in data
    assert data["backend"]["service"] == "elysia-control-panel"
    assert data["backend"]["orchestrator"] is False
    assert "models" in data


def test_status_does_not_report_running_from_core_presence(panel_mod):
    orch = SimpleNamespace(
        _initialized=False,
        _running=False,
        start_time=None,
        operational_stats={},
        memory=object(),
        elysia_loop=None,
        runtime_loop=None,
        module_registry=None,
        safety=None,
        trust=None,
    )
    panel_mod.reset_dashboard_guard()
    panel = panel_mod.UIControlPanel(orchestrator=orch, host="127.0.0.1", port=5000)
    data = panel.app.test_client().get("/api/status").get_json()
    assert data["system"]["running"] is False
    assert data["system"]["initialized"] is True
    assert data["loop"]["running"] is False


def test_status_running_only_when_loop_or_flag(panel_mod):
    loop = SimpleNamespace(running=True, paused=False, task_queue=None, queue_size=0)
    orch = SimpleNamespace(
        _initialized=True,
        _running=True,
        start_time=None,
        operational_stats={},
        memory=None,
        elysia_loop=loop,
        runtime_loop=None,
        module_registry=None,
        safety=None,
        trust=None,
    )
    panel_mod.reset_dashboard_guard()
    panel = panel_mod.UIControlPanel(orchestrator=orch, host="127.0.0.1", port=5000)
    data = panel.app.test_client().get("/api/status").get_json()
    assert data["system"]["running"] is True
    assert data["loop"]["running"] is True


def test_models_endpoint_reports_configured_local_model(client_no_orch):
    _panel, client = client_no_orch
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.get_json()
    names = [m.get("name") for m in data.get("configured") or []]
    assert "mistral:7b" in names or names  # config default or env override
    assert data["reachable"] in (True, False)
    if not data["reachable"]:
        assert data.get("error")


def test_chat_without_backend_is_actionable(client_no_orch):
    _panel, client = client_no_orch
    response = client.post("/api/chat", json={"message": "Fictional operator Nora asks for a haiku about river stones."})
    assert response.status_code == 400
    data = response.get_json()
    assert data.get("success") is False
    assert data.get("reply") is None
    assert "No chat backend available" in (data.get("error") or "")
    assert "models" in data


def test_chat_uses_local_ask_ai_when_present(panel_mod):
    orch = SimpleNamespace(
        _initialized=True,
        _running=False,
        start_time=None,
        ask_ai=MagicMock(return_value="Nora's river-stone haiku: still water, quiet stones."),
        _unified_system=None,
    )
    panel_mod.reset_dashboard_guard()
    panel = panel_mod.UIControlPanel(orchestrator=orch, host="127.0.0.1", port=5000)
    response = panel.app.test_client().post(
        "/api/chat",
        json={"message": "Fictional operator Nora asks for a haiku about river stones."},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "river-stone" in data["reply"]
    orch.ask_ai.assert_called_once()


def test_homepage_js_has_no_syntax_error_and_no_fake_running(client_no_orch):
    _panel, client = client_no_orch
    html = client.get("/").get_data(as_text=True)
    assert "Initializing..." in html
    assert "toggleTheme" in html
    assert "applyDisconnectedStatus" in html
    assert "running: true, initialized: true" not in html
    assert "Connected (Limited)" not in html
    scripts = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, flags=re.S)
    assert scripts
    source = "\n".join(scripts)
    # Balanced braces/parens is a cheap syntax canary; node --check is used in live verification.
    assert source.count("{") == source.count("}")
    assert source.count("(") == source.count(")")
    assert "controller.abort()" in source  # chat/status timeouts exist
    assert "Chat timed out after 20s" in source
