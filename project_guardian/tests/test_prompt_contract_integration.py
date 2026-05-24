# project_guardian/tests/test_prompt_contract_integration.py
"""Prompt-contract integration with BrainPipeline / TDA (no real LLM calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.brain import pipeline as brain_pipeline_module
from project_guardian.brain.contracts import BrainPipelineTrace, Observation
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.orchestration.think_decide_act import run_think_decide_act_pipeline


def _valid_planner_dict() -> dict:
    return {
        "goal": "Do the thing",
        "steps": [{"description": "step1"}],
        "constraints": [],
        "risk_level": "low",
        "reason_summary": "straightforward",
        "confidence": 0.7,
    }


class StaticLLMRouter:
    def choose_backend(self, *, user_text, router_task_type, risk_level, registry=None):
        return "fake-local", "offline"


class NoopSelfImprovement:
    def enqueue(self, *a):
        return None


@pytest.fixture
def tmp_trace_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "brain_last_pipeline.json"
    monkeypatch.setattr(brain_pipeline_module, "_TRACE_PATH", out)
    return out


def test_default_context_no_prompt_contract_validation(tmp_trace_path: Path):
    pipe = BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )
    trace, _ = pipe.run(Observation("user", "safe noop"))
    assert trace.run_context.get("prompt_contract_validation") is None


def test_warn_mode_records_validation_without_blocking(tmp_trace_path: Path):
    pipe = BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )
    trace, _ = pipe.run(
        Observation("user", "safe noop"),
        context={
            "validate_prompt_contracts": True,
            "prompt_contract_mode": "warn",
            "dry_run": False,
            "use_think_decide_act": False,
        },
    )
    pvc = trace.run_context.get("prompt_contract_validation") or {}
    assert "planner" in pvc
    assert pvc["planner"]["blocked"] is False
    assert trace.run_context.get("prompt_contract_strict_gate_failed") is None


def test_strict_dry_invalid_planner_marks_blocked_and_aborts_early(tmp_trace_path: Path):
    pipe = BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )
    bad = dict(_valid_planner_dict())
    bad["hidden_reasoning"] = "secret"
    trace, _ = pipe.run(
        Observation("user", "probe"),
        context={
            "validate_prompt_contracts": True,
            "prompt_contract_mode": "strict",
            "dry_run": True,
            "use_think_decide_act": False,
            "prompt_contract_overrides": {"planner": bad},
        },
    )
    pvc = trace.run_context.get("prompt_contract_validation") or {}
    assert pvc["planner"]["valid"] is False
    assert pvc["planner"]["blocked"] is True
    assert trace.execution is not None
    assert trace.execution.error == "prompt_contract_strict_abort_planner"
    assert trace.llm_backend == "skipped"


def test_brain_pipeline_tool_router_validation_when_enabled(tmp_trace_path: Path):
    pipe = BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )
    trace, _ = pipe.run(
        Observation("user", "safe noop"),
        context={
            "validate_prompt_contracts": True,
            "prompt_contract_mode": "warn",
            "dry_run": True,
            "use_think_decide_act": False,
            "prompt_contract_modules": ["tool_router"],
        },
    )
    pvc = trace.run_context.get("prompt_contract_validation") or {}
    assert "tool_router" in pvc
    assert "planner" not in pvc


def test_tda_think_validation_when_enabled():
    tr = run_think_decide_act_pipeline(
        {"source": "user", "message": "hello"},
        context={
            "validate_prompt_contracts": True,
            "prompt_contract_mode": "warn",
            "dry_run": True,
        },
        dry_run=True,
        guardian=None,
        executor=None,
    )
    pvc = tr.prompt_contract_validation
    assert "think_decide_act_thinker" in pvc


def test_tda_propose_validation_when_enabled():
    tr = run_think_decide_act_pipeline(
        {"source": "user", "message": "hello"},
        context={
            "validate_prompt_contracts": True,
            "prompt_contract_mode": "warn",
            "dry_run": True,
        },
        dry_run=True,
        guardian=None,
        executor=None,
    )
    pvc = tr.prompt_contract_validation
    assert "think_decide_act_proposer" in pvc


def test_hidden_reasoning_fails_contract_validation():
    from project_guardian.prompt_contracts.integration import validate_module_output_for_trace

    d = _valid_planner_dict()
    d["hidden_reasoning"] = "no"
    res = validate_module_output_for_trace(
        "planner",
        d,
        {"validate_prompt_contracts": True, "prompt_contract_mode": "warn", "dry_run": True},
    )
    assert res["valid"] is False
    assert any("forbidden" in e or "forbidden_key" in e for e in res["errors"])


def test_shell_like_pattern_fails_planner_contract():
    from project_guardian.prompt_contracts.integration import validate_module_output_for_trace

    d = _valid_planner_dict()
    d["steps"] = [{"description": "rm -rf /tmp"}]
    res = validate_module_output_for_trace(
        "planner",
        d,
        {"validate_prompt_contracts": True, "prompt_contract_mode": "warn", "dry_run": True},
    )
    assert res["valid"] is False


def test_warn_mode_invalid_planner_does_not_abort_pipeline(tmp_trace_path: Path):
    pipe = BrainPipeline(
        guardian=None,
        memory=InMemoryBrainStore(),
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )
    bad = dict(_valid_planner_dict())
    bad["hidden_reasoning"] = "x"
    trace, _ = pipe.run(
        Observation("user", "safe noop"),
        context={
            "validate_prompt_contracts": True,
            "prompt_contract_mode": "warn",
            "dry_run": True,
            "use_think_decide_act": False,
            "prompt_contract_overrides": {"planner": bad},
        },
    )
    assert trace.run_context.get("prompt_contract_strict_gate_failed") is None
    assert trace.llm_backend != "skipped"


def test_no_llm_imports_in_integration_module():
    import project_guardian.prompt_contracts.integration as mod

    src = Path(mod.__file__).read_text(encoding="utf-8").lower()
    assert "openai" not in src
    assert "anthropic" not in src
    assert "requests.post" not in src


def test_operator_chat_runtime_merge_does_not_enable_contract_validation(monkeypatch: pytest.MonkeyPatch):
    from project_guardian.brain.config import BrainPipelineConfig
    from project_guardian.brain.runtime import run_brain_pipeline_for_operator_event

    captured: dict = {}

    class RecordingBrainPipeline:
        def __init__(self, guardian=None):
            pass

        def run(self, observation, context=None):
            captured.update(dict(context or {}))
            return BrainPipelineTrace(), {}

    monkeypatch.setattr(
        "project_guardian.brain.pipeline.BrainPipeline",
        RecordingBrainPipeline,
    )

    ep = {
        "operator_chat": True,
        "operator_chat_live_execution": False,
        "tool_execution": False,
        "autonomy": False,
        "diagnostic": False,
    }
    cfg = BrainPipelineConfig(enabled=True, entrypoints=ep)
    run_brain_pipeline_for_operator_event("hello", guardian=None, context={}, config=cfg)
    assert captured.get("validate_prompt_contracts") is None


def test_strict_dry_tda_proposer_blocked_overrides_validate_stage():
    bad_proposer = {
        "action_type": "noop",
        "target": "safe_noop",
        "reason_summary": "x",
        "confidence": 0.71,
        "risk_level": "low",
        "hidden_reasoning": "nope",
    }
    tr = run_think_decide_act_pipeline(
        {"source": "user", "message": "hello"},
        context={
            "validate_prompt_contracts": True,
            "prompt_contract_mode": "strict",
            "dry_run": True,
            "prompt_contract_overrides": {"think_decide_act_proposer": bad_proposer},
        },
        dry_run=True,
        guardian=None,
        executor=None,
    )
    assert tr.prompt_contract_validation["think_decide_act_proposer"]["blocked"] is True
    assert tr.validation.approved is False
    assert "prompt_contract_strict" in (tr.validation.validation_notes or "")


def test_integration_shim_matches_validate_contract_output():
    from project_guardian.prompt_contracts.integration import validate_module_output_for_trace
    from project_guardian.prompt_contracts import validate_module_llm_response

    payload = json.dumps(_valid_planner_dict())
    ok, errs = validate_module_llm_response("planner", payload)
    res = validate_module_output_for_trace(
        "planner",
        payload,
        {"validate_prompt_contracts": True, "prompt_contract_mode": "warn"},
    )
    assert res["valid"] == ok
    assert res["errors"] == errs
