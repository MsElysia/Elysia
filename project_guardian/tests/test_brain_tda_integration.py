from __future__ import annotations

from pathlib import Path

import pytest

from project_guardian.brain import pipeline as brain_pipeline_module
from project_guardian.brain.contracts import Observation, RiskLevel
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.brain.think_decide_act_adapter import (
    CONTRACT_CONCEPT_MAP,
    validate_contract_concept_map,
)


class StaticLLMRouter:
    def choose_backend(self, *, user_text, router_task_type, risk_level, registry=None):
        return "fake-local", f"offline:{router_task_type}:{risk_level.value}"


class NoopSelfImprovement:
    def __init__(self):
        self.calls = []

    def enqueue(self, outcome, trace):
        self.calls.append((outcome, trace))


class RecordingTDAExecutor:
    def __init__(self, result=None):
        self.calls = []
        self.result = result if result is not None else {"success": True, "output_summary": "delegated ok"}

    def __call__(self, proposal, context):
        self.calls.append((proposal, context))
        return self.result


def _pipe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory=None) -> BrainPipeline:
    monkeypatch.setattr(
        brain_pipeline_module,
        "_TRACE_PATH",
        tmp_path / "brain_last_pipeline.json",
    )
    return BrainPipeline(
        guardian=None,
        memory=memory or InMemoryBrainStore(),
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )


def test_brain_pipeline_runs_when_tda_delegation_disabled(tmp_path, monkeypatch):
    import project_guardian.orchestration.think_decide_act as tda

    def fail_if_called(*args, **kwargs):
        raise AssertionError("TDA runner should not be called")

    monkeypatch.setattr(tda, "run_think_decide_act_pipeline", fail_if_called)

    pipe = _pipe(tmp_path, monkeypatch)
    trace, dash = pipe.run(
        Observation("user", "safe noop probe"),
        context={"use_think_decide_act": False},
    )

    assert trace.tda_trace is None
    assert trace.execution is not None
    assert trace.execution.success is True
    assert dash["tda_trace"] is None
    assert not any(step.startswith("think_decide_act") for step in trace.transitions)


def test_brain_pipeline_routes_action_into_tda_when_context_enabled(tmp_path, monkeypatch):
    import project_guardian.orchestration.think_decide_act as tda

    real_runner = tda.run_think_decide_act_pipeline
    calls = []

    def spy_runner(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return real_runner(*args, **kwargs)

    monkeypatch.setattr(tda, "run_think_decide_act_pipeline", spy_runner)

    pipe = _pipe(tmp_path, monkeypatch)
    trace, _dash = pipe.run(
        Observation("user", "safe noop probe"),
        context={"use_think_decide_act": True},
    )

    assert len(calls) == 1
    tda_context = calls[0]["kwargs"]["context"]
    preferred_action = tda_context["preferred_action"]
    target = getattr(preferred_action, "target_module_or_tool", None)
    if target is None:
        target = preferred_action["target_module_or_tool"]
    assert target == "safe_noop"
    assert trace.tda_trace is not None
    assert "think_decide_act_enter" in trace.transitions


def test_tda_dry_run_passes_through_and_does_not_call_executor(tmp_path, monkeypatch):
    executor = RecordingTDAExecutor({"success": True, "output_summary": "should not run"})
    pipe = _pipe(tmp_path, monkeypatch)

    trace, _dash = pipe.run(
        Observation("user", "safe noop dry run"),
        context={
            "use_think_decide_act": True,
            "dry_run": True,
            "tda_executor": executor,
        },
    )

    assert executor.calls == []
    assert trace.tda_trace is not None
    assert trace.tda_trace["dry_run"] is True
    assert trace.execution is not None
    assert trace.execution.success is False
    assert trace.execution.data["dry_run"] is True
    assert trace.tda_trace["execution"]["result_payload"]["dry_run"] is True


def test_tda_blocked_action_stops_without_execution(tmp_path, monkeypatch):
    executor = RecordingTDAExecutor({"success": True, "output_summary": "should not execute"})
    pipe = _pipe(tmp_path, monkeypatch)

    trace, _dash = pipe.run(
        Observation("user", "please delete the temporary workspace"),
        context={"use_think_decide_act": True, "tda_executor": executor},
    )

    assert executor.calls == []
    assert trace.risk is not None
    assert trace.risk.level == RiskLevel.MEDIUM
    assert trace.execution is not None
    assert trace.execution.success is False
    assert trace.tda_trace is not None
    assert trace.tda_trace["validation"]["approved"] is False
    assert trace.tda_trace["validation"]["risk_level"] in ("blocked", "high", "medium")
    assert trace.tda_trace["validation"]["validation_notes"]
    assert trace.tda_trace["execution"]["result_payload"]["skipped"] is True
    assert "think_decide_act_finished" in trace.transitions


def test_successful_delegated_action_embeds_tda_trace_and_memory(tmp_path, monkeypatch):
    memory = InMemoryBrainStore()
    executor = RecordingTDAExecutor({"success": True, "output_summary": "delegated action completed"})
    pipe = _pipe(tmp_path, monkeypatch, memory=memory)

    trace, dash = pipe.run(
        Observation("user", "safe delegated action"),
        context={"use_think_decide_act": True, "tda_executor": executor},
    )

    assert len(executor.calls) == 1
    assert trace.execution is not None
    assert trace.execution.success is True
    assert trace.learning is not None
    assert trace.learning.worked is True
    assert trace.tda_trace is not None
    assert trace.tda_trace["execution"]["success"] is True
    assert trace.tda_trace["review"]["did_it_work"] is True
    assert trace.tda_trace["memory"] is not None
    assert dash["tda_trace"] == trace.tda_trace
    assert any(entry.get("category") == "think_decide_act" for entry in memory.entries)


def test_delegated_memory_write_redacts_credentials(tmp_path, monkeypatch):
    memory = InMemoryBrainStore()
    executor = RecordingTDAExecutor(
        {"success": True, "output_summary": "completed with token=abc123"}
    )
    pipe = _pipe(tmp_path, monkeypatch, memory=memory)

    trace, _dash = pipe.run(
        Observation("user", "safe delegated action"),
        context={"use_think_decide_act": True, "tda_executor": executor},
    )

    assert trace.tda_trace is not None
    assert trace.tda_trace["memory"] is not None
    assert "token=[REDACTED]" in trace.tda_trace["memory"]["summary"]
    assert "abc123" not in trace.tda_trace["memory"]["summary"]
    stored = [entry for entry in memory.entries if entry.get("category") == "think_decide_act"]
    assert stored
    assert "token=[REDACTED]" in stored[-1]["thought"]
    assert "abc123" not in stored[-1]["thought"]


def test_brain_tda_contract_concept_map_is_visible():
    status = validate_contract_concept_map()

    assert status["ok"] is True
    assert status["missing"] == []
    for brain_concept in (
        "Observation",
        "Plan/PlanStep",
        "StructuredCommand",
        "RiskAssessment",
        "ExecutionResult",
        "LearningOutcome",
        "Memory write",
    ):
        assert brain_concept in CONTRACT_CONCEPT_MAP
        assert brain_concept in status["map"]
