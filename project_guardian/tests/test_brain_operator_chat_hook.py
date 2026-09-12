from __future__ import annotations

import logging
from types import SimpleNamespace

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.config import BrainPipelineConfig


class FakeArchitect:
    def __init__(self):
        self.calls = []

    def chat(self, message, context="general"):
        self.calls.append((message, context))
        return {
            "response": f"architect says: {message}",
            "context": context,
            "source": "fake_architect",
        }


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def run_for_proposal(self, proposal_id):
        self.calls.append(proposal_id)
        raise AssertionError("operator chat hook must not invoke executors")


class FakeTrace:
    brain_pipeline_id = "trace-123"
    transitions = ["observation_received", "think_decide_act_enter", "execution_skipped"]
    risk = SimpleNamespace(level=SimpleNamespace(value="low"))
    execution = SimpleNamespace(success=False)
    think_decide_act_trace = {"raw_secret": "must not leak"}

    def __init__(self):
        self.run_context = {"dry_run": True}


def _server(*, architect=None, implementer=None, event_bus=None):
    bus = event_bus or EventBus()
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=bus,
        architect=architect,
        implementer=implementer,
    )
    return server, bus


def _cfg(*, enabled=False, operator_chat=False, dry_run=True, autonomy=False):
    return BrainPipelineConfig(
        enabled=enabled,
        dry_run=dry_run,
        use_think_decide_act=True,
        entrypoints={
            "operator_chat": operator_chat,
            "tool_execution": False,
            "autonomy": autonomy,
            "diagnostic": False,
        },
    )


def _patch_brain(monkeypatch, cfg, wrapper):
    monkeypatch.setattr(
        "project_guardian.brain.config.get_brain_pipeline_config",
        lambda: cfg,
    )
    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        wrapper,
    )


def test_default_safe_config_preserves_chat_and_does_not_call_brain(monkeypatch):
    calls = []

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("BrainPipeline wrapper should not be called")

    _patch_brain(monkeypatch, _cfg(enabled=False, operator_chat=False), wrapper)
    architect = FakeArchitect()
    server, _bus = _server(architect=architect)

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "hello", "context": "general"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["response"] == "architect says: hello"
    assert not any(key.startswith("brain_") for key in body)
    assert architect.calls == [("hello", "general")]
    assert calls == []


def test_enabled_config_with_operator_chat_disabled_does_not_call_wrapper(monkeypatch):
    calls = []

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("BrainPipeline wrapper should not be called")

    _patch_brain(monkeypatch, _cfg(enabled=True, operator_chat=False), wrapper)
    server, _bus = _server(architect=FakeArchitect())

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "still normal", "context": "general"},
    )

    assert response.status_code == 200
    assert response.get_json()["response"] == "architect says: still normal"
    assert calls == []


def test_enabled_operator_chat_calls_wrapper_once_with_operator_entrypoint(monkeypatch):
    calls = []

    def wrapper(input_event, **kwargs):
        calls.append((input_event, kwargs))
        return FakeTrace(), {"ok": True}

    _patch_brain(monkeypatch, _cfg(enabled=True, operator_chat=True), wrapper)
    server, _bus = _server(architect=FakeArchitect())

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "trace this", "context": "general"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    input_event, kwargs = calls[0]
    assert input_event["message"] == "trace this"
    assert kwargs["source_entrypoint"] == "operator_chat"
    body = response.get_json()
    assert body["brain_trace_enabled"] is True
    assert body["brain_trace_id"] == "trace-123"


def test_operator_chat_hook_forces_dry_run_even_when_config_disables_it(monkeypatch):
    calls = []

    def wrapper(_input_event, **kwargs):
        calls.append(kwargs)
        return FakeTrace(), {"ok": True}

    _patch_brain(monkeypatch, _cfg(enabled=True, operator_chat=True, dry_run=False), wrapper)
    server, _bus = _server(architect=FakeArchitect())

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "dry-run only", "context": "general"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["config"].dry_run is False
    assert response.get_json()["brain_dry_run"] is True


def test_wrapper_exception_fails_open_to_normal_chat(monkeypatch, caplog):
    def wrapper(*args, **kwargs):
        raise RuntimeError("trace failed")

    _patch_brain(monkeypatch, _cfg(enabled=True, operator_chat=True), wrapper)
    caplog.set_level(logging.WARNING, logger="elysia.api.server")
    server, _bus = _server(architect=FakeArchitect())

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "keep chatting", "context": "general"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["response"] == "architect says: keep chatting"
    assert body["brain_trace_error"] == "trace failed"
    assert "BrainPipeline operator chat trace failed" in caplog.text


def test_trace_metadata_is_small_and_only_present_when_enabled(monkeypatch):
    def wrapper(_input_event, **_kwargs):
        return FakeTrace(), {"ok": True}

    _patch_brain(monkeypatch, _cfg(enabled=True, operator_chat=True), wrapper)
    server, _bus = _server(architect=FakeArchitect())

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "metadata check", "context": "general"},
    )

    assert response.status_code == 200
    body = response.get_json()
    metadata = {key: value for key, value in body.items() if key.startswith("brain_")}
    assert metadata["brain_trace_id"] == "trace-123"
    assert metadata["brain_transition_count"] == 3
    assert metadata["brain_last_transition"] == "execution_skipped"
    assert "brain_raw_trace" not in metadata
    assert "brain_think_decide_act_trace" not in metadata
    assert "raw_secret" not in str(body)

    calls = []

    def disabled_wrapper(*args, **kwargs):
        calls.append((args, kwargs))

    _patch_brain(monkeypatch, _cfg(enabled=False, operator_chat=False), disabled_wrapper)
    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "metadata disabled", "context": "general"},
    )

    assert response.status_code == 200
    assert not any(key.startswith("brain_") for key in response.get_json())
    assert calls == []


def test_operator_chat_hook_does_not_invoke_real_executor_or_tool(monkeypatch):
    executor = FakeExecutor()
    calls = []

    def wrapper(_input_event, **kwargs):
        calls.append(kwargs)
        assert "tda_executor" not in kwargs.get("context", {})
        return FakeTrace(), {"ok": True}

    _patch_brain(monkeypatch, _cfg(enabled=True, operator_chat=True), wrapper)
    server, _bus = _server(architect=FakeArchitect(), implementer=executor)

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "trace without tools", "context": "general"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert executor.calls == []


def test_operator_chat_hook_does_not_touch_autonomy_entrypoint(monkeypatch):
    calls = []

    def wrapper(_input_event, **kwargs):
        calls.append(kwargs)
        return FakeTrace(), {"ok": True}

    _patch_brain(monkeypatch, _cfg(enabled=True, operator_chat=True, autonomy=True), wrapper)
    server, _bus = _server(architect=FakeArchitect())

    response = server._app.test_client().post(
        "/api/chat",
        json={"message": "operator only", "context": "general"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["source_entrypoint"] == "operator_chat"
    assert calls[0]["source_entrypoint"] != "autonomy"
