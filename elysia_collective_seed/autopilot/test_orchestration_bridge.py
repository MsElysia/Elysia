from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
from typing import Any

from elysia_collective_seed.autopilot.orchestration_bridge import run_via_broker
from elysia_collective_seed.autopilot.task_ledger import TaskLedger


NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)


def _task(task_id: str = "ELY-TASK-900001", *, risk_class: str = "read_only") -> dict:
    return {
        "task_id": task_id,
        "title": "Diagnose pytest log",
        "objective": "Read this synthetic pytest failure text and explain the likely cause.",
        "status": "queued",
        "task_class": "analysis",
        "risk_class": risk_class,
        "acceptance_criteria": ["Return a concise diagnosis."],
        "required_capabilities": [],
        "required_checks": [],
        "required_review_roles": [],
        "human_approval_required": False,
        "max_attempts": 3,
    }


@dataclass
class FakePipelineResult:
    task_id: str
    pipeline_id: str
    success: bool
    final_output: Any
    node_results: list[Any] = field(default_factory=list)
    route_reason: str = ""
    error: str | None = None


class FakeBroker:
    def __init__(self) -> None:
        self.calls: list[Any] = []
        self.kwargs: list[dict] = []

    def run_task_sync(self, request, **kwargs):
        self.calls.append(request)
        self.kwargs.append(dict(kwargs))
        return FakePipelineResult(
            task_id=request.task_id,
            pipeline_id="serial_plan_execute_review",
            success=True,
            final_output={"diagnosis": "synthetic import failure"},
            route_reason="test_local_only",
        )


def test_read_only_bridge_uses_existing_broker_without_guardian_and_submits(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    broker = FakeBroker()
    try:
        ledger.put_task(_task())
        claim = ledger.claim("ELY-TASK-900001", "ollama-worker", now=NOW)
        assert claim.claimed

        result = run_via_broker(ledger, "ELY-TASK-900001", "ollama-worker", broker=broker, now=NOW)

        assert result.submitted and result.state == "submitted"
        assert len(broker.calls) == 1
        request = broker.calls[0]
        assert request.task_type == "reasoning"
        assert request.metadata["local_only"] is True
        assert request.context["execution_attempt"] == 1
        assert broker.kwargs == [{}], "guardian or another runtime authority was passed to the broker"

        row = ledger.get("ELY-TASK-900001")
        assert row["status"] == "verifying"
        assert row["bridge_status"] == "submitted"
        assert row["attempt"] == 1
        assert row["completion_submission"]["attempt"] == 1
        assert row["completion_submission"]["packet"]["worker"]["role"] == "read_only_local_inference"
        assert row["completion_submission"]["packet"]["files_changed"] == []

        event_types = [event["event_type"] for event in ledger.events("ELY-TASK-900001")]
        assert "broker_execution_started" in event_types
        assert "broker_result_captured" in event_types
        assert "producer_completion_submitted" in event_types
        assert "broker_result_submitted" in event_types
    finally:
        ledger.close()


def test_captured_result_retries_submission_without_duplicate_inference(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    broker = FakeBroker()
    try:
        ledger.put_task(_task("ELY-TASK-900002"))
        assert ledger.claim("ELY-TASK-900002", "ollama-worker", now=NOW).claimed

        original_submit = ledger.submit_for_verification
        ledger.submit_for_verification = lambda *args, **kwargs: False  # type: ignore[method-assign]
        first = run_via_broker(ledger, "ELY-TASK-900002", "ollama-worker", broker=broker, now=NOW)
        assert not first.submitted and first.state == "result_captured"
        assert len(broker.calls) == 1

        ledger.submit_for_verification = original_submit  # type: ignore[method-assign]
        second = run_via_broker(ledger, "ELY-TASK-900002", "ollama-worker", broker=broker, now=NOW)
        assert second.submitted
        assert len(broker.calls) == 1, "captured result caused duplicate inference under the same live attempt"
    finally:
        ledger.close()


def test_bridge_refuses_non_read_only_task_before_broker_call(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    broker = FakeBroker()
    try:
        ledger.put_task(_task("ELY-TASK-900003", risk_class="repo_write"))
        assert ledger.claim("ELY-TASK-900003", "ollama-worker", now=NOW).claimed
        result = run_via_broker(ledger, "ELY-TASK-900003", "ollama-worker", broker=broker, now=NOW)
        assert not result.submitted
        assert result.error == "read_only_only"
        assert broker.calls == []
    finally:
        ledger.close()


def test_started_without_result_requeues_instead_of_rerunning_same_attempt(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    broker = FakeBroker()
    try:
        ledger.put_task(_task("ELY-TASK-900004"))
        assert ledger.claim("ELY-TASK-900004", "ollama-worker", now=NOW).claimed
        assert ledger.record_bridge_started("ELY-TASK-900004", "ollama-worker", now=NOW)

        result = run_via_broker(ledger, "ELY-TASK-900004", "ollama-worker", broker=broker, now=NOW)
        assert result.state == "unknown_requeued"
        assert broker.calls == []
        assert ledger.get("ELY-TASK-900004")["status"] == "queued"

        # A new claim is the authoritative new attempt and clears current bridge state.
        assert ledger.claim("ELY-TASK-900004", "ollama-worker", now=NOW).claimed
        row = ledger.get("ELY-TASK-900004")
        assert row["attempt"] == 2
        assert row["bridge_status"] is None
    finally:
        ledger.close()



def _load_isolated_router_module(monkeypatch):
    """Load router/rules.py without importing project_guardian.__init__."""
    root = Path(__file__).resolve().parents[2]
    package_names = (
        "_bridge_router_testpkg",
        "_bridge_router_testpkg.orchestration",
        "_bridge_router_testpkg.orchestration.router",
    )
    for name in package_names:
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, module)

    ollama = types.ModuleType("_bridge_router_testpkg.ollama_model_config")
    ollama.ollama_provider_ref = lambda: "ollama:mistral:7b"
    monkeypatch.setitem(sys.modules, ollama.__name__, ollama)

    def load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    orchestration = root / "project_guardian" / "orchestration"
    task_types = load(
        "_bridge_router_testpkg.orchestration.router.task_types",
        orchestration / "router" / "task_types.py",
    )
    assert "reasoning" in task_types.TASK_TYPES
    type_module = load(
        "_bridge_router_testpkg.orchestration.types",
        orchestration / "types.py",
    )
    rules = load(
        "_bridge_router_testpkg.orchestration.router.rules",
        orchestration / "router" / "rules.py",
    )
    return rules, type_module


def test_local_only_router_rule_cannot_select_openai(monkeypatch):
    rules, type_module = _load_isolated_router_module(monkeypatch)
    monkeypatch.setattr(rules, "_openai_available", lambda: True)
    raw = {
        "orchestration": {"enabled": True},
        "defaults": {
            "pipeline": "serial_plan_execute_review",
            "planner_model": "openai:gpt-planner",
            "executor_model": "openai:gpt-executor",
            "reviewer_model": "openai:gpt-reviewer",
        },
        "routes": {
            "reasoning": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "openai:gpt-planner",
                "executor_model": "openai:gpt-executor",
                "reviewer_model": "openai:gpt-reviewer",
            }
        },
    }
    request = type_module.TaskRequest(
        task_id="ELY-TASK-900005",
        task_type="reasoning",
        prompt="diagnose synthetic pytest output",
        metadata={"local_only": True},
    )
    route = asyncio.run(rules.RulesRouter(raw).resolve(request))
    assert route.planner_model.startswith("ollama:")
    assert route.executor_model.startswith("ollama:")
    assert route.reviewer_model is None
    assert route.judge_model is None
    assert all(model.startswith("ollama:") for model in route.fanout_models)
    assert "local_only" in route.reason
