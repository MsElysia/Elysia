# project_guardian/tests/test_brain_pipeline.py

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.brain.contracts import Observation, RiskLevel, ToolRouteDecision
from project_guardian.brain.execution_module import CapabilityExecutionFacade
from project_guardian.brain.llm_router_module import UnifiedLLMRouterFacade
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.brain.planner_module import HeuristicPlannerModule
from project_guardian.brain.risk_module import KeywordRiskChecker
from project_guardian.brain.tool_router_module import DefaultToolRouterModule
from project_guardian.self_improvement.proposal_queue import reset_default_proposal_queue_for_tests


@pytest.fixture(autouse=True)
def _isolate_self_improvement_queues(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "project_guardian.brain.self_improvement_module._queue_path",
        lambda: tmp_path / "brain_self_improvement_queue.jsonl",
    )
    monkeypatch.setattr(
        "project_guardian.self_improvement.proposal_queue.DEFAULT_PROPOSALS_PATH",
        tmp_path / "self_improvement_proposals.jsonl",
    )
    reset_default_proposal_queue_for_tests()
    yield
    reset_default_proposal_queue_for_tests()
    import project_guardian.brain.planner_module as pm

    src = Path(pm.__file__).read_text(encoding="utf-8")
    assert "execute_capability" not in src
    assert "call_tool" not in src
    assert "ExecutionModule" not in src


def test_risk_checker_blocks_high_risk_command():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem)
    obs = Observation("user", "Please subprocess.run('echo hello') for automation")
    trace, _dash = pipe.run(obs)
    assert trace.risk is not None
    assert trace.risk.level.value == "high"
    assert trace.execution is None


def test_risk_checker_blocks_rm_rf():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem)
    obs = Observation("user", "rm -rf / is needed")
    trace, _ = pipe.run(obs)
    assert trace.risk.level.value == "blocked"
    assert trace.execution is None


def test_tool_router_fallback_when_primary_unavailable():
    class G:
        _modules = {}

    router = DefaultToolRouterModule()
    plan = HeuristicPlannerModule().plan(Observation("s", "x"), [], "")
    decision = router.route(Observation("s", "x"), plan, guardian=G())
    assert decision.used_fallback is True
    assert decision.selected == "brain:noop"


@patch("project_guardian.unified_llm_route.decide_chat_llm_backend")
def test_llm_router_prefers_local_for_low_risk(mock_decide):
    mock_decide.return_value = ("ollama", "test_local")
    fac = UnifiedLLMRouterFacade()
    b, r = fac.choose_backend(
        user_text="hello",
        router_task_type="simple",
        risk_level=RiskLevel.LOW,
        registry=None,
    )
    assert b == "ollama"
    assert "test_local" in r
    mock_decide.assert_called_once()
    call_kw = mock_decide.call_args.kwargs
    assert call_kw.get("task_type") == "simple"


def test_execution_module_logs_failure(caplog):
    caplog.set_level(logging.WARNING)
    ex = CapabilityExecutionFacade()
    from project_guardian.brain.contracts import RiskAssessment, RiskLevel, StructuredCommand, ToolRouteDecision

    r = ex.execute(
        None,
        StructuredCommand("tool:x", {}),
        risk=RiskAssessment(RiskLevel.LOW, "ok", {}),
        route=ToolRouteDecision("tool:x", "tool:x", False, "ok"),
    )
    assert r.success is False
    texts = [rec.getMessage() for rec in caplog.records]
    assert any("brain.execution failure" in t for t in texts)


def test_execution_module_logs_success(caplog):
    caplog.set_level(logging.INFO)
    ex = CapabilityExecutionFacade()
    from project_guardian.brain.contracts import RiskAssessment, RiskLevel, StructuredCommand, ToolRouteDecision

    r = ex.execute(
        None,
        StructuredCommand("brain:noop", {}),
        risk=RiskAssessment(RiskLevel.LOW, "ok", {}),
        route=ToolRouteDecision("brain:noop", "brain:noop", False, "ok"),
    )
    assert r.success is True
    texts = [rec.getMessage() for rec in caplog.records]
    assert any("brain.execution success" in t for t in texts)


def test_learning_writes_lesson_to_memory():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem)
    obs = Observation("user", "safe noop probe")
    _trace, _ = pipe.run(obs)
    assert mem.entries, "expected at least one memory write"
    assert any("brain.lesson" in str(e.get("category", "")) or "brain.lesson" in str(e) for e in mem.entries)


def test_brain_pipeline_trace_persisted(tmp_path, monkeypatch):
    mem = InMemoryBrainStore()
    out = tmp_path / "brain_last_pipeline.json"
    monkeypatch.setattr("project_guardian.brain.pipeline._TRACE_PATH", out)
    pipe = BrainPipeline(guardian=None, memory=mem)
    pipe.run(Observation("user", "hello"))
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "transitions" in data
    assert data["transitions"]
    assert "unified_export" in data
    assert data["unified_export"].get("brain_pipeline_id")


class _MockTdaExecutor:
    def execute(self, proposal, context=None):
        return {"success": True, "output_summary": "mock_executor_ok", "result": {"via": "mock"}}


class _ToolRouterModuleOnly:
    def route(self, observation, plan, *, guardian):
        return ToolRouteDecision("module:missing_mod", "module:missing_mod", False, "forced")


def test_brain_pipeline_without_think_decide_act_default():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem)
    trace, dash = pipe.run(Observation("user", "ping"))
    assert trace.think_decide_act_trace is None
    assert dash.get("think_decide_act_trace_present") is False


def test_brain_pipeline_with_think_decide_act_enabled(tmp_path, monkeypatch):
    mem = InMemoryBrainStore()
    out = tmp_path / "brain_last_pipeline.json"
    monkeypatch.setattr("project_guardian.brain.pipeline._TRACE_PATH", out)
    pipe = BrainPipeline(guardian=None, memory=mem)
    trace, _ = pipe.run(
        Observation("user", "simple hello for tda"),
        context={"use_think_decide_act": True, "dry_run": False, "tda_executor_override": _MockTdaExecutor()},
    )
    assert trace.think_decide_act_trace is not None
    assert trace.think_decide_act_trace.get("proposal", {}).get("action_id")
    assert trace.execution is not None
    assert trace.execution.success is True
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data.get("think_decide_act_trace_present") is True
    assert data.get("unified_export", {}).get("think_decide_act_trace") is not None


def test_brain_pipeline_think_decide_act_dry_run_no_success():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem)
    trace, _ = pipe.run(
        Observation("user", "dry run probe"),
        context={
            "use_think_decide_act": True,
            "dry_run": True,
            "tda_executor_override": _MockTdaExecutor(),
        },
    )
    assert trace.think_decide_act_trace is not None
    assert trace.think_decide_act_trace.get("dry_run") is True
    assert trace.execution is not None
    assert trace.execution.success is False
    assert trace.execution.data.get("dry_run") is True


def test_brain_pipeline_tda_validation_blocks_without_executor():
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(guardian=None, memory=mem, tool_router=_ToolRouterModuleOnly())
    trace, _ = pipe.run(
        Observation("user", "route to missing module"),
        context={"use_think_decide_act": True, "dry_run": False},
    )
    assert trace.think_decide_act_trace is not None
    assert trace.think_decide_act_trace.get("validation", {}).get("approved") is False
    assert trace.execution is not None
    assert trace.execution.success is False
