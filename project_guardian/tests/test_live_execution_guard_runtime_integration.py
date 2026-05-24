# project_guardian/tests/test_live_execution_guard_runtime_integration.py
"""Runtime wiring for live-execution guard (fail-closed; mocks only)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event

_RUNTIME_SOURCE = Path(__file__).resolve().parents[1] / "brain" / "runtime.py"
_LIVE_RUNTIME_SOURCE = Path(__file__).resolve().parents[1] / "brain" / "live_execution_runtime.py"


def _cfg(
    tmp_path: Path,
    *,
    enabled: bool = True,
    operator_chat: bool = True,
    live_execution: bool = False,
    dry_run: bool = True,
) -> BrainPipelineConfig:
    return BrainPipelineConfig(
        enabled=enabled,
        use_think_decide_act=True,
        dry_run=dry_run,
        persist_trace=True,
        trace_path=tmp_path / "brain_trace.json",
        entrypoints={
            "operator_chat": operator_chat,
            "operator_chat_live_execution": live_execution,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": False,
        },
    )


def _trace_times() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "dry_run_trace_completed_at": now - timedelta(seconds=30),
        "now": now,
    }


def _live_context(**overrides) -> dict:
    base = {
        "dry_run_trace_id": "trace-test-1",
        "operator_confirmed": True,
        "operator_confirmation_id": "op-confirm-1",
        "live_execution_executor": "brain:noop",
        "executor_allowlist": ("brain:noop",),
        "live_execution_risk_level": "low",
        **_trace_times(),
    }
    base.update(overrides)
    return base


def _mock_pipeline_run(context_holder: dict):
    def _run(_observation, context=None):
        if context is not None:
            context_holder.clear()
            context_holder.update(context)
        trace = MagicMock()
        trace.run_context = context_holder
        trace.brain_pipeline_id = "trace-test-1"
        trace.think_decide_act_trace = None
        trace.risk = None
        trace.execution = None
        trace.transitions = []
        return trace, {"status": "ok"}

    return _run


def _guard(ctx: dict) -> dict:
    return dict(ctx.get("live_execution_guard") or {})


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_default_operator_chat_brain_context_remains_dry_run(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path)
    run_brain_pipeline_for_operator_event("hello", config=cfg, context={"conversation_id": "c1"})
    assert ctx.get("dry_run") is True
    assert _guard(ctx).get("live_execution_disabled_by_default") is True


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_dry_run_false_request_forced_back_when_config_disabled(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context={"dry_run": False, **_live_context()},
    )
    assert ctx.get("dry_run") is True
    assert _guard(ctx).get("forced_dry_run") is True


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_operator_chat_live_execution_without_gates_denied(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event("hello", config=cfg)
    assert ctx.get("dry_run") is True
    guard = _guard(ctx)
    assert guard.get("requested_live_execution") is True
    assert guard.get("allowed") is False
    assert guard.get("forced_dry_run") is True


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_guard_denial_in_context_and_dashboard(mock_pipe, tmp_path):
    ctx: dict = {}
    captured_dashboard: dict = {}

    def _run(_observation, context=None):
        if context is not None:
            ctx.update(context)
        dash = {"status": "ok", "live_execution_guard": (context or {}).get("live_execution_guard")}
        captured_dashboard.update(dash)
        trace = MagicMock()
        trace.run_context = context
        trace.brain_pipeline_id = "t1"
        trace.transitions = []
        return trace, dash

    mock_pipe.return_value.run.side_effect = _run
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    trace, dashboard = run_brain_pipeline_for_operator_event("hi", config=cfg)
    assert "live_execution_guard" in ctx
    assert dashboard.get("live_execution_guard", {}).get("allowed") is False
    assert trace.run_context.get("live_execution_guard") is not None


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_audit_jsonl_written_on_denied_live_attempt(mock_pipe, tmp_path):
    audit_path = tmp_path / "live_execution_guard_audit.jsonl"
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)

    with patch(
        "project_guardian.governance.live_execution_audit.DEFAULT_AUDIT_PATH",
        audit_path,
    ):
        run_brain_pipeline_for_operator_event(
            "secret-token-abc",
            config=cfg,
            context={"live_execution_guard_audit_path": audit_path},
        )

    assert audit_path.is_file()
    row = json.loads(audit_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row.get("allowed") is False
    assert "secret-token-abc" not in json.dumps(row)


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_audit_write_failure_does_not_enable_live_execution(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)

    with patch(
        "project_guardian.brain.live_execution_runtime.append_live_execution_guard_audit",
        return_value=False,
    ):
        run_brain_pipeline_for_operator_event(
            "hello",
            config=cfg,
            context=_live_context(),
        )

    assert ctx.get("dry_run") is True
    reasons = _guard(ctx).get("reasons") or []
    assert "audit_write_failed" in reasons


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_high_risk_cannot_enable_live_execution(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_live_context(live_execution_risk_level="high"),
    )
    assert ctx.get("dry_run") is True
    assert "high_risk_denied" in (_guard(ctx).get("reasons") or [])


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_blocked_risk_cannot_enable_live_execution(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context={"live_execution_risk_level": "blocked", "dry_run": False},
    )
    assert ctx.get("dry_run") is True
    assert "blocked_risk_denied" in (_guard(ctx).get("reasons") or [])


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_autonomy_context_cannot_enable_live_execution(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context={"autonomy_context": True, "dry_run": False},
    )
    assert ctx.get("dry_run") is True
    assert "autonomy_context_denied" in (_guard(ctx).get("reasons") or [])


def test_runtime_module_does_not_add_executor_or_llm_calls():
    text = _RUNTIME_SOURCE.read_text(encoding="utf-8")
    live_text = _LIVE_RUNTIME_SOURCE.read_text(encoding="utf-8")
    combined = text + live_text
    for token in ("subprocess", "openai", "execute_capability(", "run_autonomous_cycle"):
        assert token not in combined


def test_existing_operator_chat_helper_still_passes_import():
    import project_guardian.safe_stack.operator_chat as oc

    assert callable(oc.run_operator_chat_turn)
