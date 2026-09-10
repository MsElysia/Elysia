"""Focused #22 regressions: fake proof fails closed; supplemental stays append-only."""
from tests.test_vega_verifier_boundaries import NOW, open_ledger, task
from elysia_collective_seed.autopilot.dryrun_orchestrator import validate_and_apply_completion
from tests.test_autopilot_lifecycle_repairs import completion


def test_fake_proof_string_cannot_enter_acceptably_completable_verifying(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task(required_checks=["unit"]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        packet = completion(evidence_refs=["fake-proof"])
        result = validate_and_apply_completion(ledger, packet, worker_id="writer")
        row = ledger.get("vega")
        assert not result.applied or row["status"] in {"blocked", "human_review"}
        assert row["status"] != "verifying"
        assert row["status"] != "completed"
        assert not ledger.claim_verification("vega", "reviewer", now=NOW).claimed
    finally:
        ledger.close()


def test_bound_accept_keeps_producer_evidence_and_appends_supplemental(tmp_path):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification("vega", "writer", "packet:A", ["artifact:A"], now=NOW)
        assert ledger.get("vega")["status"] == "verifying"
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        assert ledger.accept_verification(
            "vega", "reviewer", ["artifact:A", "review:note"], now=NOW
        )
        ledger.close()
        ledger = open_ledger(path)
        row = ledger.get("vega")
        assert row["status"] == "completed"
        assert row["completion_evidence"] == ["artifact:A"]
        assert row["completion_packet_id"] == "packet:A"
        assert row["verification_supplemental_evidence"] == ["review:note"]
        assert row["completion_submission_digest"]
        assert row["completion_submission"]["evidence_refs"] == ["artifact:A"]
    finally:
        ledger.close()


def test_direct_submit_without_provenance_routes_to_human_review(tmp_path):
    ledger = open_ledger(tmp_path / "ledger.db")
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification("vega", "writer", "packet:X", ["not-real"], now=NOW)
        row = ledger.get("vega")
        assert row["status"] == "human_review"
        assert row["completion_packet_id"] == "packet:X"
        assert "not-real" in row["completion_evidence"]
        assert any(e["event_type"] == "evidence_binding_rejected" for e in ledger.events("vega"))
    finally:
        ledger.close()
