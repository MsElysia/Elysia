from datetime import datetime, timedelta, timezone

import pytest

from elysia_collective_seed.autopilot.task_ledger import LedgerError, Task, TaskLedger, TaskState


def test_dependencies_gate_claim_and_unlock_after_acceptance():
    ledger = TaskLedger()
    ledger.add(Task("A", "first", ["done"] ))
    ledger.add(Task("B", "second", ["done"], dependencies=["A"]))
    assert [t.task_id for t in ledger.ready()] == ["A"]
    with pytest.raises(LedgerError):
        ledger.claim("B", "worker-b")
    lease = ledger.claim("A", "worker-a")
    ledger.start("A", lease.lease_id)
    ledger.submit("A", lease.lease_id, ["artifact:a"])
    assert ledger.tasks["A"].state == TaskState.ACCEPTED
    assert [t.task_id for t in ledger.ready()] == ["B"]


def test_write_task_requires_independent_verifier():
    ledger = TaskLedger()
    ledger.add(Task("W", "write", ["tests pass"], requires_write=True))
    lease = ledger.claim("W", "builder")
    ledger.start("W", lease.lease_id)
    ledger.submit("W", lease.lease_id, ["commit:abc"])
    assert ledger.tasks["W"].state == TaskState.VERIFYING
    with pytest.raises(LedgerError):
        ledger.verify("W", "builder", True, ["self review"])
    ledger.verify("W", "reviewer", True, ["tests:pass"])
    assert ledger.tasks["W"].state == TaskState.ACCEPTED


def test_failed_verification_requeues_without_losing_evidence():
    ledger = TaskLedger()
    ledger.add(Task("W", "write", ["tests pass"], requires_write=True))
    lease = ledger.claim("W", "builder")
    ledger.start("W", lease.lease_id)
    ledger.submit("W", lease.lease_id, ["commit:bad"])
    ledger.verify("W", "reviewer", False, ["test failure"])
    assert ledger.tasks["W"].state == TaskState.QUEUED
    assert "commit:bad" in ledger.tasks["W"].evidence
    assert "test failure" in ledger.tasks["W"].evidence


def test_expired_lease_is_requeued():
    ledger = TaskLedger()
    ledger.add(Task("A", "first", ["done"]))
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    ledger.claim("A", "worker", lease_minutes=5, now=now)
    assert ledger.reap_expired_leases(now + timedelta(minutes=6)) == ["A"]
    assert ledger.tasks["A"].state == TaskState.QUEUED


def test_block_unblock_preserves_reason_in_audit():
    ledger = TaskLedger()
    ledger.add(Task("A", "needs local archive", ["inventory"] ))
    ledger.block("A", "local archive unavailable")
    assert ledger.tasks["A"].state == TaskState.BLOCKED
    ledger.unblock("A")
    assert ledger.tasks["A"].state == TaskState.QUEUED
    assert any(e.get("reason") == "local archive unavailable" for e in ledger.audit)
