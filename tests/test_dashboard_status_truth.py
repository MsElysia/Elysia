"""
Regression tests for truthful dashboard status reporting.

The dashboard module is loaded by file path so these tests exercise the real
ui_control_panel.py without importing the project_guardian package (whose
__init__ starts the GuardianCore import chain).
"""
import importlib.util
import json
import re
import shutil
import subprocess
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_socketio")

PANEL_PATH = Path(__file__).resolve().parent.parent / "project_guardian" / "ui_control_panel.py"


@pytest.fixture(scope="module")
def panel_module():
    spec = importlib.util.spec_from_file_location("ui_control_panel_under_test", PANEL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _client(panel_module, orchestrator):
    return panel_module.UIControlPanel(orchestrator=orchestrator, host="127.0.0.1", port=5999).app.test_client()


def _loop(running, paused=False):
    return SimpleNamespace(running=running, paused=paused, task_queue=SimpleNamespace(get_queue_size=lambda: 3))


def _orch(**kw):
    base = dict(_initialized=False, _running=False, elysia_loop=None, memory=None, start_time=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_status_without_orchestrator_is_200_and_not_running(panel_module):
    r = _client(panel_module, None).get("/api/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["system"]["running"] is False
    assert data["system"]["orchestrator_available"] is False
    assert data["loop"]["running"] is False


def test_status_without_start_time_is_200(panel_module):
    r = _client(panel_module, _orch(_initialized=True, _running=True, elysia_loop=_loop(True))).get("/api/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["system"]["running"] is True
    assert data["loop"]["queue_size"] == 3


def test_status_with_start_time_reports_uptime(panel_module):
    orch = _orch(_initialized=True, _running=True, start_time=datetime.now() - timedelta(seconds=30))
    data = _client(panel_module, orch).get("/api/status").get_json()
    assert data["system"]["uptime"] >= 29


def test_constructed_components_alone_are_not_running(panel_module):
    orch = _orch(elysia_loop=_loop(False), memory=SimpleNamespace(), start_time=datetime.now())
    data = _client(panel_module, orch).get("/api/status").get_json()
    assert data["system"]["running"] is False
    assert data["loop"]["running"] is False


def test_missing_loop_is_not_reported_running(panel_module):
    data = _client(panel_module, _orch(_initialized=True)).get("/api/status").get_json()
    assert data["system"]["running"] is False
    assert data["loop"]["running"] is False
    assert data["loop"]["available"] is False


def test_trust_comes_from_trust_report(panel_module):
    trust = SimpleNamespace(get_trust_report=lambda: {"total_components": 4, "average_trust": 0.25})
    data = _client(panel_module, _orch(trust=trust)).get("/api/status").get_json()
    assert data["trust"] == {"components": 4, "average_trust": 0.25}


def test_ping_identifies_dashboard(panel_module):
    data = _client(panel_module, None).get("/api/ping").get_json()
    assert data["ok"] is True and data["service"] == "elysia-control-panel"


@pytest.fixture
def fake_ollama():
    models = ["llama3.2:3b", "mistral:latest"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"models": [{"name": m} for m in models]}).encode()
            self.send_response(200 if self.path == "/api/tags" else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_models_reports_installed_configured_model(panel_module, fake_ollama, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", fake_ollama)
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "llama3.2:3b")
    data = _client(panel_module, None).get("/api/models").get_json()
    assert data["ollama_reachable"] is True
    assert data["installed_models"] == ["llama3.2:3b", "mistral:latest"]
    assert data["configured_model"] == "llama3.2:3b"
    assert data["configured_source"] == "env:ELYSIA_OLLAMA_MODEL"
    assert data["configured_model_installed"] is True
    assert data["error"] is None


def test_models_untagged_name_matches_latest(panel_module, fake_ollama, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", fake_ollama)
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "mistral")
    assert _client(panel_module, None).get("/api/models").get_json()["configured_model_installed"] is True


def test_models_flags_configured_model_not_installed(panel_module, fake_ollama, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", fake_ollama)
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "mistral:7b")
    data = _client(panel_module, None).get("/api/models").get_json()
    assert data["configured_model_installed"] is False
    assert "not installed" in data["error"]


def test_models_reports_unreachable_ollama(panel_module, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")
    data = _client(panel_module, None).get("/api/models").get_json()
    assert data["ollama_reachable"] is False
    assert data["installed_models"] == []
    assert "not reachable" in data["error"]


def _rendered_script(panel_module):
    html = _client(panel_module, None).get("/").get_data(as_text=True)
    return "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))


def test_frontend_never_fabricates_running_status(panel_module):
    js = _rendered_script(panel_module)
    assert "running: true" not in js
    assert "Connected (Limited)" not in js
    assert "function markOffline" in js
    assert re.search(r"function markOffline\(reason\) \{[^}]*markMetricsUnknown\(\)", js)
    assert "setInterval(pollStatus" in js


def test_frontend_has_model_status_and_chat_error_handling(panel_module):
    js = _rendered_script(panel_module)
    assert "fetch('/api/models'" in js
    assert "Error (HTTP " in js and "AbortController" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_rendered_javascript_parses(panel_module, tmp_path):
    f = tmp_path / "inline.js"
    f.write_text(_rendered_script(panel_module), encoding="utf-8")
    res = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
