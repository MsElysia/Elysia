"""Independent regression for the public v2 admission decision boundary."""
import json

import pytest

from elysia_collective_seed.autopilot.contracts.admission import evaluate_admitted
from elysia_collective_seed.autopilot.contracts.checkpoint_reference import snapshot_digest
from elysia_collective_seed.autopilot.contracts.test_admission_v2 import migrate


@pytest.mark.parametrize("generation", [None, "8", [], {}])
def test_malformed_reopened_generation_returns_blocked_decision(generation):
    snapshot = migrate()
    snapshot["snapshot_generation"] = generation
    snapshot = json.loads(json.dumps(snapshot))
    result = evaluate_admitted(
        snapshot, "child", "semantic_code_write",
        trusted_current_digest=snapshot_digest(snapshot), minimum_generation=8,
    )
    assert result.disposition == "BLOCKED_INVALID_STATE"
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


@pytest.mark.parametrize("minimum, expected", [
    (8, "BLOCKED_PENDING_HUMAN_RELEASE"), (9, "BLOCKED_INVALID_STATE"),
])
def test_valid_reopened_generation_preserves_gate_and_rollback(minimum, expected):
    snapshot = json.loads(json.dumps(migrate()))
    result = evaluate_admitted(
        snapshot, "child", "semantic_code_write",
        trusted_current_digest=snapshot_digest(snapshot), minimum_generation=minimum,
        worker_proposal={"action": "docs_only", "status": "allowed"},
    )
    assert result.disposition == expected
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"
