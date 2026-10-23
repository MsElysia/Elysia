"""Regression tests for Elysia dashboard truthfulness (2026-10-23 acceptance).

Covers PR #149-class defects in project_guardian/ui_control_panel.py:
- /api/status HTTP 500 from a function-local ``datetime`` import shadowing
- false "Running" when only components/memory objects exist
- missing /api/models, chat-unavailable status code, JS fabricated Running

The module is loaded directly from file so tests do not require the heavy
project_guardian package ``__init__`` dependency chain.
"""
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ui_control_panel_under_test", ROOT / "project_guardian" / "ui_control_panel.py"
)
uicp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uicp)
UIControlPanel = uicp.UIControlPanel


class IdleOrchestrator:
    """Constructed components, but nothing is running."""

    _initialized = False
    _running = False
    start_time = None
    operational_stats = {}
    elysia_loop = None
    runtime_loop = None
    module_registry = None
    auto_module_creator = None
    safety = None
    trust = None

    class _Mem:
        vector_memory = None

        def get_memory_state(self, load_if_needed=False):
            return {"memory_loaded": False, "memory_count": 0}

    memory = _Mem()


class RunningLoop:
    running = True
    paused = False

    class _TQ:
        @staticmethod
        def get_queue_size():
            return 2

    task_queue = _TQ()


class RunningOrchestrator(IdleOrchestrator):
    elysia_loop = RunningLoop()


def make_client(orchestrator):
    panel = UIControlPanel(orchestrator=orchestrator, host="127.0.0.1", port=5000)
    return panel, panel.app.test_client()


def test_status_orchestrator_none_returns_200_not_500():
    _, client = make_client(None)
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.get_json()["system"]["running"] is False


def test_status_idle_no_start_time_returns_200_datetime_regression():
    _, client = make_client(IdleOrchestrator())
    r = client.get("/api/status")
    assert r.status_code == 200
    assert "timestamp" in r.get_json()


def test_status_idle_is_not_running():
    _, client = make_client(IdleOrchestrator())
    data = client.get("/api/status").get_json()
    assert data["system"]["running"] is False
    assert data["loop"]["running"] is False


def test_status_running_only_when_loop_running():
    _, client = make_client(RunningOrchestrator())
    data = client.get("/api/status").get_json()
    assert data["system"]["running"] is True
    assert data["loop"]["running"] is True
    assert data["loop"]["queue_size"] == 2


def test_ping_identifies_service():
    _, client = make_client(None)
    r = client.get("/api/ping")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["service"] == "elysia-control-panel"


def test_chat_unavailable_is_503_and_empty_is_400():
    _, client = make_client(IdleOrchestrator())
    assert client.post("/api/chat", json={"message": "fictional hello"}).status_code == 503
    assert client.post("/api/chat", json={}).status_code == 400


def test_chat_via_ask_ai_stub_returns_reply():
    class Chatty(IdleOrchestrator):
        def ask_ai(self, message):
            return f"stub-reply: {message}"

    _, client = make_client(Chatty())
    r = client.post("/api/chat", json={"message": "fictional hello"})
    assert r.status_code == 200
    assert r.get_json()["reply"] == "stub-reply: fictional hello"


def test_models_endpoint_truthful_shape():
    _, client = make_client(IdleOrchestrator())
    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.get_json()
    assert body["configured_model"]
    local = body["local_ollama"]
    assert isinstance(local["models"], list)
    # Availability must agree with the actual probe result, never fabricated.
    assert body["configured_available_locally"] == (
        body["configured_model"] in local["models"] and local["available"]
    )
    if not local["available"]:
        assert local["error"]


def test_template_has_no_fabricated_running_fallback():
    src = (ROOT / "project_guardian" / "ui_control_panel.py").read_text(encoding="utf-8")
    assert "system: { running: true" not in src
    assert "function showOffline" in src


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_template_inline_javascript_parses():
    src = (ROOT / "project_guardian" / "ui_control_panel.py").read_text(encoding="utf-8")
    template = src.split('CONTROL_PANEL_TEMPLATE = """', 1)[1].split('"""', 1)[0]
    scripts = re.findall(r"<script>(.*?)</script>", template, re.S)
    assert scripts
    js = Path(__file__).parent / "_dashboard_check.js"
    js.write_text("\n;\n".join(scripts), encoding="utf-8")
    try:
        result = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    finally:
        js.unlink(missing_ok=True)
