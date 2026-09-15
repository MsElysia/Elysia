"""Issue #33 regression evidence; never proof of repository write enforcement."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from .checkpoint_reference import VALIDATOR, evaluate, snapshot_digest


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "issue_33_scope_inheritance.json"
GATE = ("fixture:github:MsElysia/Elysia:29", 1)
SEMANTIC_TARGETS = (
    "cursor-side-branch",
    "product-7374820",
    "restack-v2-sibling",
    "renamed-worker-task",
    "salami-slice-a",
    "salami-slice-b",
)


def issue_33_state():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def decide(state, entity, action="semantic_code_write", checkpoint=None):
    return evaluate(
        state,
        {"entity_id": entity, "action": action},
        trusted_current_digest=snapshot_digest(state),
        checkpoint=checkpoint,
    )


def assert_gated(result):
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.effective_active_gates == (GATE,)
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_issue_33_fixture_is_valid_and_records_exact_preserved_lineage():
    state = issue_33_state()
    VALIDATOR.validate(state)
    entities = {entity["entity_id"]: entity for entity in state["admissions"]}
    assert entities["detached-4ff2dc92"]["repository_lineage_refs"] == [
        "commit:4ff2dc92dd7d9bc393225bce35de9239a9cad6a5"
    ]
    assert entities["cursor-side-branch"]["repository_lineage_refs"] == [
        "branch:cursor/autopilot-003-issue23-restack-cwa"
    ]
    assert entities["product-7374820"]["repository_lineage_refs"] == [
        "commit:7374820642fad52a6264c86df8632c3a630df592"
    ]


@pytest.mark.parametrize("entity", SEMANTIC_TARGETS)
def test_branch_alias_sibling_renamed_task_and_salami_slices_remain_gated(entity):
    assert_gated(decide(issue_33_state(), entity))


def test_detached_sha_rebind_inherits_gate_before_branch_creation():
    assert_gated(decide(issue_33_state(), "detached-4ff2dc92", "repo_write"))


@pytest.mark.parametrize("checkpoint", [
    {},
    {"effective_active_gates": []},
    {
        "status": "IMPLEMENTATION_COMPLETE_ON_RESTACK_PENDING_INTEGRATION",
        "official_staging_branch_unchanged": True,
        "product": "7374820642fad52a6264c86df8632c3a630df592",
        "vega": "PASS",
        "architecture": "READY_FOR_INTEGRATION_REVIEW",
        "pull_request": 34,
    },
    {
        "allowed": True,
        "actor": "MsElysia",
        "author_association": "OWNER",
        "performed_via_github_app": "ChatGPT Codex Connector",
    },
])
def test_checkpoint_omission_or_technical_success_cannot_authorize_product(checkpoint):
    assert_gated(decide(issue_33_state(), "product-7374820", checkpoint=checkpoint))


@pytest.mark.parametrize("transport", ["Cursor", "Codex", "direct Git"])
def test_external_writer_is_blocked_normatively_but_explicitly_not_enforced(transport):
    result = decide(
        issue_33_state(),
        "product-7374820",
        "external_write",
        checkpoint={"transport": transport, "tests": "PASS", "pr_exists": True},
    )
    assert_gated(result)
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_friendly_self_declared_labels_do_not_erase_admitted_parent_scope():
    state = issue_33_state()
    product = next(e for e in state["admissions"] if e["entity_id"] == "product-7374820")
    product["objective_refs"] = ["objective:documentation-only"]
    product["repository_lineage_refs"] = ["branch:totally-new-candidate"]
    product["governance_gate_refs"] = []
    assert_gated(decide(state, "product-7374820"))


@pytest.mark.parametrize("mutation", [
    lambda state: state["admissions"].remove(next(e for e in state["admissions"] if e["entity_id"] == "detached-4ff2dc92")),
    lambda state: next(e for e in state["admissions"] if e["entity_id"] == "product-7374820").update(parent_refs=[]),
    lambda state: next(e for e in state["admissions"] if e["entity_id"] == "product-7374820").update(parent_refs=["unknown"]),
    lambda state: next(e for e in state["admissions"] if e["entity_id"] == "product-7374820").update(objective_refs=[]),
])
def test_missing_or_ambiguous_admission_state_fails_closed(mutation):
    state = issue_33_state()
    mutation(state)
    result = decide(state, "product-7374820")
    assert result.disposition == "BLOCKED_INVALID_STATE"
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_even_exact_shaped_release_remains_unavailable_and_gate_effective():
    state = issue_33_state()
    gate = state["gates"][0]
    gate["state"] = "released"
    gate["release"] = {
        "gate_id": gate["gate_id"],
        "generation": gate["generation"],
        "scope": deepcopy(gate["scope"]),
        "actions": gate["blocked_actions"][:],
        "asserted_human": "MsElysia",
        "transport": "direct_human",
        "application": "claimed-out-of-band",
        "evidence_refs": ["authorization:unverified"],
    }
    assert_gated(decide(state, "product-7374820"))


def test_no_matching_block_is_explicitly_not_authorization():
    state = issue_33_state()
    state["admissions"].append({
        "entity_id": "unrelated-static-review",
        "entity_kind": "task",
        "ancestry_kind": "root",
        "parent_refs": [],
        "objective_refs": ["github:MsElysia/Elysia:issue:999"],
        "repository_lineage_refs": ["branch:unrelated"],
        "governance_lineage_refs": ["governance:unrelated"],
        "action_classes": ["static_read"],
        "admission_generation": 1,
        "admitted_by": {"authority_id": "fixture:trusted-control-plane", "authority_generation": 1},
        "admission_source": ["fixture:source"],
        "admission_evidence": ["fixture:evidence"],
        "admitted_at": "2026-09-11T00:00:00Z",
        "governance_gate_refs": [],
    })
    result = decide(state, "unrelated-static-review", "static_read")
    assert result.disposition == "NO_MATCHING_BLOCK_NOT_AUTHORIZATION"
    assert result.effective_active_gates == ()
    assert result.external_write_enforcement == "NOT_ENFORCED"
