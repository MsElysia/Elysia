"""Tests for brain trace visibility (matches project_guardian.brain.trace_visibility on disk)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.brain.trace_visibility import (
    load_latest_brain_trace_summary,
    redact_sensitive,
    sanitize_brain_trace,
    summarize_trace,
)


def _cfg(trace_path: Path, **kwargs) -> BrainPipelineConfig:
    ep = {
        "operator_chat": False,
        "operator_chat_live_execution": False,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }
    return BrainPipelineConfig(
        enabled=kwargs.get("enabled", False),
        use_think_decide_act=True,
        dry_run=kwargs.get("dry_run", True),
        persist_trace=True,
        trace_path=trace_path,
        entrypoints=ep,
    )


def _valid_trace(**overrides):
    trace = {
        "brain_pipeline_id": "brain-123",
        "started_at": "2026-05-14T12:00:00+00:00",
        "input_source": "operator_chat",
        "risk": "low",
        "execution_ok": True,
        "think_decide_act_trace_present": True,
        "transitions": ["observation_received", "think_decide_act_finished"],
        "context_preview": "safe context",
        "unified_export": {"think_decide_act_trace": {"x": 1}},
    }
    trace.update(overrides)
    return trace


def test_missing_trace_returns_minimal_payload(tmp_path):
    p = tmp_path / "missing.json"
    out = load_latest_brain_trace_summary(config=_cfg(p))
    assert out["trace_exists"] is False
    assert out["trace_path"].endswith("missing.json")


def test_valid_trace_file_returns_summary_fields(tmp_path):
    trace_path = tmp_path / "brain_trace.json"
    trace_path.write_text(json.dumps(_valid_trace()), encoding="utf-8")
    out = load_latest_brain_trace_summary(config=_cfg(trace_path))
    assert out["trace_exists"] is True
    assert out["brain_pipeline_id"] == "brain-123"
    assert out["tda_used"] is True
    assert out["trace_path"] == str(trace_path)


def test_sensitive_values_are_redacted():
    s = "use api_key=sk-1234567890abcdef and Bearer secret_token_here"
    r = redact_sensitive(s)
    assert "sk-1234567890abcdef" not in r
    assert "Bearer secret_token_here" not in r
    assert "[REDACTED]" in r


def test_sanitize_truncates_long_context_preview():
    d = {"brain_pipeline_id": "1", "context_preview": "x" * 400}
    s = sanitize_brain_trace(d)
    assert len(s.get("context_preview", "")) <= 280


def test_malformed_json_trace_returns_error(tmp_path):
    trace_path = tmp_path / "bad_trace.json"
    trace_path.write_text("{not json", encoding="utf-8")
    out = load_latest_brain_trace_summary(config=_cfg(trace_path))
    assert out["trace_exists"] is False
    assert out.get("error") == "invalid_trace_json"
    assert "error_message" in out


def test_endpoint_200_no_trace(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path / "definitely_missing.json")
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)
    server = RuntimeAPIServer(status_provider=lambda: {"running": True}, event_bus=EventBus())
    r = server._app.test_client().get("/api/brain/trace/latest")
    assert r.status_code == 200
    assert r.get_json()["trace_exists"] is False


def test_endpoint_respects_configured_trace_path(tmp_path, monkeypatch):
    p = tmp_path / "custom.json"
    p.write_text(json.dumps(_valid_trace(brain_pipeline_id="z")), encoding="utf-8")
    cfg = _cfg(p, enabled=True)

    def _get(**_k):
        return cfg

    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", _get)
    server = RuntimeAPIServer(status_provider=lambda: {"running": True}, event_bus=EventBus())
    r = server._app.test_client().get("/api/brain/trace/latest")
    body = r.get_json()
    assert body["trace_path"] == str(p)
    assert body["trace_exists"] is True
    assert body["brain_pipeline_id"] == "z"


def test_api_latest_trace_returns_sanitized_summary(monkeypatch, tmp_path):
    trace_path = tmp_path / "brain_trace.json"
    trace_path.write_text(
        json.dumps(
            _valid_trace(
                context_preview="password=hunter2",
                unified_export={"think_decide_act_trace": {"raw": "nested-raw-secret"}},
            )
        ),
        encoding="utf-8",
    )
    cfg = _cfg(trace_path)
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)
    server = RuntimeAPIServer(status_provider=lambda: {"running": True}, event_bus=EventBus())
    body = server._app.test_client().get("/api/brain/trace/latest").get_json()
    text = json.dumps(body)
    assert body["trace_exists"] is True
    assert body["brain_pipeline_id"] == "brain-123"
    assert body["tda_used"] is True
    assert "hunter2" not in text
    assert "nested-raw-secret" not in text


def test_summarize_trace_aligns_with_sanitize_brain_trace():
    """summarize_trace adds dashboard fields; core ids match sanitize_brain_trace."""
    t = _valid_trace()
    san = sanitize_brain_trace(t)
    summ = summarize_trace(t)
    assert summ["brain_pipeline_id"] == san["brain_pipeline_id"]
    assert summ["started_at"] == str(san.get("started_at", ""))[:80]
    assert summ["input_source"] == str(san.get("input_source", ""))[:120]
    assert summ["tda_used"] is san.get("think_decide_act_trace_present")
    assert summ["risk_level"] == redact_sensitive(str(san.get("risk", "")))
    assert summ["observation_preview"] == san.get("context_preview", "")
    assert "self_improvement_queued" in summ
    assert "unified_export_keys" in summ


def test_operator_chat_response_still_compact(monkeypatch):
    class FakeArchitect:
        def chat(self, message, context="general"):
            return {"response": f"ok:{message}", "context": context, "source": "fake"}

    cfg = _cfg(Path("/nonexistent/default_trace.json"))
    monkeypatch.setattr("project_guardian.brain.config.get_brain_pipeline_config", lambda **_k: cfg)
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        architect=FakeArchitect(),
    )
    r = server._app.test_client().post("/api/chat", json={"message": "hello", "context": "general"})
    body = r.get_json()
    assert "unified_export" not in body
    assert "think_decide_act_trace" not in body
    assert "brain_trace_enabled" not in body
