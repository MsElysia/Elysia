"""RuntimeAPIServer /api/chat integration with BrainPipeline config (mocked, no LLM)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.brain.contracts import BrainPipelineTrace, RiskAssessment, RiskLevel


class FakeArchitect:
    def __init__(self):
        self.calls = []

    def chat(self, message, context="general"):
        self.calls.append((message, context))
        return {"response": f"ok:{message}", "context": context, "source": "fake"}


class FakeProposalSystem:
    def get_proposal(self, proposal_id):
        return {"title": "t", "status": "draft", "proposal_id": proposal_id}


def _ep(**overrides):
    base = {
        "operator_chat": False,
        "operator_chat_live_execution": False,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }
    base.update(overrides)
    return base


def _make_trace() -> BrainPipelineTrace:
    tr = BrainPipelineTrace()
    tr.brain_pipeline_id = "test-trace-id"
    tr.run_context = {"dry_run": True, "use_think_decide_act": True}
    tr.risk = RiskAssessment(RiskLevel.LOW, "ok", {})
    tr.think_decide_act_trace = {"stub": True}
    return tr


@pytest.fixture
def chat_server():
    arch = FakeArchitect()
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        architect=arch,
    )
    return server, arch


def test_api_chat_default_no_brain_metadata(chat_server, monkeypatch):
    server, _arch = chat_server
    cfg = BrainPipelineConfig(
        enabled=False,
        trace_path=Path("/tmp/brain.json"),
        entrypoints=_ep(),
    )
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)
    client = server._app.test_client()
    r = client.post("/api/chat", json={"message": "hello", "context": "general"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["response"] == "ok:hello"
    assert "brain_trace_enabled" not in body
    assert "brain_trace_error" not in body


def test_api_chat_operator_off_skips_pipeline(chat_server, monkeypatch):
    server, _arch = chat_server
    spy = MagicMock()
    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        spy,
    )
    cfg = BrainPipelineConfig(
        enabled=True,
        trace_path=Path("/tmp/brain.json"),
        entrypoints=_ep(operator_chat=False),
    )
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)
    client = server._app.test_client()
    client.post("/api/chat", json={"message": "hello", "context": "general"})
    spy.assert_not_called()


def test_api_chat_operator_on_calls_pipeline_once_forces_dry_run(chat_server, monkeypatch, tmp_path):
    server, _arch = chat_server
    tp = tmp_path / "t.json"
    cfg = BrainPipelineConfig(
        enabled=True,
        use_think_decide_act=True,
        dry_run=False,
        persist_trace=False,
        trace_path=tp,
        entrypoints=_ep(operator_chat=True, operator_chat_live_execution=False),
    )
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)

    mock_run = MagicMock(return_value=(_make_trace(), {"dash": 1}))
    with patch("project_guardian.brain.pipeline.BrainPipeline") as BP:
        BP.return_value.run = mock_run
        client = server._app.test_client()
        r = client.post("/api/chat", json={"message": "hello", "context": "general"})
    assert r.status_code == 200
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["context"]["dry_run"] is True
    body = r.get_json()
    assert body["brain_trace_enabled"] is True
    assert body["brain_trace_id"] == "test-trace-id"
    assert body["brain_dry_run"] is True
    assert body["brain_tda_used"] is True
    assert body["response"] == "ok:hello"


def test_api_chat_pipeline_exception_does_not_break_chat(chat_server, monkeypatch):
    server, _arch = chat_server
    cfg = BrainPipelineConfig(
        enabled=True,
        trace_path=Path("/tmp/x"),
        entrypoints=_ep(operator_chat=True),
    )
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)
    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        MagicMock(side_effect=RuntimeError("brain boom")),
    )
    client = server._app.test_client()
    r = client.post("/api/chat", json={"message": "hello", "context": "general"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["response"] == "ok:hello"
    assert "brain_trace_error" in body
    assert "boom" in body["brain_trace_error"]


def test_proposal_context_chat_skips_brain_trace(chat_server, monkeypatch):
    server, _ = chat_server
    server._proposal_system = FakeProposalSystem()  # type: ignore[attr-defined]
    spy = MagicMock()
    monkeypatch.setattr(
        "project_guardian.brain.runtime.run_brain_pipeline_for_operator_event",
        spy,
    )
    cfg = BrainPipelineConfig(
        enabled=True,
        trace_path=Path("/tmp/x"),
        entrypoints=_ep(operator_chat=True),
    )
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)
    client = server._app.test_client()
    r = client.post("/api/chat", json={"message": "hi", "context": "proposal:p1"})
    assert r.status_code == 200
    spy.assert_not_called()
    body = r.get_json()
    assert "brain_trace_enabled" not in body
