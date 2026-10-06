"""Exact Issue #33 fixture at the v2 boundary; no Git/runtime enforcement."""
from copy import deepcopy
import json

import pytest

from .admission import evaluate_admitted
from .checkpoint_reference import snapshot_digest
from .test_issue_33_scope_inheritance import (
    GATE, SEMANTIC_TARGETS, assert_gated, issue_33_state,
)


def decide(state, entity, action="semantic_code_write", *, proposal=None, pin=None):
    # Synthetic trusted state pin only: this is not an authentication service.
    return evaluate_admitted(
        state, entity, action,
        trusted_current_digest=pin if pin is not None else snapshot_digest(state),
        minimum_generation=33, worker_proposal=proposal,
    )


@pytest.mark.parametrize("entity", ("detached-4ff2dc92",) + SEMANTIC_TARGETS)
def test_exact_recurrence_stays_blocked_at_v2_admission_after_reload(entity):
    state = issue_33_state()
    pin = snapshot_digest(state)
    restored = json.loads(json.dumps(state))
    before = deepcopy(restored)
    assert_gated(decide(restored, entity, pin=pin))
    assert restored == before  # Evaluation must not mutate preserved evidence.


@pytest.mark.parametrize("match", ["objective", "repository", "governance", "gate_ref"])
def test_inherited_scope_routes_independently_block_alias_without_branch_match(match):
    state = issue_33_state()
    gate = state["gates"][0]
    gate["scope"] = {
        "objective_refs": ["fixture:unmatched-objective"],
        "lineage_refs": ["fixture:unmatched-lineage"],
    }
    for node in state["admissions"]:
        node["governance_gate_refs"] = []
    root = state["admissions"][0]
    if match == "objective":
        gate["scope"]["objective_refs"] = root["objective_refs"][:]
    elif match == "repository":
        # Match an ancestor SHA, never the new branch's literal name.
        ancestor = state["admissions"][1]
        gate["scope"]["lineage_refs"] = ancestor["repository_lineage_refs"][:]
    elif match == "governance":
        gate["scope"]["lineage_refs"] = root["governance_lineage_refs"][:]
    else:
        root["governance_gate_refs"] = [GATE[0]]
    assert_gated(decide(state, "product-7374820"))


@pytest.mark.parametrize("gated_parent_first", [True, False])
def test_merge_alias_inherits_gate_from_every_parent(gated_parent_first):
    state = issue_33_state()
    unrelated = deepcopy(state["admissions"][0])
    unrelated.update(
        entity_id="unrelated-root", objective_refs=["fixture:unrelated"],
        repository_lineage_refs=["branch:unrelated"],
        governance_lineage_refs=["governance:unrelated"], governance_gate_refs=[],
    )
    alias = deepcopy(state["admissions"][2])
    parents = ["unrelated-root", "detached-4ff2dc92"]
    if gated_parent_first:
        parents.reverse()
    alias.update(
        entity_id="merge-alias", parent_refs=parents,
        repository_lineage_refs=["branch:friendly-candidate"],
        governance_lineage_refs=["governance:friendly-candidate"],
        objective_refs=["task:friendly-candidate"], governance_gate_refs=[],
    )
    state["admissions"].extend([unrelated, alias])
    assert_gated(decide(state, "merge-alias"))


@pytest.mark.parametrize("transport", ["Cursor", "Codex", "direct Git"])
def test_worker_alias_root_docs_and_owner_claims_cannot_narrow_admitted_effect(transport):
    state = issue_33_state()
    proposal = {
        "branch": "new-safe-candidate", "parent_refs": [], "ancestry_kind": "root",
        "objective_refs": ["task:docs-only"], "action": "docs_only",
        "effective_active_gates": [], "transport": transport,
        "official_staging_branch_unchanged": True,
        "tests": "PASS", "candidate_status": "READY_FOR_INTEGRATION_REVIEW",
        "asserted_human": "MsElysia", "author_association": "OWNER",
        "performed_via_github_app": "ChatGPT Codex Connector",
    }
    assert_gated(decide(state, "product-7374820", "integration", proposal=proposal))
    result = decide(state, "product-7374820", "docs_only", proposal=proposal)
    assert result.disposition == "BLOCKED_INVALID_STATE"
    assert result.reason == "action_not_admitted"


@pytest.mark.parametrize("mutation", ["severed", "unknown_parent", "stale_authority", "stale_pin"])
def test_alias_admission_cannot_recover_authority_from_invalid_or_stale_state(mutation):
    state = issue_33_state()
    pin = snapshot_digest(state)
    product = state["admissions"][3]
    if mutation == "severed":
        product["parent_refs"] = []
    elif mutation == "unknown_parent":
        product["parent_refs"] = ["unadmitted-root"]
    elif mutation == "stale_authority":
        product["admitted_by"]["authority_generation"] += 1
    else:
        state["snapshot_generation"] += 1
    result = decide(state, "product-7374820", pin=pin if mutation == "stale_pin" else None)
    assert result.disposition == "BLOCKED_INVALID_STATE"
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"
