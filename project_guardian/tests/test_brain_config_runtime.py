from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from project_guardian.brain.config import BrainPipelineConfig, clear_brain_pipeline_config_cache, get_brain_pipeline_config
from project_guardian.brain.contracts import Observation
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event


@pytest.fixture(autouse=True)
def _clear_brain_config_cache():
    clear_brain_pipeline_config_cache()
    yield
    clear_brain_pipeline_config_cache()


def test_config_defaults_when_file_missing(tmp_path):
    missing = tmp_path / "nope.json"
    c = get_brain_pipeline_config(_path_str=str(missing))
    assert c.enabled is False
    assert c.dry_run is True
    assert c.use_think_decide_act is True
    assert c.entrypoints["autonomy"] is False
    assert c.entrypoints["diagnostic"] is False


def test_config_malformed_json_uses_defaults(tmp_path, caplog):
    caplog.set_level("WARNING")
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    c = get_brain_pipeline_config(_path_str=str(p))
    assert c.enabled is False
    assert any("invalid JSON" in r.message for r in caplog.records)


def test_runtime_disabled_bypasses_pipeline():
    cfg = BrainPipelineConfig(
        enabled=False,
        use_think_decide_act=True,
        dry_run=True,
        persist_trace=True,
        trace_path=Path("/tmp/unused"),
        entrypoints={
            "operator_chat": True,
            "operator_chat_live_execution": False,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": True,
        },
    )
    out = run_brain_pipeline_for_operator_event("hello", config=cfg, source_entrypoint="diagnostic")
    assert isinstance(out, dict) and out.get("bypass") is True
    assert out.get("reason") == "brain_pipeline_disabled"


def test_runtime_entrypoint_disabled():
    cfg = BrainPipelineConfig(
        enabled=True,
        use_think_decide_act=True,
        dry_run=True,
        persist_trace=True,
        trace_path=Path("/tmp/unused"),
        entrypoints={
            "operator_chat": False,
            "operator_chat_live_execution": False,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": False,
        },
    )
    out = run_brain_pipeline_for_operator_event("hello", config=cfg, source_entrypoint="diagnostic")
    assert out["reason"] == "entrypoint_disabled"


def test_runtime_enabled_invokes_pipeline(tmp_path, monkeypatch):
    out_file = tmp_path / "trace.json"
    cfg = BrainPipelineConfig(
        enabled=True,
        use_think_decide_act=True,
        dry_run=True,
        persist_trace=True,
        trace_path=out_file,
        entrypoints={
            "operator_chat": False,
            "operator_chat_live_execution": False,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": True,
        },
    )
    mock_run = MagicMock(return_value=("trace", {"ok": True}))
    with patch("project_guardian.brain.pipeline.BrainPipeline") as BP:
        BP.return_value.run = mock_run
        res = run_brain_pipeline_for_operator_event("ping", config=cfg, source_entrypoint="diagnostic")
    trace, dashboard = res
    assert trace == "trace"
    assert dashboard.get("ok") is True
    mock_run.assert_called_once()
    call_kw = mock_run.call_args.kwargs["context"]
    assert call_kw["dry_run"] is True
    assert call_kw["use_think_decide_act"] is True
    assert call_kw["source_entrypoint"] == "diagnostic"


def test_operator_chat_forces_dry_run_when_live_execution_off():
    cfg = BrainPipelineConfig(
        enabled=True,
        use_think_decide_act=False,
        dry_run=False,
        persist_trace=False,
        trace_path=Path("/tmp/x"),
        entrypoints={
            "operator_chat": True,
            "operator_chat_live_execution": False,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": False,
        },
    )
    mock_run = MagicMock(return_value=("trace", {}))
    with patch("project_guardian.brain.pipeline.BrainPipeline") as BP:
        BP.return_value.run = mock_run
        run_brain_pipeline_for_operator_event("x", config=cfg, source_entrypoint="operator_chat")
    assert mock_run.call_args.kwargs["context"]["dry_run"] is True


def test_operator_chat_allows_config_dry_run_when_live_execution_on():
    """Live entrypoint on still fails closed without confirmation; pipeline stays dry_run."""
    cfg = BrainPipelineConfig(
        enabled=True,
        use_think_decide_act=False,
        dry_run=False,
        persist_trace=False,
        trace_path=Path("/tmp/x"),
        entrypoints={
            "operator_chat": True,
            "operator_chat_live_execution": True,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": False,
        },
    )
    mock_run = MagicMock(return_value=("trace", {}))
    with patch("project_guardian.brain.pipeline.BrainPipeline") as BP:
        BP.return_value.run = mock_run
        run_brain_pipeline_for_operator_event("x", config=cfg, source_entrypoint="operator_chat")
    ctx = mock_run.call_args.kwargs["context"]
    assert ctx["dry_run"] is True
    assert ctx.get("live_execution_guard", {}).get("requested_live_execution") is True


def test_diagnostic_entrypoint_uses_config_dry_run_not_operator_override():
    """Diagnostic with dry_run=False is evaluated by the guard; denial keeps pipeline dry_run."""
    cfg = BrainPipelineConfig(
        enabled=True,
        use_think_decide_act=False,
        dry_run=False,
        persist_trace=False,
        trace_path=Path("/tmp/x"),
        entrypoints={
            "operator_chat": True,
            "operator_chat_live_execution": False,
            "tool_execution": False,
            "autonomy": False,
            "diagnostic": True,
        },
    )
    mock_run = MagicMock(return_value=("trace", {}))
    with patch("project_guardian.brain.pipeline.BrainPipeline") as BP:
        BP.return_value.run = mock_run
        run_brain_pipeline_for_operator_event("x", config=cfg, source_entrypoint="diagnostic")
    ctx = mock_run.call_args.kwargs["context"]
    assert ctx["dry_run"] is True
    assert "live_execution_guard" in ctx


def test_pipeline_dry_run_skips_direct_execution_without_tda():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem)
    trace, _ = pipe.run(
        Observation("user", "safe text"),
        context={"use_think_decide_act": False, "dry_run": True},
    )
    assert "execution_skipped" in trace.transitions
    assert trace.execution is not None
    assert trace.execution.success is False
    assert "dry_run" in (trace.execution.error or "")


def test_pipeline_persist_trace_false_skips_file(tmp_path, monkeypatch):
    mem = InMemoryBrainStore()
    out = tmp_path / "should_not_exist.json"
    monkeypatch.setattr("project_guardian.brain.pipeline._TRACE_PATH", out)
    pipe = BrainPipeline(guardian=None, memory=mem)
    trace, _ = pipe.run(
        Observation("user", "x"),
        context={"persist_trace": False, "trace_path": str(out)},
    )
    assert not out.exists()
    assert trace.unified_export is not None


def test_default_repo_config_autonomy_entrypoint_off():
    """Shipped defaults keep autonomy unwired; do not flip without explicit review."""
    cfg = get_brain_pipeline_config()
    assert cfg.entrypoints.get("autonomy") is False


def test_pipeline_blocked_risk_skips_execution():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem)
    trace, _ = pipe.run(
        Observation("user", "rm -rf / delete everything"),
        context={"use_think_decide_act": False, "dry_run": False},
    )
    assert trace.execution is None
    assert "execution_skipped" in trace.transitions
