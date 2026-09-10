"""Submission binding and offline evidence policy; no network or runtime."""
import json
from datetime import timedelta

import pytest

from tests.test_vega_verifier_boundaries import NOW, open_ledger, task
from tests.evidence_fixture import attest_local_submission


def submitted(tmp_path, **policy):
    ledger = open_ledger(tmp_path / "ledger.db")
    ledger.put_task(task(max_attempts=3, required_checks=["unit"], **policy))
    assert ledger.claim("vega", "writer", now=NOW).claimed
    assert ledger.submit_for_verification("vega", "writer", "packet:A", ["artifact:A"], now=NOW,
        completion_checks=[{"name": "unit", "result": "pass", "evidence": ["artifact:A"]}])
    assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
    return ledger


def accept(ledger, digest, **kwargs):
    return ledger.accept_verification("vega", "reviewer", ["artifact:A", "review:notes"], now=NOW,
                                      expected_submission_digest=digest, **kwargs)


def test_bound_real_local_evidence_survives_reopen_and_preserves_provenance(tmp_path):
    ledger = submitted(tmp_path)
    digest = attest_local_submission(ledger, "vega", tmp_path)
    resolver = ledger.evidence_validator
    original = ledger.get("vega")["completion_submission"]
    ledger.close()
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        assert not accept(ledger, digest)  # A reopened DB does not grant evidence authority.
        ledger.evidence_validator = resolver
        assert accept(ledger, digest)
        row = ledger.get("vega")
        assert row["completion_submission"] == original
        assert row["completion_evidence"] == ["artifact:A"]
        assert row["verification_supplemental_evidence"] == ["review:notes"]
        assert row["completion_submission"]["checks"][0]["evidence"] == ["artifact:A"]
        assert ledger.events("vega")[-1]["detail"]["submission_digest"] == digest
        assert not accept(ledger, digest)
    finally:
        ledger.close()


@pytest.mark.parametrize("mutation", ["artifact", "attestation", "submission", "producer", "attempt", "packet", "evidence", "policy", "registry"])
def test_changed_evidence_or_submission_cannot_complete(tmp_path, mutation):
    ledger = submitted(tmp_path)
    try:
        digest = attest_local_submission(ledger, "vega", tmp_path)
        if mutation == "artifact":
            (tmp_path / "verified-artifact.txt").write_text("changed")
        elif mutation == "attestation":
            (tmp_path / "trusted-check-report.json").unlink()
        elif mutation == "registry":
            ledger.independence_groups["reviewer"] = "a"
        else:
            column, value = {
                "submission": ("completion_submission_json", "{}"),
                "producer": ("produced_by", "writer-b"),
                "attempt": ("attempt", 2),
                "packet": ("completion_packet_id", "packet:B"),
                "evidence": ("completion_evidence_json", '["artifact:B"]'),
                "policy": ("payload_json", json.dumps(task(risk_class="read_only"))),
            }[mutation]
            with ledger.conn:
                ledger.conn.execute(f"UPDATE tasks SET {column}=? WHERE task_id='vega'", (value,))
        before = ledger.events("vega")
        assert not accept(ledger, digest)
        assert ledger.get("vega")["status"] == "verifying"
        assert ledger.events("vega") == before
    finally:
        ledger.close()


@pytest.mark.parametrize("checks", [[], [{"name":"unit","result":"fail"}], [{"name":"unit","result":"skip"}], [{"name":"unit","result":"pass"}]*2])
def test_direct_submission_cannot_bypass_required_checks(tmp_path, checks):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(required_checks=["unit"]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification("vega", "writer", "packet:A", ["artifact:A"], now=NOW, completion_checks=checks)
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        digest = attest_local_submission(ledger, "vega", tmp_path)
        assert not accept(ledger, digest)
    finally:
        ledger.close()


def test_stale_review_cannot_accept_new_attempt_with_same_evidence(tmp_path):
    ledger = submitted(tmp_path)
    try:
        old = attest_local_submission(ledger, "vega", tmp_path)
        assert ledger.reject_verification("vega", "reviewer", "retry", [], now=NOW)
        assert ledger.claim("vega", "writer-b", now=NOW).claimed
        assert ledger.submit_for_verification("vega", "writer-b", "packet:A", ["artifact:A"], now=NOW,
            completion_checks=[{"name":"unit", "result":"pass"}])
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        new = attest_local_submission(ledger, "vega", tmp_path)
        assert old != new
        assert not accept(ledger, old)
        assert accept(ledger, new)
    finally:
        ledger.close()


@pytest.mark.parametrize("evidence", [[], ["sha256:" + "0"*64], ["commit:" + "0"*40], ["artifact:fake"], ["https://example.invalid/pull/1"]])
def test_arbitrary_evidence_without_trusted_resolver_denied(tmp_path, evidence):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification("vega", "writer", "packet", evidence, now=NOW)
        row = ledger.get("vega")
        if row["status"] == "verifying":
            assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
            assert not accept(ledger, row["completion_submission_digest"])
            assert ledger.get("vega")["status"] != "completed"
        else:
            assert row["status"] == "human_review"
            assert not ledger.claim_verification("vega", "reviewer", now=NOW).claimed
    finally:
        ledger.close()


@pytest.mark.parametrize("policy", [{"human_approval_required":True}, {"required_review_roles":["human"]}])
def test_local_proof_does_not_override_governance(tmp_path, policy):
    ledger = submitted(tmp_path, **policy)
    try:
        digest = attest_local_submission(ledger, "vega", tmp_path)
        assert not accept(ledger, digest)
    finally:
        ledger.close()


@pytest.mark.parametrize("result", [1, "true", None])
def test_resolver_requires_strict_boolean(tmp_path, result):
    ledger = submitted(tmp_path)
    try:
        ledger.evidence_validator = lambda submission: result
        assert not accept(ledger, ledger.get("vega")["completion_submission_digest"])
    finally:
        ledger.close()


def test_resolver_exception_and_mutation_fail_safely(tmp_path):
    ledger = submitted(tmp_path)
    try:
        digest = attest_local_submission(ledger, "vega", tmp_path)
        original = ledger.get("vega")["completion_submission"]
        def unavailable(submission):
            raise RuntimeError("offline")
        ledger.evidence_validator = unavailable
        assert not accept(ledger, digest)
        resolver = attest_local_submission(ledger, "vega", tmp_path)
        real = ledger.evidence_validator
        def mutating(submission):
            verified = real(submission)
            submission["evidence_refs"] = ["wrong"]
            return verified
        ledger.evidence_validator = mutating
        assert accept(ledger, digest)
        assert ledger.get("vega")["completion_submission"] == original
        assert ledger.events("vega")[-1]["detail"]["evidence_refs"] == ["artifact:A"]
    finally:
        ledger.close()


def test_live_verifier_lease_and_registry_still_required_with_proof(tmp_path):
    ledger = submitted(tmp_path)
    try:
        digest = attest_local_submission(ledger, "vega", tmp_path)
        assert not ledger.accept_verification("vega", "reviewer", [], now=NOW + timedelta(minutes=16), expected_submission_digest=digest)
        ledger.verification_workers.clear()
        assert not accept(ledger, digest)
    finally:
        ledger.close()


def test_legacy_verifying_row_without_snapshot_fails_closed_and_preserves_history(tmp_path):
    ledger = submitted(tmp_path)
    digest = ledger.get("vega")["completion_submission_digest"]
    with ledger.conn:
        ledger.conn.execute("UPDATE tasks SET completion_submission_json=NULL,completion_submission_digest=NULL WHERE task_id='vega'")
    history = ledger.events("vega")
    ledger.close()
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        assert ledger.get("vega")["completion_evidence"] == ["artifact:A"]
        assert not accept(ledger, digest)
        assert ledger.events("vega") == history
    finally:
        ledger.close()


@pytest.mark.parametrize("supplemental", [[], ["artifact:B"]])
def test_exact_digest_does_not_make_unverified_refs_substantive(tmp_path, supplemental):
    ledger = submitted(tmp_path)
    try:
        digest = ledger.get("vega")["completion_submission_digest"]
        # A real resolver exists, but its independently stored report names a
        # different submission. Knowing the digest is still not evidence.
        attest_local_submission(ledger, "vega", tmp_path)
        report = tmp_path / "trusted-check-report.json"
        content = json.loads(report.read_text())
        content["submission_digest"] = "sha256:" + "0" * 64
        report.write_text(json.dumps(content))
        assert not ledger.accept_verification("vega", "reviewer", supplemental,
            now=NOW, expected_submission_digest=digest)
        assert ledger.get("vega")["status"] == "verifying"
    finally:
        ledger.close()


def test_packet_hash_only_is_not_substantive_even_with_local_attestation(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        identity = "sha256:" + "1" * 64
        assert ledger.submit_for_verification("vega", "writer", identity, [identity], now=NOW)
        row = ledger.get("vega")
        if row["status"] == "verifying":
            assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
            digest = attest_local_submission(ledger, "vega", tmp_path)
            assert not accept(ledger, digest)
            assert ledger.get("vega")["status"] != "completed"
        else:
            assert row["status"] == "human_review"
            assert any(e["event_type"] == "evidence_binding_rejected" for e in ledger.events("vega"))
    finally:
        ledger.close()


def test_claim_is_bound_to_original_submission_digest(tmp_path):
    ledger = submitted(tmp_path)
    try:
        digest = attest_local_submission(ledger, "vega", tmp_path)
        with ledger.conn:
            ledger.conn.execute("UPDATE tasks SET verification_submission_digest='other' WHERE task_id='vega'")
        assert not accept(ledger, digest)
    finally:
        ledger.close()


@pytest.mark.parametrize("changes", [
    {"task_id": "different"}, {"packet_id": "different"}, {"outcome": "failed"},
    {"checks": [{"name":"unit", "result":"fail"}]},
    {"checks": [{"name":"unit", "result":"pass", "evidence":["different"]}]},
    {"evidence_refs": ["different"]}, {"commits": ["unmatched-commit"]},
    {"claims": [{"claim":"other", "evidence":["different"]}]},
    {"attempt": 999}, {"checks": []},
])
def test_direct_full_packet_cannot_conflict_with_submission_envelope(tmp_path, changes):
    from tests.test_autopilot_lifecycle_repairs import completion
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(required_checks=["unit"]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        packet = completion(packet_id="packet:A", evidence_refs=["artifact:A"])
        packet.update(changes)
        before = ledger.events("vega")
        assert not ledger.submit_for_verification("vega", "writer", "packet:A", ["artifact:A"],
            now=NOW, completion_checks=[{"name":"unit", "result":"pass"}], completion_packet=packet)
        assert ledger.get("vega")["status"] == "claimed"
        assert ledger.events("vega") == before
    finally:
        ledger.close()


def test_consistent_full_packet_with_actual_local_proof_completes(tmp_path):
    from tests.test_autopilot_lifecycle_repairs import completion
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(required_checks=["unit"]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        packet = completion(packet_id="packet:A", evidence_refs=["artifact:A"])
        assert ledger.submit_for_verification("vega", "writer", "packet:A", ["artifact:A"],
            now=NOW, completion_checks=packet["checks"], completion_packet=packet)
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        digest = attest_local_submission(ledger, "vega", tmp_path)
        assert accept(ledger, digest)
    finally:
        ledger.close()


def test_accept_rechecks_preexisting_inconsistent_packet_after_reopen(tmp_path):
    import hashlib
    from tests.test_autopilot_lifecycle_repairs import completion
    ledger = submitted(tmp_path)
    # Simulate the durable snapshot admitted by the prior implementation. Both
    # integrity/claim digests match; the full packet still contradicts its checks.
    snapshot = ledger.get("vega")["completion_submission"]
    snapshot["packet"] = completion(packet_id="packet:A", evidence_refs=["artifact:A"],
        checks=[{"name":"unit", "result":"fail"}])
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = "sha256:" + hashlib.sha256(raw.encode()).hexdigest()
    with ledger.conn:
        ledger.conn.execute("UPDATE tasks SET completion_submission_json=?,completion_submission_digest=?,verification_submission_digest=? WHERE task_id='vega'", (raw,digest,digest))
    ledger.close()
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        attest_local_submission(ledger, "vega", tmp_path)
        assert not accept(ledger, digest)
        assert ledger.get("vega")["status"] == "verifying"
    finally:
        ledger.close()
