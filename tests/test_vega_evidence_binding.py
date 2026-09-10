"""Issue #22 falsification; synthetic local SQLite, no external validation.

These assertions intentionally fail on PR15 head 6649b89. A packet digest is
identity, not proof; independent acceptance must bind the persisted submission.
"""
import pytest

from tests.test_vega_verifier_boundaries import NOW, open_ledger, task
from tests.test_autopilot_lifecycle_repairs import completion
from elysia_collective_seed.autopilot.dryrun_orchestrator import validate_and_apply_completion


@pytest.mark.parametrize("reopen", [False, True])
def test_packet_self_hash_is_not_substantive_write_evidence(tmp_path, reopen):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    try:
        ledger.put_task(task(required_checks=["unit"]))
        assert ledger.claim("vega", "writer").claimed
        packet = completion()  # Schema-valid; no artifact/commit/PR/claim evidence.
        result = validate_and_apply_completion(ledger, packet, worker_id="writer")
        if reopen:
            ledger.close()
            ledger = open_ledger(path)
        row = ledger.get("vega")
        assert not result.applied or row["status"] in {"blocked", "human_review"}, (
            f"A packet's own hash admitted as sole write evidence: {row}"
        )
    finally:
        ledger.close()


@pytest.mark.parametrize("reopen", [False, True])
@pytest.mark.parametrize("review_evidence", [[], ["artifact:B"]], ids=["empty", "unrelated"])
def test_verifier_acceptance_requires_persisted_submission_binding(tmp_path, reopen, review_evidence):
    path = tmp_path / "ledger.db"
    ledger = open_ledger(path)
    try:
        ledger.put_task(task())
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification("vega", "writer", "packet:A", ["artifact:A"], now=NOW)
        assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
        if reopen:
            ledger.close()
            ledger = open_ledger(path)
        assert ledger.get("vega")["completion_evidence"] == ["artifact:A"]
        assert ledger.get("vega")["completion_packet_id"] == "packet:A"
        accepted = ledger.accept_verification("vega", "reviewer", review_evidence, now=NOW)
        row = ledger.get("vega")
        assert not accepted and row["status"] != "completed", (
            f"Acceptance completed without binding packet:A/artifact:A; "
            f"review evidence={review_evidence!r}; row={row}; events={ledger.events('vega')}"
        )
    finally:
        ledger.close()
