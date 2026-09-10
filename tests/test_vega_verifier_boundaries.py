"""Independent safety falsification for PR #15; synthetic SQLite only."""
from datetime import datetime, timedelta, timezone

import pytest

from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.dryrun_orchestrator import validate_and_apply_completion
from elysia_collective_seed.autopilot.task_ledger import TaskLedger

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def open_ledger(path):
    return TaskLedger(path, verification_workers=[
        Worker("reviewer", "synthetic", frozenset({"verification"}), frozenset({"repo_write"}))
    ], independence_groups={"writer": "a", "writer-b": "b", "reviewer": "c"})


def task(**overrides):
    result = dict(task_id="vega", status="queued", title="Synthetic write",
                  objective="Test only", risk_class="repo_write", max_attempts=1,
                  human_approval_required=False, required_capabilities=["verification"],
                  acceptance_criteria=["independent verification"], source_refs=["synthetic:test"])
    result.update(overrides)
    return result


@pytest.mark.parametrize("expired", [False, True])
def test_execution_budget_survives_reopen(tmp_path, expired):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    ledger.put_task(task())
    assert ledger.claim("vega", "writer", lease_seconds=1, now=NOW).claimed
    if not expired:
        assert ledger.release("vega", "writer", now=NOW)
    ledger.close()
    ledger = open_ledger(path)
    try:
        second = ledger.claim("vega", "writer-b", now=NOW + timedelta(seconds=2))
        assert not second.claimed, f"max_attempts=1 bypassed: {second}; attempt={ledger.get('vega')['attempt']}"
    finally:
        ledger.close()


def test_rejection_ceiling_cannot_be_raised_after_reopen(tmp_path):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    ledger.put_task(task(max_attempts=3))
    try:
        for index, ceiling in enumerate((2, 9999)):
            assert ledger.claim("vega", "writer", now=NOW).claimed
            assert ledger.submit_for_verification("vega", "writer", f"packet-{index}", ["artifact:synthetic"], now=NOW)
            assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
            ledger.reject_verification("vega", "reviewer", "failure", [], max_rejections=ceiling, now=NOW)
            ledger.close()
            ledger = open_ledger(path)
        state = ledger.get("vega")
        assert state["status"] != "queued", f"Caller raised established ceiling: {state}"
    finally:
        ledger.close()


def test_producer_cannot_release_write_directly_to_completed(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        ledger.release("vega", "writer", next_status="completed", now=NOW)
        assert ledger.get("vega")["status"] != "completed", ledger.events("vega")
    finally:
        ledger.close()


def test_validated_completion_reaches_independent_verifier(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer").claimed
        packet = dict(task_id="vega", packet_id="packet-1", evidence_refs=["artifact:synthetic"],
                      worker={"provider": "synthetic", "role": "engineer"}, outcome="completed",
                      summary="Synthetic result", checks=[{"name": "unit", "result": "pass"}],
                      next_recommendation={"action": "verify"})
        result = validate_and_apply_completion(ledger, packet, worker_id="writer", required_checks=("unit",))
        assert result.applied, result
        claim = ledger.claim_verification("vega", "reviewer")
        assert claim.claimed, f"Completion cannot reach verifier: {claim}; row={ledger.get('vega')}"
        assert ledger.get("vega")["produced_by"] == "writer"
        from tests.evidence_fixture import attest_local_submission
        digest = attest_local_submission(ledger, "vega", tmp_path)
        assert ledger.accept_verification(
            "vega", "reviewer", ["artifact:synthetic", "synthetic:review"],
            expected_submission_digest=digest,
        )
    finally:
        ledger.close()


def test_rerouted_retry_refuses_old_producer_and_current_self_review(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(max_attempts=2))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification("vega", "writer", "packet-1", ["artifact:first"], now=NOW)
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        assert ledger.reject_verification("vega", "reviewer", "retry", [], now=NOW)
        assert ledger.claim("vega", "writer-b", now=NOW).claimed
        assert not ledger.submit_for_verification("vega", "writer", "stale", [], now=NOW)
        assert ledger.submit_for_verification("vega", "writer-b", "packet-2", ["artifact:second"], now=NOW)
        assert ledger.claim_verification("vega", "writer-b", now=NOW).reason == "self_verification_forbidden"
        submissions = [e for e in ledger.events("vega") if e["event_type"] == "producer_completion_submitted"]
        assert [(e["actor"], e["detail"]["evidence_refs"]) for e in submissions] == [("writer", ["artifact:first"]), ("writer-b", ["artifact:second"])]
    finally:
        ledger.close()
