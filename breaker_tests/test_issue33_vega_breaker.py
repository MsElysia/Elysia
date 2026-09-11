"""Independent Issue #33 breaker tests against the committed normative oracle."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest


WORKTREE = Path(r"C:\Users\Owner\guardian-issue33-vega-worktree")
sys.path.insert(0, str(WORKTREE))

from elysia_collective_seed.autopilot.contracts.checkpoint_reference import (  # noqa: E402
    VALIDATOR,
    evaluate,
    snapshot_digest,
)


FIXTURE = WORKTREE / "elysia_collective_seed/autopilot/contracts/fixtures/issue_33_scope_inheritance.json"
GATE = ("fixture:github:MsElysia/Elysia:29", 1)


def state():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def decision(snapshot, entity, action="semantic_write", checkpoint=None):
    return evaluate(
        snapshot,
        {"entity_id": entity, "action": action},
        trusted_current_digest=snapshot_digest(snapshot),
        checkpoint=checkpoint,
    )


def assert_blocked(result):
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.effective_active_gates == (GATE,)
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


@pytest.mark.parametrize("entity", [
    "detached-4ff2dc92",
    "cursor-side-branch",
    "product-7374820",
    "restack-v2-sibling",
    "renamed-worker-task",
    "salami-slice-a",
    "salami-slice-b",
])
def test_exact_regression_chain_and_aliases_inherit_gate(entity):
    assert_blocked(decision(state(), entity))


def test_deep_salami_slicing_does_not_outrun_iterative_ancestry():
    snapshot = state()
    parent = "salami-slice-b"
    for index in range(1200):
        child = f"tiny-slice-{index}"
        snapshot["entities"].append({
            "entity_id": child,
            "ancestry_kind": "derived",
            "parent_refs": [parent],
            "objective_refs": [f"friendly:objective:{index}"],
            "lineage_refs": [f"friendly:branch:{index}"],
            "governance_gate_refs": [],
        })
        parent = child
    assert_blocked(decision(snapshot, parent))


@pytest.mark.parametrize("checkpoint", [
    {},
    {"effective_active_gates": [], "allowed": True},
    {"actor": "owner", "author_association": "OWNER", "allowed": True},
    {"automation": "trusted", "tests": "PASS", "vega": "PASS", "architecture": "READY"},
])
def test_checkpoint_omission_and_attribution_spoofing_are_inert(checkpoint):
    assert_blocked(decision(state(), "product-7374820", checkpoint=checkpoint))


@pytest.mark.parametrize("transport", ["Cursor", "Codex", "direct Git"])
def test_external_writers_are_normatively_blocked_but_not_enforced(transport):
    result = decision(state(), "product-7374820", "external_write", {"transport": transport})
    assert_blocked(result)
    assert result.external_write_enforcement == "NOT_ENFORCED"


@pytest.mark.parametrize("mutation", [
    lambda s: next(e for e in s["entities"] if e["entity_id"] == "product-7374820").update(parent_refs=[]),
    lambda s: next(e for e in s["entities"] if e["entity_id"] == "product-7374820").update(parent_refs=["missing"]),
    lambda s: next(e for e in s["entities"] if e["entity_id"] == "product-7374820").update(ancestry_kind="root"),
    lambda s: next(e for e in s["entities"] if e["entity_id"] == "product-7374820").pop("ancestry_kind"),
    lambda s: next(e for e in s["entities"] if e["entity_id"] == "product-7374820").update(objective_refs=[]),
    lambda s: next(e for e in s["entities"] if e["entity_id"] == "product-7374820").update(lineage_refs=[]),
])
def test_severed_or_unknown_admission_fails_closed(mutation):
    snapshot = state()
    mutation(snapshot)
    result = decision(snapshot, "product-7374820")
    assert result.disposition == "BLOCKED_INVALID_STATE"
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_worker_created_new_root_is_no_authorization_even_if_structurally_valid():
    snapshot = state()
    snapshot["entities"].append({
        "entity_id": "self-declared-fresh-root",
        "ancestry_kind": "root",
        "parent_refs": [],
        "objective_refs": ["friendly:documentation"],
        "lineage_refs": ["branch:renamed"],
        "governance_gate_refs": [],
    })
    result = decision(snapshot, "self-declared-fresh-root")
    assert result.disposition == "NO_MATCHING_BLOCK_NOT_AUTHORIZATION"
    assert result.effective_active_gates == ()
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_spoofed_release_remains_unavailable_and_blocked():
    snapshot = state()
    gate = snapshot["gates"][0]
    gate["state"] = "released"
    gate["release"] = {
        "gate_id": gate["gate_id"], "generation": gate["generation"],
        "scope": deepcopy(gate["scope"]), "actions": list(gate["blocked_actions"]),
        "asserted_human": "owner", "transport": "direct_human",
        "application": "claimed", "evidence_refs": ["unverified:claim"],
    }
    assert_blocked(decision(snapshot, "product-7374820"))


def test_fixture_schema_and_exact_historical_chain():
    snapshot = state()
    VALIDATOR.validate(snapshot)
    entities = {e["entity_id"]: e for e in snapshot["entities"]}
    assert entities["detached-4ff2dc92"]["lineage_refs"] == [
        "commit:4ff2dc92dd7d9bc393225bce35de9239a9cad6a5"
    ]
    assert entities["cursor-side-branch"]["lineage_refs"] == [
        "branch:cursor/autopilot-003-issue23-restack-cwa"
    ]
    assert entities["product-7374820"]["lineage_refs"] == [
        "commit:7374820642fad52a6264c86df8632c3a630df592"
    ]
