"""Regression tests for truthful dashboard status, models, and chat wiring.

The panel is loaded by file path. Importing ``project_guardian`` executes
GuardianCore, which currently fails before the dashboard can start.
"""

import re
import subprocess
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_socketio")

from tests.dashboard_panel_loader import UIControlPanel, panel_module


def _client(orchestrator):
    panel = UIControlPanel(orchestrator=orchestrator, host="127.0.0.1", port=5999)
    return panel.app.test_client()


def test_status_without_orchestrator_is_not_running():
    response = _client(None).get("/api/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["system"]["running"] is False
    assert data["system"]["initialized"] is False
    assert data["system"]["orchestrator_attached"] is False
    assert data["system"]["uptime"] is None
    assert "error" not in data["system"]
    assert data["loop"]["running"] is False
    assert data["trust"]["average_trust"] is None
    assert isinstance(data["timestamp"], str)


def test_status_ignores_idle_components_and_does_not_invent_trust():
    orchestrator = SimpleNamespace(
        _initialized=False,
        _running=False,
        memory=SimpleNamespace(
            get_memory_state=lambda load_if_needed=False: {
                "memory_loaded": False,
                "memory_count": 0,
            }
        ),
        elysia_loop=SimpleNamespace(
            running=False,
            paused=False,
            task_queue=SimpleNamespace(get_queue_size=lambda: 0),
        ),
        safety=SimpleNamespace(),
        trust=SimpleNamespace(),
    )
    data = _client(orchestrator).get("/api/status").get_json()
    assert data["system"]["running"] is False
    assert data["system"]["initialized"] is False
    assert data["loop"]["running"] is False
    assert data["loop"]["attached"] is True
    assert data["loop"]["queue_size"] == 0
    assert data["memory"]["total_entries"] == 0
    assert data["trust"]["average_trust"] is None
    assert data["trust"]["attached"] is True
    assert data["security"]["policy_loaded"] is True
    assert data["security"]["recent_violations"] is None


def test_status_reports_running_from_explicit_flags():
    orchestrator = SimpleNamespace(
        _initialized=True,
        _running=True,
        start_time=datetime.now() - timedelta(seconds=5),
        elysia_loop=SimpleNamespace(
            running=True,
            paused=False,
            task_queue=SimpleNamespace(get_queue_size=lambda: 2),
        ),
        trust=SimpleNamespace(average_trust=0.4, components=3),
    )
    data = _client(orchestrator).get("/api/status").get_json()
    assert data["system"]["running"] is True
    assert data["system"]["initialized"] is True
    assert data["system"]["uptime"] >= 4
    assert data["loop"]["running"] is True
    assert data["loop"]["queue_size"] == 2
    assert data["trust"]["average_trust"] == 0.4
    assert data["trust"]["components"] == 3


def test_status_running_loop_without_system_flag_is_running():
    orchestrator = SimpleNamespace(
        _initialized=False,
        _running=False,
        elysia_loop=SimpleNamespace(running=True, paused=True, queue_size=1),
    )
    data = _client(orchestrator).get("/api/status").get_json()
    assert data["system"]["running"] is True
    assert data["system"]["initialized"] is False
    assert data["loop"]["running"] is True
    assert data["loop"]["paused"] is True


def test_status_exception_returns_json_instead_of_http_500():
    class Broken:
        @property
        def _initialized(self):
            raise RuntimeError("status collector failed")

    response = _client(Broken()).get("/api/status")
    assert response.status_code == 200
    data = response.get_json()
    assert "status collector failed" in data["system"]["error"]
    assert data["system"]["running"] is False
    assert isinstance(data["timestamp"], str)


def test_ping_identifies_control_panel():
    response = _client(None).get("/api/ping")
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["service"] == "elysia-control-panel"


def test_models_report_configured_name_and_availability(monkeypatch):
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "llama3.2:3b")
    loaded = sys.modules.get("elysia_dashboard_ollama_model_config")
    if loaded is not None:
        loaded.reset_log_flag_for_tests()
    monkeypatch.setattr(
        panel_module,
        "probe_local_ollama",
        lambda timeout=0.8: {
            "reachable": True,
            "models": ["llama3.2:3b", "other:1b"],
            "error": None,
            "endpoint": "http://127.0.0.1:11434/api/tags",
        },
    )
    data = _client(None).get("/api/models").get_json()
    assert data["configured"]["name"] == "llama3.2:3b"
    assert data["configured"]["source"] == "ELYSIA_OLLAMA_MODEL"
    assert data["configured"]["available"] is True
    assert data["available"] == ["llama3.2:3b", "other:1b"]
    assert data["ollama"]["reachable"] is True


def test_models_report_unavailable_when_ollama_is_down(monkeypatch):
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "llama3.2:3b")
    loaded = sys.modules.get("elysia_dashboard_ollama_model_config")
    if loaded is not None:
        loaded.reset_log_flag_for_tests()
    monkeypatch.setattr(
        panel_module,
        "probe_local_ollama",
        lambda timeout=0.8: {
            "reachable": False,
            "models": [],
            "error": "connection refused",
            "endpoint": "http://127.0.0.1:11434/api/tags",
        },
    )
    data = _client(None).get("/api/models").get_json()
    assert data["configured"]["name"] == "llama3.2:3b"
    assert data["configured"]["available"] is False
    assert data["available"] == []
    assert data["ollama"]["reachable"] is False


def test_chat_without_backend_is_actionable(monkeypatch):
    monkeypatch.setattr(
        panel_module,
        "probe_local_ollama",
        lambda timeout=0.8: {
            "reachable": False,
            "models": [],
            "error": "connection refused",
            "endpoint": "http://127.0.0.1:11434/api/tags",
        },
    )
    response = _client(None).post("/api/chat", json={"message": "hello fictional profile"})
    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert body["reply"] is None
    assert "No chat backend is attached" in body["error"]
    assert "No external provider was called" in body["error"]


def test_chat_reaches_fictional_backend():
    class Orchestrator:
        _running = False
        _initialized = False

        def ask_ai(self, message):
            return "FICTIONAL:" + message

    response = _client(Orchestrator()).post("/api/chat", json={"message": "ping-fictional"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["reply"] == "FICTIONAL:ping-fictional"


def test_pause_without_loop_is_a_client_error():
    response = _client(None).post("/api/control/pause")
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_dashboard_javascript_parses_and_does_not_fake_running(tmp_path):
    html = _client(None).get("/").get_data(as_text=True)
    assert "Initializing..." in html
    assert "window.toggleTheme" in html
    assert "id=\"model-configured\"" in html
    assert "markDashboardOffline" in html
    assert "running: true, initialized: true" not in html
    assert "Connected (Limited)" not in html
    scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    assert scripts, "dashboard should include inline JavaScript"
    for index, script in enumerate(scripts):
        path = tmp_path / f"dashboard_{index}.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_probe_refuses_non_loopback_ollama_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://example.com:11434")
    result = panel_module.probe_local_ollama(timeout=0.1)
    assert result["reachable"] is False
    assert result["endpoint"] is None
    assert "not loopback" in result["error"]
