# project_guardian/tests/test_operator_confirmation_guard_integration.py
"""Validation-only integration: confirmation store + live-execution guard (no live exec)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from project_guardian.brain.config import BrainPipelineConfig
from project_guardian.brain.live_execution_runtime import apply_live_execution_guard_to_context
from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event
from project_guardian.governance.operator_confirmation_store import (
    OperatorConfirmationStore,
    get_operator_confirmation,
)

_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
_LIVE_RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[1] / "brain" / "live_execution_runtime.py"
)


def _cfg(
    tmp_path: Path,
    *,
    live_execution: bool = False,
    dry_run: bool = True,
) -> BrainPipelineConfig:
    return BrainPipelineConfig(
        enabled=True,
        use_think_decide_act=True,
        dry_run=dry_run,
        persist_trace=True,
        trace_path=tmp_path / "brain_trace.json",
        entrypoints={
            "operator_chat": True,
            "operator_chat_live_execution": live_execution,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": False,
        },
    )


def _create_confirmation(
    store_path: Path,
    confirmation_id: str = "conf_ok",
    *,
    risk_level: str = "low",
    ttl_seconds: float = 3600.0,
    autonomy_context: bool = False,
) -> None:
    store = OperatorConfirmationStore(store_path)
    rec, errors = store.create_operator_confirmation(
        operator_id="op1",
        conversation_id="control_panel",
        dry_run_trace_id="trace-1",
        confirmed_action_id="act-1",
        action_summary="Invoke brain:noop",
        action_type="capability_invoke",
        tool_name="brain:noop",
        risk_level=risk_level,
        executor_allowlisted=True,
        confirmation_id=confirmation_id,
        ttl_seconds=ttl_seconds,
        now=_NOW,
        autonomy_context=autonomy_context,
    )
    assert errors == []
    assert rec is not None


def _append_raw_record(store_path: Path, row: dict) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with store_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


def _base_context(store_path: Path, confirmation_id: str, **overrides) -> dict:
    ctx = {
        "operator_confirmation_store_path": str(store_path),
        "operator_confirmation_id": confirmation_id,
        "dry_run_trace_id": "trace-1",
        "confirmed_action_id": "act-1",
        "dry_run_trace_age_seconds": 30.0,
        "conversation_id": "c1",
    }
    ctx.update(overrides)
    return ctx


def _mock_pipeline_run(context_holder: dict):
    def _run(_observation, context=None):
        if context is not None:
            context_holder.clear()
            context_holder.update(context)
        trace = MagicMock()
        trace.run_context = context_holder
        trace.brain_pipeline_id = "trace-1"
        trace.transitions = []
        return trace, {"status": "ok"}

    return _run


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_missing_confirmation_id_no_effect_on_default_dry_run(mock_pipe, tmp_path):
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path)
    run_brain_pipeline_for_operator_event("hello", config=cfg, context={"conversation_id": "c1"})
    assert ctx.get("dry_run") is True
    assert "operator_confirmation_validation" not in ctx


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_valid_confirmation_id_adds_validation_metadata(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create_confirmation(store_path)
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_ok"),
    )
    validation = ctx.get("operator_confirmation_validation") or {}
    assert validation.get("valid") is True
    assert validation.get("validation_only") is True
    assert validation.get("consumed") is False
    assert ctx.get("operator_confirmed") is True


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_valid_confirmation_still_dry_run_when_config_disabled(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create_confirmation(store_path)
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=False, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context={**_base_context(store_path, "conf_ok"), "dry_run": False},
    )
    assert ctx.get("dry_run") is True
    validation = ctx.get("operator_confirmation_validation") or {}
    assert validation.get("valid") is True
    assert validation.get("live_execution_disabled_by_config") is True
    guard = ctx.get("live_execution_guard") or {}
    assert guard.get("allowed") is False


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_missing_confirmation_record_denies_live_attempt(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_missing"),
    )
    assert ctx.get("dry_run") is True
    validation = ctx.get("operator_confirmation_validation") or {}
    assert validation.get("valid") is False
    assert validation.get("reason") == "not_found"


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_expired_confirmation_denies_live_attempt(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create_confirmation(store_path, "conf_exp", ttl_seconds=60.0)
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context={
            **_base_context(store_path, "conf_exp"),
            "now": _NOW + timedelta(seconds=120),
        },
    )
    assert ctx.get("dry_run") is True
    validation = ctx.get("operator_confirmation_validation") or {}
    assert validation.get("valid") is False
    assert validation.get("reason") == "expired"


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_used_confirmation_denies_live_attempt(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create_confirmation(store_path, "conf_used")
    store = OperatorConfirmationStore(store_path)
    store.mark_operator_confirmation_used("conf_used", now=_NOW)
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_used"),
    )
    assert ctx.get("dry_run") is True
    validation = ctx.get("operator_confirmation_validation") or {}
    assert validation.get("valid") is False
    assert validation.get("reason") == "already_used"


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_mismatched_dry_run_trace_id_denies(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create_confirmation(store_path, "conf_trace")
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_trace", dry_run_trace_id="other-trace"),
    )
    assert ctx.get("dry_run") is True
    assert (ctx.get("operator_confirmation_validation") or {}).get("reason") == "dry_run_trace_mismatch"


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_mismatched_confirmed_action_id_denies(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create_confirmation(store_path, "conf_act")
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_act", confirmed_action_id="other-act"),
    )
    assert ctx.get("dry_run") is True
    assert (
        ctx.get("operator_confirmation_validation") or {}
    ).get("reason") == "confirmed_action_mismatch"


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_high_risk_confirmation_denies(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _append_raw_record(
        store_path,
        {
            "operator_confirmation_id": "conf_high",
            "created_at": _NOW.isoformat(),
            "expires_at": (_NOW + timedelta(hours=1)).isoformat(),
            "status": "pending",
            "dry_run_trace_id": "trace-1",
            "confirmed_action_id": "act-1",
            "action_summary": "x",
            "action_type": "capability_invoke",
            "tool_name": "brain:noop",
            "risk_level": "high",
            "executor_allowlisted": True,
            "prompt_contract_valid": True,
        },
    )
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_high"),
    )
    assert ctx.get("dry_run") is True
    assert (ctx.get("operator_confirmation_validation") or {}).get("valid") is False


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_blocked_risk_confirmation_denies(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _append_raw_record(
        store_path,
        {
            "operator_confirmation_id": "conf_blocked",
            "created_at": _NOW.isoformat(),
            "expires_at": (_NOW + timedelta(hours=1)).isoformat(),
            "status": "pending",
            "dry_run_trace_id": "trace-1",
            "confirmed_action_id": "act-1",
            "action_summary": "x",
            "action_type": "capability_invoke",
            "tool_name": "brain:noop",
            "risk_level": "blocked",
            "executor_allowlisted": True,
            "prompt_contract_valid": True,
        },
    )
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_blocked"),
    )
    assert ctx.get("dry_run") is True
    assert (ctx.get("operator_confirmation_validation") or {}).get("reason") == "risk_not_confirmable"


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_autonomy_confirmation_denies(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _append_raw_record(
        store_path,
        {
            "operator_confirmation_id": "conf_auto",
            "created_at": _NOW.isoformat(),
            "expires_at": (_NOW + timedelta(hours=1)).isoformat(),
            "status": "pending",
            "dry_run_trace_id": "trace-1",
            "confirmed_action_id": "act-1",
            "action_summary": "x",
            "action_type": "capability_invoke",
            "tool_name": "brain:noop",
            "risk_level": "low",
            "autonomy_context": True,
            "executor_allowlisted": True,
            "prompt_contract_valid": True,
        },
    )
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_auto"),
    )
    assert ctx.get("dry_run") is True
    assert (ctx.get("operator_confirmation_validation") or {}).get("reason") == "autonomy_context"


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_confirmation_not_marked_used_in_validation_only_mode(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create_confirmation(store_path, "conf_pending")
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context={**_base_context(store_path, "conf_pending"), "dry_run": False},
    )
    rec = get_operator_confirmation("conf_pending", store_path=store_path, now=_NOW)
    assert rec is not None
    assert rec.status == "pending"
    assert not rec.used_at


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_temp_store_path_override_works(mock_pipe, tmp_path):
    store_path = tmp_path / "alt" / "confirmations.jsonl"
    _create_confirmation(store_path, "conf_alt")
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context=_base_context(store_path, "conf_alt"),
    )
    assert (ctx.get("operator_confirmation_validation") or {}).get("valid") is True


@patch("project_guardian.brain.pipeline.BrainPipeline")
def test_audit_records_confirmation_id_on_denied_live_attempt(mock_pipe, tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    audit_path = tmp_path / "live_execution_guard_audit.jsonl"
    _create_confirmation(store_path)
    ctx: dict = {}
    mock_pipe.return_value.run.side_effect = _mock_pipeline_run(ctx)
    cfg = _cfg(tmp_path, live_execution=True, dry_run=False)
    run_brain_pipeline_for_operator_event(
        "hello",
        config=cfg,
        context={
            **_base_context(store_path, "conf_ok"),
            "dry_run": False,
            "live_execution_guard_audit_path": str(audit_path),
        },
    )
    assert audit_path.is_file()
    row = json.loads(audit_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row.get("operator_confirmation_id") == "conf_ok"
    assert row.get("allowed") is False


def test_no_shell_subprocess_llm_api_in_live_runtime_module():
    text = _LIVE_RUNTIME_SOURCE.read_text(encoding="utf-8").lower()
    for token in ("subprocess", "os.system", "openai", "httpx", "requests.post", "requests.get"):
        assert token not in text
