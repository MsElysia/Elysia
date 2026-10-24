"""Regression coverage for truthful dashboard status and browser wiring."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def ui_module():
    """Load the UI module without importing the currently incomplete package root."""
    package_path = Path(__file__).parents[1] / "project_guardian"
    package = ModuleType("project_guardian")
    package.__path__ = [str(package_path)]
    sys.modules.setdefault("project_guardian", package)
    path = package_path / "ui_control_panel.py"
    spec = importlib.util.spec_from_file_location("elysia_ui_control_panel_acceptance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ping_identifies_control_panel(ui_module):
    panel = ui_module.UIControlPanel(orchestrator=None)
    response = panel.app.test_client().get("/api/ping")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "service": "elysia-control-panel",
        "port": 5000,
        "orchestrator": False,
    }


def test_status_without_orchestrator_is_valid_and_not_running(ui_module):
    panel = ui_module.UIControlPanel(orchestrator=None)
    response = panel.app.test_client().get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data["system"]["running"] is False
    assert data["system"]["initialized"] is False
    assert data["loop"]["running"] is False
    assert data["timestamp"]


def test_loaded_components_do_not_fabricate_running_state(ui_module):
    orchestrator = SimpleNamespace(
        _initialized=False,
        _running=False,
        memory=SimpleNamespace(
            get_memory_state=lambda load_if_needed=False: {
                "memory_loaded": True,
                "memory_count": 4,
            }
        ),
        elysia_loop=SimpleNamespace(
            running=False,
            paused=False,
            task_queue=SimpleNamespace(get_queue_size=lambda: 0),
        ),
        start_time=None,
        operational_stats={},
    )
    panel = ui_module.UIControlPanel(orchestrator=orchestrator)
    response = panel.app.test_client().get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data["system"]["running"] is False
    assert data["system"]["initialized"] is False
    assert data["loop"]["running"] is False
    assert data["memory"]["total_entries"] == 4


def test_chat_backend_failures_are_service_unavailable(ui_module):
    unified = SimpleNamespace(chat_with_llm=lambda message: ("", "Ollama is offline"))
    orchestrator = SimpleNamespace(_unified_system=unified)
    panel = ui_module.UIControlPanel(orchestrator=orchestrator)
    response = panel.app.test_client().post("/api/chat", json={"message": "Hello"})

    assert response.status_code == 503
    assert response.get_json() == {
        "success": False,
        "error": "Ollama is offline",
        "reply": None,
    }


def test_model_status_reports_configured_model_and_unreachable_runtime(
    ui_module, monkeypatch
):
    monkeypatch.setattr(
        "project_guardian.ollama_health.list_ollama_installed_model_names",
        lambda base_url, timeout: ([], "tags_unreachable: connection refused"),
    )
    panel = ui_module.UIControlPanel(orchestrator=None)
    response = panel.app.test_client().get("/api/models")

    assert response.status_code == 200
    data = response.get_json()
    assert data["provider"] == "ollama"
    assert data["configured_model"] == "mistral:7b"
    assert data["available_models"] == []
    assert data["configured_available"] is False
    assert data["reachable"] is False
    assert "connection refused" in data["error"]


def test_template_has_truthful_disconnect_and_model_status_wiring(ui_module):
    template = ui_module.CONTROL_PANEL_TEMPLATE

    assert "setConnectionState(false, 'Offline — ' + msg)" in template
    assert "element.textContent = 'Unknown'" in template
    assert "system: { running: true, initialized: true" not in template
    assert "Available models: checking…" in template
    assert "Model request timed out after 60 seconds" in template
