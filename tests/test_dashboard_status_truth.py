"""
Regression tests for the Elysia Control Panel status/API surface
(project_guardian/ui_control_panel.py).

Covers defects reproduced during the 2026-10-23 runtime UI acceptance:

1. /api/status returned HTTP 500 (UnboundLocalError on ``datetime``) whenever the
   orchestrator was missing or had no ``start_time``.
2. /api/status reported ``system.running``/``loop.running`` as True for an idle
   orchestrator that merely owned a memory object ("false Running").
3. /api/chat wrapped ``ask_ai`` error strings ("Error: ...") as successful replies.
4. The rendered dashboard JavaScript fabricated a "running" status when
   /api/status failed, and never reported a lost backend.
5. The dashboard had no model-availability information at all.

These tests load ``ui_control_panel.py`` directly when the ``project_guardian``
package cannot be imported (on ``main`` the package ``__init__`` currently fails
because ``core.py`` imports modules that are missing), so the dashboard surface
can be verified independently of backend import health.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PG_DIR = PROJECT_ROOT / "project_guardian"

flask = pytest.importorskip("flask")
pytest.importorskip("flask_socketio")


def _load_file_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_ui_control_panel():
    """Prefer the packaged module; fall back to a standalone load of the same file."""
    try:
        import project_guardian.ui_control_panel as mod  # noqa: F401
        return mod
    except Exception:
        return _load_file_module("ui_control_panel_standalone", PG_DIR / "ui_control_panel.py")


@pytest.fixture(scope="module")
def ucp():
    return load_ui_control_panel()


class FictionalMemory:
    def get_memory_state(self, load_if_needed=False):
        return {"memory_loaded": True, "memory_count": 3}


class FictionalLoop:
    def __init__(self, running=True, paused=False):
        self.running = running
        self.paused = paused
        self.task_queue = None


class FictionalOrchestrator:
    """Duck-typed orchestrator: no GuardianCore, no providers, no persistence."""

    def __init__(self, running=False, loop=None, start_time=None, ask_ai_reply=None):
        self._initialized = True
        self._running = running
        self.memory = FictionalMemory()
        self.elysia_loop = loop
        self.start_time = start_time
        self.operational_stats = {}
        self._ask_ai_reply = ask_ai_reply

    def ask_ai(self, question):
        if self._ask_ai_reply is not None:
            return self._ask_ai_reply
        return "[fictional-model] " + question


def make_client(ucp, orchestrator):
    panel = ucp.UIControlPanel(orchestrator, host="127.0.0.1", port=5999)
    return panel, panel.app.test_client()


# --------------------------------------------------------------------------- ping

def test_ping_identifies_control_panel(ucp):
    _, client = make_client(ucp, FictionalOrchestrator())
    r = client.get("/api/ping")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["service"] == "elysia-control-panel"
    assert body["orchestrator"] is True


# ------------------------------------------------------------------------- status

def test_status_without_orchestrator_is_valid_json_not_500(ucp):
    """Regression: UnboundLocalError on ``datetime`` produced HTTP 500."""
    _, client = make_client(ucp, None)
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["system"]["running"] is False
    assert body["system"]["initialized"] is False
    assert "Orchestrator not available" in body["system"]["error"]
    assert "timestamp" in body
    assert "llm" in body


@pytest.mark.parametrize("start_time", [None, dt.datetime.now()])
def test_status_idle_orchestrator_is_not_reported_running(ucp, start_time):
    """Regression: memory present + no loop + _running False was reported as Running."""
    _, client = make_client(ucp, FictionalOrchestrator(running=False, loop=None, start_time=start_time))
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["system"]["initialized"] is True
    assert body["system"]["running"] is False
    assert body["loop"]["running"] is False
    assert body["loop"]["available"] is False
    assert body["memory"]["total_entries"] == 3


def test_status_running_loop_is_reported_running(ucp):
    _, client = make_client(ucp, FictionalOrchestrator(running=True, loop=FictionalLoop(running=True)))
    body = client.get("/api/status").get_json()
    assert body["system"]["running"] is True
    assert body["loop"]["running"] is True
    assert body["loop"]["paused"] is False


def test_status_paused_loop_is_reported_paused_not_running_flag_only(ucp):
    _, client = make_client(ucp, FictionalOrchestrator(running=True, loop=FictionalLoop(running=True, paused=True)))
    body = client.get("/api/status").get_json()
    assert body["loop"]["running"] is True
    assert body["loop"]["paused"] is True


def test_status_internal_error_path_returns_json_without_false_running(ucp):
    class ExplodingOrchestrator(FictionalOrchestrator):
        @property
        def start_time(self):  # hasattr() only swallows AttributeError
            raise RuntimeError("fictional failure")

        @start_time.setter
        def start_time(self, value):
            pass

    _, client = make_client(ucp, ExplodingOrchestrator())
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.get_json()
    assert "fictional failure" in body["system"]["error"]
    assert body["system"]["running"] is False
    assert body["loop"]["running"] is False
    assert body["llm"]["state"] == "unknown"


# ---------------------------------------------------------------------------- llm

def test_status_llm_block_has_stable_shape(ucp):
    _, client = make_client(ucp, FictionalOrchestrator())
    llm = client.get("/api/status").get_json()["llm"]
    for key in ("state", "canonical_model", "ollama_reachable", "model_installed",
                "installed_model_tags", "chat_backend", "detail"):
        assert key in llm
    assert llm["state"] in {"ready", "degraded", "unavailable", "unknown"}
    assert llm["chat_backend"] == "orchestrator.ask_ai"
    if llm["state"] == "unknown":
        # Unknown must come with an explanation, never a silent blank.
        assert llm["detail"]


@pytest.fixture
def planner_modules(monkeypatch):
    """
    Give the dashboard real ``planner_readiness`` / ``ollama_model_config`` modules.

    If the package imports, the real modules are used. Otherwise the two pure
    modules are loaded from file under a stub ``project_guardian`` package so the
    lookup inside ``_collect_llm_status`` resolves. Recorded probe state is
    restored afterwards.
    """
    try:
        from project_guardian import planner_readiness as pr  # type: ignore
        from project_guardian import ollama_model_config as omc  # type: ignore
    except Exception:
        pkg = types.ModuleType("project_guardian")
        pkg.__path__ = [str(PG_DIR)]  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "project_guardian", pkg)
        pr = _load_file_module("project_guardian.planner_readiness", PG_DIR / "planner_readiness.py")
        omc = _load_file_module("project_guardian.ollama_model_config", PG_DIR / "ollama_model_config.py")
        monkeypatch.setitem(sys.modules, "project_guardian.planner_readiness", pr)
        monkeypatch.setitem(sys.modules, "project_guardian.ollama_model_config", omc)

    saved = {k: getattr(pr, k) for k in (
        "_canonical_model", "_ollama_reachable", "_model_installed",
        "_installed_names", "_startup_health_ok", "_startup_detail")}
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "fictional-model:1b")
    yield pr, omc
    for k, v in saved.items():
        setattr(pr, k, v)


def _set_probe(pr, **kw):
    with pr._lock:
        for k, v in kw.items():
            setattr(pr, k, v)


def test_llm_state_unknown_before_startup_probe(ucp, planner_modules):
    pr, _ = planner_modules
    _set_probe(pr, _canonical_model="", _ollama_reachable=False, _model_installed=False,
               _installed_names=[], _startup_health_ok=False, _startup_detail="")
    _, client = make_client(ucp, FictionalOrchestrator())
    llm = client.get("/api/status").get_json()["llm"]
    assert llm["canonical_model"] == "fictional-model:1b"
    assert llm["state"] == "unknown"
    assert "probe has not run" in llm["detail"]


def test_llm_state_ready_when_probe_recorded_installed_and_healthy(ucp, planner_modules):
    pr, _ = planner_modules
    _set_probe(pr, _canonical_model="fictional-model:1b", _ollama_reachable=True, _model_installed=True,
               _installed_names=["fictional-model:1b", "other:7b"], _startup_health_ok=True, _startup_detail="")
    _, client = make_client(ucp, FictionalOrchestrator())
    llm = client.get("/api/status").get_json()["llm"]
    assert llm["state"] == "ready"
    assert llm["ollama_reachable"] is True
    assert llm["model_installed"] is True
    assert "fictional-model:1b" in llm["installed_model_tags"]


def test_llm_state_unavailable_when_ollama_unreachable(ucp, planner_modules):
    pr, _ = planner_modules
    _set_probe(pr, _canonical_model="fictional-model:1b", _ollama_reachable=False, _model_installed=False,
               _installed_names=[], _startup_health_ok=False, _startup_detail="connection refused 127.0.0.1:11434")
    _, client = make_client(ucp, FictionalOrchestrator())
    llm = client.get("/api/status").get_json()["llm"]
    assert llm["state"] == "unavailable"
    assert llm["ollama_reachable"] is False
    assert "connection refused" in llm["detail"]


def test_llm_state_unavailable_when_tag_not_installed(ucp, planner_modules):
    pr, _ = planner_modules
    _set_probe(pr, _canonical_model="fictional-model:1b", _ollama_reachable=True, _model_installed=False,
               _installed_names=["other:7b"], _startup_health_ok=False, _startup_detail="")
    _, client = make_client(ucp, FictionalOrchestrator())
    llm = client.get("/api/status").get_json()["llm"]
    assert llm["state"] == "unavailable"
    assert llm["model_installed"] is False
    assert "not installed" in llm["detail"]


# --------------------------------------------------------------------------- chat

def test_chat_success_returns_reply(ucp):
    _, client = make_client(ucp, FictionalOrchestrator())
    r = client.post("/api/chat", json={"message": "fictional ping"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True
    assert body["reply"] == "[fictional-model] fictional ping"
    assert body["error"] is None


@pytest.mark.parametrize("reply", [
    "Error: No OpenAI API key configured or openai module not available",
    "[AI Interaction Error] connection refused",
    "",
])
def test_chat_backend_error_strings_are_not_reported_as_success(ucp, reply):
    """Regression: ask_ai failure strings were returned with success=True."""
    _, client = make_client(ucp, FictionalOrchestrator(ask_ai_reply=reply))
    r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is False
    assert body["reply"] is None
    assert body["error"]


def test_chat_requires_message(ucp):
    _, client = make_client(ucp, FictionalOrchestrator())
    assert client.post("/api/chat", json={}).status_code == 400


def test_chat_without_backend_is_explicit_failure(ucp):
    class NoChat:
        _initialized = True
        _running = False
        memory = None
        elysia_loop = None

    _, client = make_client(ucp, NoChat())
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


# ---------------------------------------------------------------------- template

def _rendered_script(ucp) -> str:
    _, client = make_client(ucp, FictionalOrchestrator())
    html = client.get("/").get_data(as_text=True)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts, "inline <script> block not found in dashboard HTML"
    return "\n".join(scripts)


def test_dashboard_html_renders_with_status_elements(ucp):
    _, client = make_client(ucp, FictionalOrchestrator())
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for element_id in ("status-text", "status-indicator", "loop-status", "llm-model", "llm-readiness",
                       "api-chat-message", "api-chat-result", "console-logs"):
        assert f'id="{element_id}"' in html, element_id


def test_rendered_dashboard_javascript_has_no_syntax_errors(ucp, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available for JavaScript syntax check")
    js_path = tmp_path / "dashboard_inline.js"
    js_path.write_text(_rendered_script(ucp), encoding="utf-8")
    proc = subprocess.run([node, "--check", str(js_path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_template_does_not_fabricate_running_status_on_fetch_failure(ucp):
    js = _rendered_script(ucp)
    assert "running: true, initialized: true" not in js
    assert "Connected (Limited)" not in js
    # The failure path must be wired to the explicit unreachable handler.
    assert "noteStatusFailure(err)" in js
    assert "markBackendUnreachable" in js


def test_template_chat_has_timeout_and_error_branch(ucp):
    js = _rendered_script(ucp)
    assert "CHAT_TIMEOUT_MS" in js
    assert "Model error: " in js
