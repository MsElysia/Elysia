"""Local test authority: bind a real artifact and check report to one submission.

Only test setup installs this trusted resolver. Production has no default proof
resolver. Opaque reference strings are mapped by this independent fixture report,
not interpreted as proof because of their spelling.
"""
import hashlib
import json


def attest_local_submission(ledger, task_id, directory):
    row = ledger.get(task_id)
    artifact = directory / "verified-artifact.txt"
    artifact.write_bytes(b"bounded local result\n")
    # This independently controlled local check actually reads the artifact.
    passed = artifact.read_bytes() == b"bounded local result\n"
    report = directory / "trusted-check-report.json"
    report.write_text(json.dumps({
        "submission_digest": row["completion_submission_digest"],
        "evidence_refs": row["completion_evidence"],
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "checks": {check["name"]: "pass" if passed else "fail"
                   for check in row["completion_submission"]["checks"]},
        "artifact_check_passed": passed,
    }))

    def verify(submission):
        attestation = json.loads(report.read_text())
        canonical = json.dumps(submission, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return (
            "sha256:" + hashlib.sha256(canonical.encode()).hexdigest() == attestation["submission_digest"]
            and bool(submission["evidence_refs"])
            and submission["evidence_refs"] == attestation["evidence_refs"]
            and hashlib.sha256(artifact.read_bytes()).hexdigest() == attestation["artifact_sha256"]
            and attestation["artifact_check_passed"] is True
            and all(attestation["checks"].get(check["name"]) == check["result"] == "pass" for check in submission["checks"])
        )

    ledger.evidence_validator = verify
    return row["completion_submission_digest"]


def seed_legacy_execution_lease(ledger, task_id, worker, now):
    """Test-only historical lease predating execution policy enforcement."""
    from datetime import timedelta
    with ledger.conn:
        ledger.conn.execute("UPDATE tasks SET status='claimed',claimed_by=?,lease_expires_at=?,attempt=attempt+1 WHERE task_id=?",
                            (worker, (now + timedelta(minutes=15)).isoformat(), task_id))
