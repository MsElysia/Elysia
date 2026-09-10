from pathlib import Path

from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.dryrun_orchestrator import dispatch_and_claim, validate_and_apply_completion
from elysia_collective_seed.autopilot.task_ledger import TaskLedger


def _task(task_id="ELY-TASK-DRY-001", **overrides):
    task = {
        "task_id": task_id,
        "title": "Dry-run task",
        "objective": "Verify deterministic orchestration",
        "task_class": "code",
        "risk_class": "sandbox_write",
        "status": "queued",
        "dependencies": [],
        "required_capabilities": [],
        "allowed_workers": ["worker-a"],
        "acceptance_criteria": ["claimed exactly once"],
        "source_refs": ["github:#8"],
        "attempt": 0,
        "max_attempts": 3,
        "human_approval_required": False,
    }
    task.update(overrides)
    return task


def _workers():
    return [Worker(worker_id="worker-a", provider="dryrun", capabilities=frozenset({"code"}), risk_classes=frozenset({"read_only", "sandbox_write", "repo_write"}))]


def _completion(outcome="completed", **overrides):
    packet = {
        "task_id": "ELY-TASK-DRY-001",
        "worker": {"provider": "dryrun", "role": "engineer"},
        "outcome": outcome,
        "summary": "bounded dry-run result",
        "checks": [{"name": "unit", "result": "pass"}],
        "next_recommendation": {"action": "verify" if outcome == "completed" else "continue"},
    }
    packet.update(overrides)
    return packet


def test_dispatch_and_claim_happy_path(tmp_path: Path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        result = dispatch_and_claim(ledger, _task(), {}, _workers(), lease_seconds=60)
        assert result.state == "claimed"
        assert result.worker_id == "worker-a"
        assert result.claim is not None and result.claim.claimed
        persisted = ledger.get("ELY-TASK-DRY-001")
        assert persisted["status"] == "claimed"
        assert persisted["claimed_by"] == "worker-a"
        assert persisted["attempt"] == 1
    finally:
        ledger.close()


def test_human_gate_never_claims(tmp_path: Path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        result = dispatch_and_claim(ledger, _task(human_approval_required=True), {}, _workers())
        assert result.state == "human_gate"
        assert result.claim is None
        assert ledger.get("ELY-TASK-DRY-001")["claimed_by"] is None
    finally:
        ledger.close()


def test_incomplete_dependency_never_claims(tmp_path: Path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        result = dispatch_and_claim(ledger, _task(dependencies=["ELY-DEP-1"]), {"ELY-DEP-1": "queued"}, _workers())
        assert result.state == "blocked"
        assert result.reasons == ("dependencies_incomplete",)
        assert ledger.get("ELY-TASK-DRY-001")["claimed_by"] is None
    finally:
        ledger.close()


def test_existing_active_lease_is_not_stolen(tmp_path: Path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        task = _task()
        ledger.put_task(task)
        first = ledger.claim(task["task_id"], "other-worker", lease_seconds=60)
        assert first.claimed
        result = dispatch_and_claim(ledger, task, {}, _workers(), lease_seconds=60)
        assert result.state == "claim_blocked"
        assert result.claim is not None and result.claim.reason == "active_lease"
        persisted = ledger.get(task["task_id"])
        assert persisted["claimed_by"] == "other-worker"
        assert persisted["attempt"] == 1
    finally:
        ledger.close()


def test_stale_payload_cannot_reopen_completed_task(tmp_path: Path):
    ledger = TaskLedger(
        tmp_path / "ledger.db",
        verification_workers=[Worker("verifier", "dryrun", frozenset({"verification"}), frozenset({"sandbox_write"}))],
        independence_groups={"worker-a": "producer", "verifier": "independent"},
    )
    try:
        task = _task()
        ledger.put_task(task)
        assert ledger.claim(task["task_id"], "worker-a", lease_seconds=60).claimed
        assert ledger.submit_for_verification(task["task_id"], "worker-a", "packet:test", ["artifact:test"])
        assert ledger.claim_verification(task["task_id"], "verifier").claimed
        assert ledger.accept_verification(task["task_id"], "verifier", ["artifact:test", "test:review"])
        result = dispatch_and_claim(ledger, task, {}, _workers())
        assert result.state == "not_dispatchable"
        assert result.reasons == ("terminal_task",)
        persisted = ledger.get(task["task_id"])
        assert persisted["status"] == "completed"
        assert persisted["claimed_by"] is None
    finally:
        ledger.close()


def test_completed_worker_report_moves_to_verifying_not_completed(tmp_path: Path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        dispatch_and_claim(ledger, _task(), {}, _workers(), lease_seconds=60)
        result = validate_and_apply_completion(ledger, _completion(), worker_id="worker-a", required_checks=("unit",))
        assert result.applied and result.state == "verifying"
        persisted = ledger.get("ELY-TASK-DRY-001")
        assert persisted["status"] == "verifying"
        assert persisted["claimed_by"] is None
    finally:
        ledger.close()


def test_completion_from_non_owner_cannot_mutate_task(tmp_path: Path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        dispatch_and_claim(ledger, _task(), {}, _workers(), lease_seconds=60)
        result = validate_and_apply_completion(ledger, _completion(), worker_id="worker-b")
        assert not result.applied
        assert result.reasons == ("lease_owner_mismatch",)
        assert ledger.get("ELY-TASK-DRY-001")["status"] == "claimed"
    finally:
        ledger.close()


def test_invalid_completion_cannot_mutate_task(tmp_path: Path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        dispatch_and_claim(ledger, _task(), {}, _workers(), lease_seconds=60)
        result = validate_and_apply_completion(ledger, _completion(checks=[{"name": "unit", "result": "fail"}]), worker_id="worker-a")
        assert not result.applied
        assert "completed_with_failed_check" in result.reasons
        assert ledger.get("ELY-TASK-DRY-001")["status"] == "claimed"
    finally:
        ledger.close()


def test_partial_and_failed_work_return_to_queue(tmp_path: Path):
    for outcome in ("partial", "failed"):
        ledger = TaskLedger(tmp_path / f"{outcome}.db")
        try:
            dispatch_and_claim(ledger, _task(), {}, _workers(), lease_seconds=60)
            result = validate_and_apply_completion(ledger, _completion(outcome=outcome), worker_id="worker-a")
            assert result.applied and result.state == "queued"
            assert ledger.get("ELY-TASK-DRY-001")["claimed_by"] is None
        finally:
            ledger.close()
