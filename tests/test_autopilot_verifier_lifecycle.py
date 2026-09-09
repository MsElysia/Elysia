"""Executable acceptance contract for AUTOPILOT-004 verifier ledger lifecycle.

These tests are local-only and intentionally drive the remaining implementation.
They grant no provider, merge, deploy, external-write, credential, or private-data authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from elysia_collective_seed.autopilot.task_ledger import TaskLedger

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def _claimed_writer(ledger: TaskLedger, task_id: str = "write-1") -> None:
    ledger.put_task({"task_id": task_id, "status": "queued", "title": "bounded local write"})
    assert ledger.claim(task_id, "writer", now=NOW).claimed


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
        claimed = ledger.claim_verification("write-1", "verifier-a", now=NOW)
        assert claimed.claimed
        competing = ledger.claim_verification("write-1", "verifier-b", now=NOW)
        assert not competing.claimed
    finally:
        ledger.close()


def test_accept_requires_live_owner_and_records_decision(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:test"], now=NOW)
        ledger.claim_verification("write-1", "verifier-a", lease_seconds=60, now=NOW)
        assert not ledger.accept_verification("write-1", "verifier-b", ["review:wrong"], now=NOW)
        assert not ledger.accept_verification("write-1", "verifier-a", ["review:stale"], now=NOW + timedelta(seconds=61))
        assert ledger.accept_verification("write-1", "verifier-a", ["review:ok"], now=NOW + timedelta(seconds=30))
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
        ledger.claim_verification("write-1", "verifier-a", now=NOW)
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
    """A rejected write may be rerouted, but the new attempt must own its submission.

    AUTOPILOT-004 explicitly requires failed workers to be reroutable.  This test
    prevents the task-level ``produced_by`` field from permanently binding every
    future attempt to the first producer.  Historical producer evidence must remain
    reconstructable in the event stream while the new worker becomes the producer
    of the retry it actually performed.
    """
    ledger = TaskLedger(tmp_path / "ledger.sqlite3")
    try:
        _claimed_writer(ledger)
        assert ledger.submit_for_verification("write-1", "writer", "packet-1", ["evidence:first"], now=NOW)
        assert ledger.claim_verification("write-1", "verifier-a", now=NOW).claimed
        assert ledger.reject_verification(
            "write-1", "verifier-a", "needs revision", ["review:first-fail"], max_rejections=3, now=NOW
        )

        retry_time = NOW + timedelta(minutes=1)
        retry = ledger.claim("write-1", "writer-b", now=retry_time)
        assert retry.claimed
        assert ledger.submit_for_verification(
            "write-1", "writer-b", "packet-2", ["evidence:retry"], now=retry_time
        )

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
        ledger.claim_verification("write-1", "verifier-a", lease_seconds=60, now=NOW)
        assert ledger.reap_expired_verification(now=NOW + timedelta(seconds=61)) == ["write-1"]
        row = ledger.conn.execute("SELECT * FROM tasks WHERE task_id='write-1'").fetchone()
        assert row["status"] == "verifying"
        assert row["attempt"] == attempt
        assert row["produced_by"] == "writer"
        assert row["completion_packet_id"] == "packet-1"
        assert ledger.claim_verification("write-1", "verifier-b", now=NOW + timedelta(seconds=62)).claimed
    finally:
        ledger.close()
