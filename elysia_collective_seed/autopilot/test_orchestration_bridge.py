from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
from typing import Any
from unittest.mock import Mock

import pytest

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

# Issue #83: broker identity must be validated before any result side effect.


class HostileTaskId(str):
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __str__(self):
        raise AssertionError('task identity must not be coerced')


class ThrowingTaskId(str):
    def __eq__(self, other):
        raise AssertionError('task identity must not be compared')

    def __ne__(self, other):
        raise AssertionError('task identity must not be compared')


@pytest.mark.parametrize('identity', [
    'ELY-TASK-UNRELATED', '', ' ', None, False, 42, [], {},
    HostileTaskId('ELY-TASK-UNRELATED'), HostileTaskId('ELY-TASK-900001'),
    ThrowingTaskId('ELY-TASK-900001'),
], ids=['wrong-task', 'empty', 'whitespace', 'null', 'bool', 'int', 'list', 'dict',
        'spoofed-subclass', 'matching-subclass', 'throwing-subclass'])
def test_invalid_broker_identity_has_zero_downstream_mutation(tmp_path, monkeypatch, identity):
    from elysia_collective_seed.autopilot import orchestration_bridge as bridge

    ledger = TaskLedger(tmp_path / 'ledger.db')
    returned = FakePipelineResult(identity, 'serial_plan_execute_review', True,
                                  'WRONG_TASK_OUTPUT_SENTINEL')
    before_return = []

    class Broker:
        def run_task_sync(self, request):
            assert request.task_id == 'ELY-TASK-900001'
            before_return.append(list(ledger.conn.iterdump()))
            return returned

    capture = Mock(side_effect=AssertionError('capture must not be called'))
    packet = Mock(side_effect=AssertionError('completion packet must not be built'))
    submit = Mock(side_effect=AssertionError('verification must not be called'))
    monkeypatch.setattr(ledger, 'capture_bridge_result', capture)
    monkeypatch.setattr(bridge, '_completion_packet', packet)
    monkeypatch.setattr(ledger, 'submit_for_verification', submit)
    try:
        ledger.put_task(_task())
        assert ledger.claim('ELY-TASK-900001', 'producer', now=NOW).claimed
        result = run_via_broker(ledger, 'ELY-TASK-900001', 'producer', broker=Broker(), now=NOW)
        assert not result.submitted
        assert result.error == 'broker_task_identity_mismatch'
        assert result.result_digest is None
        assert returned.task_id is identity  # no relabeling of the result
        capture.assert_not_called()
        packet.assert_not_called()
        submit.assert_not_called()
        assert list(ledger.conn.iterdump()) == before_return[0]
        assert 'WRONG_TASK_OUTPUT_SENTINEL' not in '\n'.join(ledger.conn.iterdump())
        assert ledger.get_bridge_receipt('ELY-TASK-900001') is None
        assert ledger.get('ELY-TASK-900001')['completion_submission'] is None
    finally:
        ledger.close()


def test_missing_identity_is_rejected_before_any_other_result_field(tmp_path):
    class IdentitylessResult:
        @property
        def pipeline_id(self):
            raise AssertionError('receipt construction began before identity validation')

    class Broker:
        def run_task_sync(self, request):
            return IdentitylessResult()

    ledger = TaskLedger(tmp_path / 'ledger.db')
    try:
        ledger.put_task(_task())
        assert ledger.claim('ELY-TASK-900001', 'producer', now=NOW).claimed
        result = run_via_broker(ledger, 'ELY-TASK-900001', 'producer', broker=Broker(), now=NOW)
        assert result.error == 'broker_task_identity_mismatch'
        assert ledger.get_bridge_receipt('ELY-TASK-900001') is None
    finally:
        ledger.close()


def test_rejected_identity_reopens_without_capture_and_recovers_new_attempt(tmp_path):
    path = tmp_path / 'ledger.db'
    ledger = TaskLedger(path)
    broker = FakeBroker()
    broker.run_task_sync = lambda request: FakePipelineResult(
        'task-B', 'serial_plan_execute_review', True, 'task-B-only-output')
    ledger.put_task(_task())
    assert ledger.claim('ELY-TASK-900001', 'producer', now=NOW).claimed
    assert not run_via_broker(ledger, 'ELY-TASK-900001', 'producer', broker=broker, now=NOW).submitted
    ledger.close()
    ledger = TaskLedger(path)
    try:
        assert ledger.get_bridge_receipt('ELY-TASK-900001') is None
        assert ledger.get('ELY-TASK-900001')['completion_submission'] is None
        assert 'task-B-only-output' not in '\n'.join(ledger.conn.iterdump())
        broker = FakeBroker()
        recovery = run_via_broker(ledger, 'ELY-TASK-900001', 'producer', broker=broker, now=NOW)
        assert recovery.state == 'unknown_requeued'
        assert broker.calls == []
        assert ledger.claim('ELY-TASK-900001', 'producer', now=NOW).claimed
        assert ledger.get('ELY-TASK-900001')['attempt'] == 2
        assert run_via_broker(ledger, 'ELY-TASK-900001', 'producer', broker=broker, now=NOW).submitted
        assert ledger.get_bridge_receipt('ELY-TASK-900001')['task_id'] == 'ELY-TASK-900001'
        events = [event['event_type'] for event in ledger.events('ELY-TASK-900001')]
        assert events.count('broker_execution_started') == 2
        assert events.count('broker_result_captured') == 1
    finally:
        ledger.close()


def test_matching_identity_broker_failure_keeps_existing_behavior(tmp_path, monkeypatch):
    ledger = TaskLedger(tmp_path / 'ledger.db')
    class Broker:
        def run_task_sync(self, request):
            return FakePipelineResult(request.task_id, 'serial_plan_execute_review',
                                      False, None, error='synthetic failure')
    submit = Mock(side_effect=AssertionError('failed broker must not submit'))
    monkeypatch.setattr(ledger, 'submit_for_verification', submit)
    try:
        ledger.put_task(_task())
        assert ledger.claim('ELY-TASK-900001', 'producer', now=NOW).claimed
        result = run_via_broker(ledger, 'ELY-TASK-900001', 'producer', broker=Broker(), now=NOW)
        assert result.state == 'broker_failed_requeued'
        assert result.error == 'synthetic failure'
        assert result.result_digest is not None
        assert not result.submitted
        assert ledger.get('ELY-TASK-900001')['status'] == 'queued'
        assert ledger.get_bridge_receipt('ELY-TASK-900001')['success'] is False
        submit.assert_not_called()
    finally:
        ledger.close()


@pytest.mark.parametrize('field,value', [
    ('human_approval_required', True), ('required_capabilities', ['execute']),
    ('required_checks', ['check']), ('required_review_roles', ['human']),
])
def test_identity_repair_preserves_authority_refusals(tmp_path, field, value):
    ledger = TaskLedger(tmp_path / 'ledger.db')
    broker = FakeBroker()
    try:
        task = _task()
        task[field] = value
        ledger.put_task(task)
        assert ledger.claim(task['task_id'], 'producer', now=NOW).claimed
        result = run_via_broker(ledger, task['task_id'], 'producer', broker=broker, now=NOW)
        assert not result.submitted
        assert broker.calls == []
        assert ledger.get_bridge_receipt(task['task_id']) is None
    finally:
        ledger.close()

@pytest.mark.parametrize('error_type', [RuntimeError, ValueError, TypeError])
def test_throwing_identity_accessor_has_zero_downstream_mutation(tmp_path, monkeypatch, error_type):
    from elysia_collective_seed.autopilot import orchestration_bridge as bridge

    class Result:
        @property
        def task_id(self):
            raise error_type('malformed identity accessor')

    ledger = TaskLedger(tmp_path / 'ledger.db')
    before_return = []
    class Broker:
        def run_task_sync(self, request):
            before_return.append(list(ledger.conn.iterdump()))
            return Result()

    traps = [Mock(side_effect=AssertionError('downstream mutation')) for _ in range(3)]
    monkeypatch.setattr(ledger, 'capture_bridge_result', traps[0])
    monkeypatch.setattr(bridge, '_completion_packet', traps[1])
    monkeypatch.setattr(ledger, 'submit_for_verification', traps[2])
    try:
        ledger.put_task(_task())
        assert ledger.claim('ELY-TASK-900001', 'producer', now=NOW).claimed
        result = run_via_broker(ledger, 'ELY-TASK-900001', 'producer', broker=Broker(), now=NOW)
        assert not result.submitted
        assert result.error == 'broker_task_identity_mismatch'
        assert result.result_digest is None
        for trap in traps:
            trap.assert_not_called()
        assert list(ledger.conn.iterdump()) == before_return[0]
    finally:
        ledger.close()
