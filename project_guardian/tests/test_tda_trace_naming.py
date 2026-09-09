"""Regression tests for BrainPipeline/TDA trace naming contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_guardian.brain import pipeline as brain_pipeline_module
from project_guardian.brain.contracts import Observation
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.brain.trace_visibility import summarize_trace


class StaticLLMRouter:
    def choose_backend(self, *, user_text, router_task_type, risk_level, registry=None):
        return "fake-local", f"offline:{router_task_type}:{risk_level.value}"


class NoopSelfImprovement:
    def enqueue(self, outcome, trace):
        return None


def _pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BrainPipeline:
    monkeypatch.setattr(
        brain_pipeline_module,
        "_TRACE_PATH",
        tmp_path / "brain_last_pipeline.json",
    )
    return BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )


def test_brain_pipeline_tda_trace_uses_canonical_field(tmp_path, monkeypatch):
    pipe = _pipeline(tmp_path, monkeypatch)

    trace, _dashboard = pipe.run(
        Observation("user", "safe noop trace naming probe"),
        context={"use_think_decide_act": True, "dry_run": True},
    )

    assert trace.think_decide_act_trace is not None
    assert isinstance(trace.think_decide_act_trace, dict)
    if trace.tda_trace is not None:
        assert trace.tda_trace == trace.think_decide_act_trace


def test_sanitized_trace_visibility_hides_full_tda_trace():
    summary = summarize_trace(
        {
            "brain_pipeline_id": "brain-trace-naming-test",
            "started_at": "2026-05-16T12:00:00+00:00",
            "input_source": "operator_chat",
            "risk": "low",
            "execution_ok": True,
            "think_decide_act_trace_present": True,
            "think_decide_act_trace": {
                "observation": {"raw_input": "do not expose this full nested trace"}
            },
            "tda_trace": {
                "observation": {"raw_input": "do not expose this alias either"}
            },
            "unified_export": {
                "think_decide_act_trace": {"nested": "hidden"},
                "tda_trace": {"nested": "hidden"},
                "safe_summary": "ok",
            },
            "transitions": ["observation_received", "think_decide_act_finished"],
        }
    )

    assert summary["tda_used"] is True
    assert "think_decide_act_trace" not in summary
    assert "tda_trace" not in summary
    assert "think_decide_act_trace" not in summary.get("unified_export_keys", [])
    assert "tda_trace" not in summary.get("unified_export_keys", [])
    assert "safe_summary" in summary.get("unified_export_keys", [])
    assert "do not expose" not in repr(summary)


def test_brain_architecture_docs_name_canonical_tda_trace_field():
    doc = Path("docs/ELYSIA_BRAIN_ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "think_decide_act_trace" in doc
    assert "canonical" in doc.lower()

