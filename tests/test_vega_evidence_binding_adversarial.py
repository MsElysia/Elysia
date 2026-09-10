"""Adversarial #22 re-verify: fail-open risk allowlist (expected FAIL until Astra repair).

Independent Vega finding against 0cf0e99. Non-allowlisted risk_class values skip
substantive provenance and can complete with unrelated review notes when a matching
verifier is registered. Soft path must be an explicit allowlist (sandbox_write /
read_only), not a consequential-only denylist.
"""
from elysia_collective_seed.autopilot.dispatcher import Worker
from elysia_collective_seed.autopilot.task_ledger import TaskLedger
from tests.test_vega_verifier_boundaries import NOW, task


def _open(path, risks):
    return TaskLedger(
        path,
        verification_workers=[
            Worker("reviewer", "synthetic", frozenset({"verification"}), frozenset(risks))
        ],
        independence_groups={"writer": "a", "reviewer": "c"},
    )


def test_unknown_risk_cannot_complete_without_substantive_provenance(tmp_path):
    ledger = _open(tmp_path / "ledger.db", {"repo_write", "unknown_risk"})
    try:
        ledger.put_task(task(risk_class="unknown_risk", required_checks=[]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:X", ["only-identity"], now=NOW
        )
        row = ledger.get("vega")
        assert row["status"] in {"human_review", "blocked"}, (
            f"unknown risk admitted to completable verifying without provenance: {row}"
        )
        assert row["status"] != "verifying"
        assert row["status"] != "completed"
    finally:
        ledger.close()


def test_empty_risk_class_cannot_complete_without_substantive_provenance(tmp_path):
    ledger = _open(tmp_path / "ledger.db", {"repo_write", ""})
    try:
        ledger.put_task(task(risk_class="", required_checks=[]))
        assert ledger.claim("vega", "writer", now=NOW).claimed
        assert ledger.submit_for_verification(
            "vega", "writer", "packet:Y", ["not-real"], now=NOW
        )
        row = ledger.get("vega")
        # If somehow verifying, accept with unrelated notes must still fail closed.
        if row["status"] == "verifying":
            assert ledger.claim_verification("vega", "reviewer", now=NOW).claimed
            accepted = ledger.accept_verification(
                "vega", "reviewer", ["note:only"], now=NOW
            )
            assert not accepted and ledger.get("vega")["status"] != "completed"
        else:
            assert row["status"] in {"human_review", "blocked"}
    finally:
        ledger.close()
