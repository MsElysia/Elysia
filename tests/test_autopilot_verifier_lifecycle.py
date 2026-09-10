"""Executable acceptance contract for AUTOPILOT-004 verifier ledger lifecycle.

These tests are local-only and intentionally drive the remaining implementation.
They grant no provider, merge, deploy, external-write, credential, or private-data authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.task_ledger import TaskLedger

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _claimed_writer(ledger: TaskLedger, task_id: str = "write-1") -> None:
    if not ledger.verification_workers:
        ledger.verification_workers = {
            worker_id: Worker(
                worker_id,
                "test",
                frozenset({"verification"}),
                frozenset({"repo_write"}),
                quality=1.0 if worker_id == "verifier-a" else 0.9,
            )
            for worker_id in ("verifier-a", "verifier-b")
        }
        ledger.independence_groups = {
            "writer": "producer-group",
            "writer-b": "producer-b-group",
            "verifier-a": "verifier-group-a",
            "verifier-b": "verifier-group-b",
        }
    ledger.put_task({
        "task_id": task_id,
        "status": "queued",
        "title": "bounded local write",
        "objective": "change only the approved local repository scope",
        "risk_class": "repo_write",
        "required_capabilities": ["verification"],
        "human_approval_required": False,
        "source_refs": ["issue:#17"],
        "acceptance_criteria": ["tests pass"],
    })
    assert ledger.claim(task_id, "writer", now=NOW).claimed


def _claim_verification(ledger: TaskLedger, verifier_worker_id: str, **kwargs):
    return ledger.claim_verification("write-1", verifier_worker_id, **kwargs)


def test_writer_submission_enters_verifying_and_releases_execution_lease(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        assert ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:test"], now=NOW)
        row = ledger.conn.execute("SELECT * FROM tasks WHERE task_id='write-1'").fetchone()
        assert row["status"] == "verifying"
        assert row["claimed_by"] is None and row["lease_expires_at"] is None
        assert row["produced_by"] == "writer"
        assert row["completion_packet_id"] == "packet-1"
        assert not ledger.claim("write-1", "writer", now=NOW).claimed
        assert ledger.events("write-1")[-1]["event_type"] == "producer_completion_submitted"
    finally:
        ledger.close()


def test_self_verification_forbidden_and_distinct_verifier_claims(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:test"], now=NOW)
        denied = ledger.claim_verification("write-1", "writer", now=NOW)
        assert not denied.claimed and denied.reason == "self_verification_forbidden"
        claimed = _claim_verification(ledger, "verifier-a", now=NOW)
        assert claimed.claimed
        competing = _claim_verification(ledger, "verifier-b", now=NOW)
        assert not competing.claimed
    finally:
        ledger.close()


def test_accept_requires_live_owner_and_records_decision(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:test"], now=NOW)
        _claim_verification(ledger, "verifier-a", lease_seconds=60, now=NOW)
        assert not ledger.accept_verification("write-1", "verifier-b", ["review:wrong"], now=NOW)
        assert not ledger.accept_verification("write-1", "verifier-a", ["review:stale"], now=NOW + timedelta(seconds=61))
        assert ledger.reap_expired_verification(now=NOW + timedelta(seconds=61)) == ["write-1"]
        ledger.verification_workers["verifier-a"] = Worker(
            "verifier-a", "test", frozenset({"verification"}), frozenset({"repo_write"}),
            available=False, quality=1.0,
        )
        assert _claim_verification(ledger, "verifier-b", lease_seconds=60, now=NOW + timedelta(seconds=62)).claimed
        from tests.evidence_fixture import attest_local_submission
        digest = attest_local_submission(ledger, "write-1", tmp_path)
        assert ledger.accept_verification("write-1", "verifier-b", ["review:ok"], now=NOW + timedelta(seconds=63), expected_submission_digest=digest)
        row = ledger.conn.execute("SELECT * FROM tasks WHERE task_id='write-1'").fetchone()
        assert row["status"] == "completed"
        assert row["verification_claimed_by"] is None
        assert ledger.events("write-1")[-1]["event_type"] == "verification_accepted"
    finally:
        ledger.close()


def test_rejection_preserves_evidence_and_attempt_and_bounds_retry(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        attempt = ledger.get("write-1")["attempt"]
        ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:test"], now=NOW)
        _claim_verification(ledger, "verifier-a", now=NOW)
        assert ledger.reject_verification("write-1", "verifier-a", "test failure", ["review:fail"], max_rejections=2, now=NOW)
        row = ledger.conn.execute("SELECT * FROM tasks WHERE task_id='write-1'").fetchone()
        assert row["status"] == "queued"
        assert row["attempt"] == attempt
        assert row["completion_packet_id"] == "packet-1"
        assert "evidence:test" in row["completion_evidence_json"]
        assert row["verification_rejections"] == 1
    finally:
        ledger.close()


def test_rejected_retry_can_be_rerouted_without_losing_producer_provenance(tmp_path):
    """A rejected write may be rerouted, but the new attempt must own its submission."""
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        assert ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:first"], now=NOW)
        assert _claim_verification(ledger, "verifier-a", now=NOW).claimed
        assert ledger.reject_verification(
            "write-1", "verifier-a", "needs revision", ["review:first-fail"], max_rejections=3, now=NOW
        )
        retry_time = NOW + timedelta(minutes=1)
        retry = ledger.claim("write-1", "writer-b", now=retry_time)
        assert retry.claimed
        assert ledger.submit_for_verification("write-1", "writer-b", "packet-2", ["evidence:retry"], now=retry_time)
        row = ledger.conn.execute("SELECT * FROM tasks WHERE task_id='write-1'").fetchone()
        assert row["status"] == "verifying"
        assert row["produced_by"] == "writer-b"
        assert row["completion_packet_id"] == "packet-2"
        events = ledger.events("write-1")
        first_submission = next(e for e in events if e["event_type"] == "producer_completion_submitted")
        assert first_submission["actor"] == "writer"
        assert first_submission["detail"]["packet_id"] == "packet-1"
        assert events[-1]["event_type"] == "producer_completion_submitted"
        assert events[-1]["actor"] == "writer-b"
        assert events[-1]["detail"]["packet_id"] == "packet-2"
    finally:
        ledger.close()


def test_expired_verifier_lease_reaps_without_touching_producer_evidence(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        attempt = ledger.get("write-1")["attempt"]
        ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:test"], now=NOW)
        _claim_verification(ledger, "verifier-a", lease_seconds=60, now=NOW)
        assert ledger.reap_expired_verification(now=NOW + timedelta(seconds=61)) == ["write-1"]
        row = ledger.conn.execute("SELECT * FROM tasks WHERE task_id='write-1'").fetchone()
        assert row["status"] == "verifying"
        assert row["attempt"] == attempt
        assert row["produced_by"] == "writer"
        assert row["completion_packet_id"] == "packet-1"
        ledger.verification_workers["verifier-a"] = Worker(
            "verifier-a",
            "test",
            frozenset({"verification"}),
            frozenset({"repo_write"}),
            available=False,
            quality=1.0,
        )
        assert _claim_verification(ledger, "verifier-b", now=NOW + timedelta(seconds=62)).claimed
    finally:
        ledger.close()


def test_verification_claim_requires_atomic_independence_decision(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:test"], now=NOW)

        ledger.independence_groups["verifier-a"] = "producer-group"
        denied = ledger.claim_verification("write-1", "verifier-a", now=NOW)
        assert not denied.claimed and denied.reason == "verifier_not_independent"

        del ledger.independence_groups["verifier-a"]
        denied = ledger.claim_verification("write-1", "verifier-a", now=NOW)
        assert not denied.claimed and denied.reason == "verifier_not_independent"

        ledger.independence_groups["verifier-a"] = "verifier-group-a"
        assert _claim_verification(ledger, "verifier-a", now=NOW).claimed
    finally:
        ledger.close()


def test_claim_rechecks_current_registry_eligibility(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:first"], now=NOW)
        ledger.verification_workers["verifier-a"] = Worker(
            "verifier-a",
            "test",
            frozenset({"verification"}),
            frozenset({"repo_write"}),
            available=False,
        )
        denied = ledger.claim_verification("write-1", "verifier-a", now=NOW)
        assert not denied.claimed and denied.reason == "verifier_not_independent"
    finally:
        ledger.close()


def test_claim_enforces_task_specific_capability_and_risk(tmp_path):
    worker = Worker(
        "verifier-a", "test", frozenset({"verification"}), frozenset({"repo_write"}), quality=1.0
    )
    ledger = TaskLedger(
        tmp_path / "ledger.sqlite3",
        verification_workers=[worker],
        independence_groups={"writer": "producer-group", "verifier-a": "verifier-group"},
    )
    try:
        ledger.put_task({
            "task_id": "write-1",
            "status": "queued",
            "title": "specialized write",
            "risk_class": "sandbox_write",
            "required_capabilities": ["specialized_review"],
        })
        assert ledger.claim("write-1", "writer", now=NOW).claimed
        assert ledger.submit_for_verification("write-1", "writer", "packet-1", [], now=NOW)
        denied = ledger.claim_verification("write-1", "verifier-a", now=NOW)
        assert not denied.claimed and denied.reason == "verifier_not_independent"
    finally:
        ledger.close()


def test_exhausted_retries_route_to_human_review_without_expanding_authority(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = TaskLedger(path)
    try:
        _claimed_writer(ledger)
        original_payload = dict(ledger.get("write-1"))
        assert ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:one"], now=NOW)
        assert _claim_verification(ledger, "verifier-a", now=NOW).claimed
        assert ledger.reject_verification("write-1", "verifier-a", "retry", ["review:one"], max_rejections=2, now=NOW)

        retry_time = NOW + timedelta(minutes=1)
        assert ledger.claim("write-1", "writer-b", now=retry_time).claimed
        assert ledger.submit_for_verification("write-1", "writer-b", "packet-2", ["evidence:two"], now=retry_time)
        assert _claim_verification(ledger, "verifier-a", now=retry_time).claimed
        assert ledger.reject_verification("write-1", "verifier-a", "still unsafe", ["review:two"], max_rejections=2, now=retry_time)

        final = ledger.get("write-1")
        assert final["status"] == "human_review"
        for protected_field in ("title", "risk_class", "human_approval_required", "source_refs"):
            assert final.get(protected_field) == original_payload.get(protected_field)
        assert [event["event_type"] for event in ledger.events("write-1")].count("verification_rejected") == 2
    finally:
        ledger.close()

    reopened = TaskLedger(path)
    try:
        assert reopened.get("write-1")["status"] == "human_review"
        submissions = [
            event for event in reopened.events("write-1")
            if event["event_type"] == "producer_completion_submitted"
        ]
        assert [(event["actor"], event["detail"]["packet_id"]) for event in submissions] == [
            ("writer", "packet-1"),
            ("writer-b", "packet-2"),
        ]
    finally:
        reopened.close()
