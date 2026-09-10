"""Independent Vega executable re-verify probes for reconcile-22 (4e5a55b).

Verification-only; does not change product behavior. Failures indicate a material
bypass of evidence-binding or risk-classification gates.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.task_ledger import (
    TaskLedger,
    _risk_requires_substantive_evidence,
    is_substantive_write_ref,
)
from tests.evidence_fixture import attest_local_submission
from tests.test_vega_verifier_boundaries import NOW, task


def open_ledger(path, risks=None):
    risks = risks or {
        "repo_write",
        "sandbox_write",
        "read_only",
        "unknown_risk",
        "",
        "write",
        "Sandbox_Write",
        "READ_ONLY",
        "Repo_Write",
    }
    return TaskLedger(
        path,
        verification_workers=[
            Worker("reviewer", "synthetic", frozenset({"verification"}), frozenset(risks))
        ],
        independence_groups={"writer": "a", "reviewer": "c"},
    )


def completion(packet_id="packet:A", evidence_refs=None, **extra):
    refs = evidence_refs or ["artifact:A"]
    p = {
        "task_id": "vega",
        "packet_id": packet_id,
        "evidence_refs": refs,
        "worker": {"provider": "synthetic", "role": "engineer"},
        "outcome": "completed",
        "summary": "ok",
        "checks": [{"name": "unit", "result": "pass", "evidence": refs}],
        "next_recommendation": {"action": "verify"},
    }
    p.update(extra)
    return p


# ---- Evidence-binding family ----


def test_unrelated_evidence_refs_cannot_accept(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion()
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:A", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        digest = attest_local_submission(ledger, "vega", tmp_path)
        ok = ledger.accept_verification(
            "vega", "reviewer", ["artifact:B"], now=NOW,
            expected_submission_digest=digest,
        )
        assert not ok and ledger.get("vega")["status"] != "completed"
    finally:
        ledger.close()


def test_conflicting_packet_identity_rejected(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion(packet_id="packet:A")
        submitted = ledger.submit_for_verification(
            "vega", "writer", "packet:B", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        row = ledger.get("vega")
        assert not submitted or row["status"] not in {"verifying", "completed"}
    finally:
        ledger.close()


def test_stale_verifier_lease_cannot_accept(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion()
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:A", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        assert ledger.claim_verification(
            "vega", "reviewer", lease_seconds=60, now=NOW
        ).claimed
        digest = attest_local_submission(ledger, "vega", tmp_path)
        ok = ledger.accept_verification(
            "vega", "reviewer", ["artifact:A", "review:n"],
            now=NOW + timedelta(minutes=5),
            expected_submission_digest=digest,
        )
        assert not ok and ledger.get("vega")["status"] != "completed"
    finally:
        ledger.close()


def test_self_hash_is_not_substantive_repo_write_evidence(tmp_path):
    digest_id = "sha256:" + ("a" * 64)
    assert not is_substantive_write_ref(digest_id, packet_digest=digest_id)
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion(packet_id=digest_id, evidence_refs=[digest_id])
        ledger.submit_for_verification(
            "vega", "writer", digest_id, [digest_id], now=NOW,
            completion_packet=pkt,
            completion_checks=[{"name": "unit", "result": "pass", "evidence": [digest_id]}],
        )
        assert ledger.get("vega")["status"] == "human_review"
    finally:
        ledger.close()


@pytest.mark.parametrize("bad", [[], ["  "], [123], None])
def test_malformed_review_evidence_rejected(tmp_path, bad):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion()
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:A", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        digest = attest_local_submission(ledger, "vega", tmp_path)
        try:
            ok = ledger.accept_verification(
                "vega", "reviewer", bad, now=NOW,
                expected_submission_digest=digest,
            )
        except Exception:
            ok = False
        assert not ok and ledger.get("vega")["status"] != "completed"
    finally:
        ledger.close()


def test_missing_and_wrong_submission_digest_rejected(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion()
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:A", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        digest = attest_local_submission(ledger, "vega", tmp_path)
        assert not ledger.accept_verification(
            "vega", "reviewer", ["artifact:A"], now=NOW,
            expected_submission_digest=None,
        )
        assert not ledger.accept_verification(
            "vega", "reviewer", ["artifact:A"], now=NOW,
            expected_submission_digest="sha256:" + ("0" * 64),
        )
        assert ledger.get("vega")["status"] != "completed"
        # correct digest still works (gates not broken)
        assert ledger.accept_verification(
            "vega", "reviewer", ["artifact:A", "review:ok"], now=NOW,
            expected_submission_digest=digest,
        )
    finally:
        ledger.close()


def test_accept_without_claim_pin_rejected(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion()
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:A", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        digest = attest_local_submission(ledger, "vega", tmp_path)
        ok = ledger.accept_verification(
            "vega", "reviewer", ["artifact:A"], now=NOW,
            expected_submission_digest=digest,
        )
        assert not ok and ledger.get("vega")["status"] != "completed"
    finally:
        ledger.close()


def test_sqlite_reopen_without_validator_fails_closed(tmp_path):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        pkt = completion()
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:A", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        digest = attest_local_submission(ledger, "vega", tmp_path)
    finally:
        ledger.close()

    ledger2 = open_ledger(path)
    try:
        ok = ledger2.accept_verification(
            "vega", "reviewer", ["artifact:A", "review:n"], now=NOW,
            expected_submission_digest=digest,
        )
        assert not ok and ledger2.get("vega")["status"] != "completed"
        # reinstall trusted authority after reopen — legitimate path still holds
        d2 = attest_local_submission(ledger2, "vega", tmp_path)
        assert ledger2.accept_verification(
            "vega", "reviewer", ["artifact:A", "review:n"], now=NOW,
            expected_submission_digest=d2,
        )
        assert ledger2.get("vega")["status"] == "completed"
    finally:
        ledger2.close()


# ---- Risk-classification family ----


@pytest.mark.parametrize(
    "risk",
    ["unknown_risk", "", "write", "Sandbox_Write", "READ_ONLY", "Repo_Write"],
)
def test_non_soft_risk_fails_closed_without_substantive(tmp_path, risk):
    assert _risk_requires_substantive_evidence(risk)
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(risk_class=risk, required_checks=[]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        ledger.submit_for_verification(
            "vega", "writer", "packet:X", ["only-identity"], now=NOW
        )
        row = ledger.get("vega")
        assert row["status"] not in {"verifying", "completed"}, row
        assert row["status"] in {"human_review", "blocked"}
    finally:
        ledger.close()


def test_missing_none_risk_fails_closed_without_substantive(tmp_path):
    assert _risk_requires_substantive_evidence(None)
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(risk_class="repo_write", required_checks=[]))
        payload = json.loads(
            ledger.conn.execute(
                "SELECT payload_json FROM tasks WHERE task_id=?", ("vega",)
            ).fetchone()[0]
        )
        payload["risk_class"] = None
        ledger.conn.execute(
            "UPDATE tasks SET payload_json=? WHERE task_id=?",
            (json.dumps(payload), "vega"),
        )
        ledger.conn.commit()
        assert ledger.claim("vega", "writer", now=NOW).claimed
        ledger.submit_for_verification(
            "vega", "writer", "packet:X", ["only-identity"], now=NOW
        )
        row = ledger.get("vega")
        assert row["status"] not in {"verifying", "completed"}, row
    finally:
        ledger.close()


@pytest.mark.parametrize("risk", ["sandbox_write", "read_only"])
def test_only_explicit_soft_risks_skip_substantive_at_submit(tmp_path, risk):
    assert not _risk_requires_substantive_evidence(risk)
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(risk_class=risk, required_checks=[]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        ledger.submit_for_verification(
            "vega", "writer", "packet:X", ["only-identity"], now=NOW
        )
        row = ledger.get("vega")
        assert row["status"] == "verifying"
        # soft path still needs claim + digest pin to complete
        assert not ledger.accept_verification(
            "vega", "reviewer", ["note:only"], now=NOW,
            expected_submission_digest=row["completion_submission_digest"],
        )
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        digest = row["completion_submission_digest"]
        assert ledger.accept_verification(
            "vega", "reviewer", ["note:only"], now=NOW,
            expected_submission_digest=digest,
        )
        assert ledger.get("vega")["status"] == "completed"
    finally:
        ledger.close()


# ---- Codex repo_write proof / digest / lease ----


def test_repo_write_proof_digest_lease_paths_hold(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(risk_class="repo_write", required_checks=[]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:A", ["note:x"], now=NOW
        )
        assert ledger.get("vega")["status"] == "human_review"

        ledger.put_task(task(task_id="vega2", risk_class="repo_write"))
        assert ledger.claim("vega2", "writer", now=NOW).claimed
        pkt = {
            "task_id": "vega2",
            "packet_id": "packet:A",
            "evidence_refs": ["artifact:A"],
            "worker": {"provider": "synthetic", "role": "engineer"},
            "outcome": "completed",
            "summary": "ok",
            "checks": [{"name": "unit", "result": "pass", "evidence": ["artifact:A"]}],
            "next_recommendation": {"action": "verify"},
        }
        assert ledger.submit_for_verification(
            "vega2", "writer", "packet:A", ["artifact:A"], now=NOW,
            completion_packet=pkt, completion_checks=pkt["checks"],
        )
        assert ledger.get("vega2")["status"] == "verifying"
        assert ledger.claim_verification("vega2", "reviewer", now=NOW).claimed
        digest = attest_local_submission(ledger, "vega2", tmp_path)
        assert not ledger.accept_verification(
            "vega2", "reviewer", ["artifact:A"], now=NOW,
            expected_submission_digest="sha256:" + ("f" * 64),
        )
        assert not ledger.accept_verification(
            "vega2", "reviewer", ["artifact:A"],
            now=NOW + timedelta(hours=1),
            expected_submission_digest=digest,
        )
        assert ledger.accept_verification(
            "vega2", "reviewer", ["artifact:A", "review:ok"], now=NOW,
            expected_submission_digest=digest,
        )
        assert ledger.get("vega2")["status"] == "completed"
    finally:
        ledger.close()
