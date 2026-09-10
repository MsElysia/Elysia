"""Regression tests for issues #19, #20 and #21; local SQLite only."""
from datetime import timedelta

import pytest

from tests.test_vega_verifier_boundaries import NOW, open_ledger, task
from elysia_collective_seed.autopilot.dryrun_orchestrator import validate_and_apply_completion


@pytest.mark.parametrize("risk", ["repo_write", "sandbox_write", "deployment", None])
def test_release_cannot_complete_write_or_unknown_risk(tmp_path, risk):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(risk_class=risk))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert not ledger.release("vega", "writer", "completed", now=NOW)
        assert ledger.get("vega")["status"] == "claimed"
        assert not any(e["event_type"] == "verification_accepted" for e in ledger.events("vega"))
    finally:
        ledger.close()


def test_read_only_release_requires_live_lease_and_no_review_gate(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(risk_class="read_only", required_capabilities=[]))
        assert ledger.claim("vega", "writer", lease_seconds=10, now=NOW).claimed
        assert not ledger.release("vega", "writer", "completed", now=NOW + timedelta(seconds=10))
        assert ledger.release("vega", "writer", "completed", now=NOW + timedelta(seconds=1))
    finally:
        ledger.close()


def test_upsert_cannot_downgrade_write_or_mark_queued_task_complete(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        ledger.put_task(task(risk_class="read_only", required_capabilities=[], status="completed"))
        assert ledger.get("vega")["status"] == "queued"
        assert ledger.get("vega")["risk_class"] == "repo_write"
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert not ledger.release("vega", "writer", "completed", now=NOW)
    finally:
        ledger.close()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "3", None])
def test_invalid_execution_policy_rejected_at_admission(tmp_path, limit):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        with pytest.raises(ValueError):
            ledger.put_task(task(max_attempts=limit))
        assert ledger.get("vega") is None
    finally:
        ledger.close()


def test_policy_cannot_be_raised_by_upsert_after_reopen(tmp_path):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    ledger.put_task(task())
    assert ledger.claim("vega", "writer", now=NOW).claimed
    assert ledger.release("vega", "writer", now=NOW)
    ledger.close()
    ledger = open_ledger(path)
    try:
        ledger.put_task(task(max_attempts=9999, attempt=0))
        assert ledger.get("vega")["max_attempts"] == 1
        assert ledger.get("vega")["status"] == "human_review"
        assert not ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.get("vega")["attempt"] == 1
    finally:
        ledger.close()


def test_concurrent_expired_reclaims_cannot_exceed_budget(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    ledger.put_task(task())
    assert ledger.claim("vega", "writer", lease_seconds=1, now=NOW).claimed
    ledger.close()
    barrier = Barrier(2)

    def reclaim(worker):
        other = open_ledger(path)
        try:
            barrier.wait(timeout=5)
            return other.claim("vega", worker, now=NOW + timedelta(seconds=2)).claimed
        finally:
            other.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(reclaim, ("worker-a", "worker-b"))) == [False, False]
    ledger = open_ledger(path)
    try:
        assert ledger.get("vega")["attempt"] == 1
        assert ledger.get("vega")["status"] == "human_review"
        assert sum(e["event_type"] == "retry_budget_exhausted" for e in ledger.events("vega")) == 1
    finally:
        ledger.close()


@pytest.mark.parametrize("caller_limit", [0, 1, 9999, None])
def test_rejection_uses_system_policy_regardless_of_caller(tmp_path, caller_limit):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(max_attempts=3))
        for index in range(2):
            assert ledger.claim("vega", "writer", now=NOW).claimed
            assert ledger.submit_for_verification("vega", "writer", str(index), [], now=NOW)
            assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
            assert ledger.reject_verification("vega", "reviewer", "failure", [], max_rejections=caller_limit, now=NOW)
            assert ledger.get("vega")["status"] == ("queued" if index == 0 else "human_review")
        assert ledger.get("vega")["attempt"] == 2
    finally:
        ledger.close()


def completion(**overrides):
    packet = dict(task_id="vega", worker={"provider": "synthetic", "role": "engineer"},
                  summary="Synthetic result", outcome="completed",
                  checks=[{"name": "unit", "result": "pass"}],
                  next_recommendation={"action": "verify"})
    packet.update(overrides)
    return packet


def test_bridge_persists_identity_evidence_and_lease_provenance_across_reopen(tmp_path):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    ledger.put_task(task(required_checks=["unit"]))
    assert ledger.claim("vega", "writer").claimed
    lease = ledger.get("vega")["lease_expires_at"]
    packet = completion(packet_id="packet-explicit", evidence_refs=["ref:direct"],
                        claims=[{"claim": "tested", "evidence": ["ref:claim"]}])
    assert validate_and_apply_completion(ledger, packet, worker_id="writer").applied
    ledger.close()
    ledger = open_ledger(path)
    try:
        row = ledger.get("vega")
        assert row["produced_by"] == "writer"
        assert row["completion_packet_id"] == "packet-explicit"
        assert {"ref:direct", "ref:claim"}.issubset(row["completion_evidence"])
        event = ledger.events("vega")[-1]
        assert event["detail"]["checks"] == [{"name": "unit", "result": "pass"}]
        assert event["detail"]["attempt"] == 1
        assert event["detail"]["producer_lease_expires_at"] == lease
        assert ledger.claim_verification("vega", "reviewer").claimed
        assert ledger.accept_verification("vega", "reviewer", ["ref:review"])
    finally:
        ledger.close()


def test_legacy_packet_gets_stable_content_identity(tmp_path):
    import hashlib
    import json

    packet = completion()
    expected = "sha256:" + hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer").claimed
        assert validate_and_apply_completion(ledger, packet, worker_id="writer").applied
        assert ledger.get("vega")["completion_packet_id"] == expected
        assert expected in ledger.get("vega")["completion_evidence"]
    finally:
        ledger.close()


@pytest.mark.parametrize("changes", [{"packet_id": ""}, {"evidence_refs": "bad"},
                                     {"claims": [{"claim": "missing evidence"}]}, {"checks": []}])
def test_bridge_rejects_malformed_evidence_and_cannot_omit_task_checks(tmp_path, changes):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(required_checks=["unit"]))
        assert ledger.claim("vega", "writer").claimed
        before = ledger.events("vega")
        assert not validate_and_apply_completion(ledger, completion(**changes), worker_id="writer").applied
        assert ledger.get("vega")["status"] == "claimed"
        assert ledger.events("vega") == before
    finally:
        ledger.close()


def test_bridge_refuses_expired_producer_lease(tmp_path, monkeypatch):
    import elysia_collective_seed.autopilot.task_ledger as ledger_module

    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", lease_seconds=1, now=NOW).claimed
        monkeypatch.setattr(ledger_module, "_utcnow", lambda: NOW + timedelta(seconds=1))
        before = ledger.events("vega")
        assert not validate_and_apply_completion(ledger, completion(), worker_id="writer").applied
        assert ledger.get("vega")["produced_by"] is None
        assert ledger.events("vega") == before
    finally:
        ledger.close()


def test_legacy_policy_migration_is_durable_and_preserves_events(tmp_path):
    from tests.test_autopilot_verifier_ledger_migration import _legacy_ledger

    path = tmp_path / "legacy.db"
    _legacy_ledger(path)
    ledger = open_ledger(path)
    try:
        assert ledger.get("legacy-task")["max_attempts"] == 3
        assert ledger.claim("legacy-task", "writer", now=NOW).claimed
        assert ledger.release("legacy-task", "writer", now=NOW)
    finally:
        ledger.close()
    ledger = open_ledger(path)
    try:
        assert ledger.get("legacy-task")["status"] == "human_review"
        assert ledger.get("legacy-task")["attempt"] == 3
        assert ledger.events("legacy-task")[0]["detail"] == {"proof": "keep"}
        assert not ledger.claim("legacy-task", "writer", now=NOW).claimed
    finally:
        ledger.close()
