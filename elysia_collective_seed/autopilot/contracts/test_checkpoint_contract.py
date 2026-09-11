"""Falsification of the normative oracle, NOT runtime/SQLite/Git enforcement."""
from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator

from .checkpoint_reference import SCHEMA, VALIDATOR, evaluate, snapshot_digest


BLOCKED = ["claim", "repo_write", "semantic_write", "integration", "merge", "deploy", "external_write"]


def machine_state():
    # Synthetic reconstruction of #28/#29 at 9b21e002; generation 1 is a fixture,
    # not an assertion that GitHub already contains a durable numbered gate.
    return {
        "schema_version": 1, "revision": 1,
        "source_refs": ["https://github.com/MsElysia/Elysia/issues/11#issuecomment-5636666687"],
        "gates": [{
            "gate_id": "fixture:github:MsElysia/Elysia:29", "generation": 1,
            "kind": "human_governance_required", "state": "active",
            "scope": {"objective_refs": ["github:MsElysia/Elysia:issue:23"],
                      "lineage_refs": ["autopilot-003-issue23-restack"]},
            "inherit_to_children": True, "blocked_actions": BLOCKED[:],
            "reason": "Unreleased lineage decision",
            "source_refs": ["https://github.com/MsElysia/Elysia/issues/29",
                            "commit:9b21e002a8d65735469e7038a22853a444ee7e1c"],
            "release": None,
        }],
        "entities": [{
            "entity_id": "root", "parent_refs": [],
            "objective_refs": ["github:MsElysia/Elysia:issue:23"],
            "lineage_refs": ["autopilot-003-issue23-restack"],
            "governance_gate_refs": [],
        }],
    }


def inspect(state, entity="root", action="semantic_write", checkpoint=None, pin=None):
    return evaluate(state, {"entity_id": entity, "action": action},
                    trusted_current_digest=pin or snapshot_digest(state), checkpoint=checkpoint)


def child(name, parents):
    return {"entity_id": name, "parent_refs": parents,
            "objective_refs": [f"objective:{name}"], "lineage_refs": [f"branch:{name}"],
            "governance_gate_refs": []}


def release_claim(gate):
    return {"gate_id": gate["gate_id"], "generation": gate["generation"],
            "scope": deepcopy(gate["scope"]), "actions": BLOCKED[:],
            "asserted_human": "MsElysia", "transport": "github_app",
            "application": "ChatGPT Codex Connector", "evidence_refs": ["issue:owner-comment"]}


def test_schema_validity_and_reference_fixture():
    Draft202012Validator.check_schema(SCHEMA)
    VALIDATOR.validate(machine_state())


@pytest.mark.parametrize("action", BLOCKED)
@pytest.mark.parametrize("checkpoint", [None, {}, {"effective_active_gates": []},
    {"Next safe action": "Port #23 CWA now", "human_approval_required": False},
    {"state": "released", "released_by": "MsElysia", "author_association": "OWNER",
     "performed_via_github_app": "ChatGPT Codex Connector"}])
def test_checkpoint_omission_conflict_or_owner_claim_cannot_clear_gate(action, checkpoint):
    result = inspect(machine_state(), action=action, checkpoint=checkpoint)
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.effective_active_gates == (("fixture:github:MsElysia/Elysia:29", 1),)
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_child_restack_and_salami_slices_inherit_all_ancestors():
    state = machine_state()
    for i in range(30):
        state["entities"].append(child(f"slice-{i}", [f"slice-{i-1}" if i else "root"]))
    # Unsorted storage and renamed child metadata cannot sever graph ancestry.
    state["entities"].reverse()
    for i in range(30):
        assert inspect(state, f"slice-{i}").disposition == "BLOCKED_PENDING_HUMAN_RELEASE"


def test_multiple_parents_and_multiple_gates_union_without_newest_wins():
    state = machine_state()
    extra = deepcopy(state["gates"][0])
    extra.update(gate_id="second", generation=7,
                 scope={"objective_refs": ["other"], "lineage_refs": ["other"]})
    state["gates"].append(extra)
    other = child("other-root", [])
    other["governance_gate_refs"] = ["second"]
    state["entities"] += [other, child("combined", ["root", "other-root"])]
    result = inspect(state, "combined")
    assert result.effective_active_gates == (("fixture:github:MsElysia/Elysia:29", 1), ("second", 7))


@pytest.mark.parametrize("preserved", ["objective_refs", "lineage_refs", "governance_gate_refs"])
def test_each_independent_scope_match_is_sufficient(preserved):
    state = machine_state()
    node = child("renamed", [])
    node[preserved] = (state["entities"][0][preserved] if preserved != "governance_gate_refs"
                       else [state["gates"][0]["gate_id"]])
    state["entities"] = [node]
    assert inspect(state, "renamed").disposition == "BLOCKED_PENDING_HUMAN_RELEASE"


@pytest.mark.parametrize("change", [
    {"asserted_human": "worker"}, {"asserted_human": "verifier"},
    {"transport": "direct_human", "application": "none"},
    {"generation": 2}, {"gate_id": "different"}, {"actions": ["merge"]},
    {"scope": {"objective_refs": ["all"], "lineage_refs": ["all"]}},
    {"evidence_refs": ["repo:automation-writable-proof"]}, {},
])
def test_release_authenticity_is_never_inferred_from_shape_or_identity(change, tmp_path):
    state = machine_state()
    gate = state["gates"][0]
    gate["state"] = "released"
    gate["release"] = release_claim(gate)
    gate["release"].update(change)
    VALIDATOR.validate(state)
    # File roundtrip proves only portable snapshot semantics; not ledger safety.
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert inspect(restored).disposition == "BLOCKED_PENDING_HUMAN_RELEASE"


def test_new_generation_cannot_use_prior_release():
    state = machine_state()
    gate = state["gates"][0]
    gate["release"] = release_claim(gate)
    gate.update(generation=2, state="released")
    assert inspect(state).effective_active_gates == ((gate["gate_id"], 2),)
    assert inspect(state).disposition == "BLOCKED_PENDING_HUMAN_RELEASE"


@pytest.mark.parametrize("mutation", ["remove_gate", "replace_gate", "rename_objective", "erase_ancestry", "old_revision"])
def test_snapshot_tampering_or_rollback_cannot_match_independent_current_pin(mutation):
    state = machine_state()
    state["entities"].append(child("descendant", ["root"]))
    pin = snapshot_digest(state)
    if mutation == "remove_gate":
        state["gates"] = []
    elif mutation == "replace_gate":
        state["gates"][0]["generation"] += 1
    elif mutation == "rename_objective":
        state["entities"][0]["objective_refs"] = ["unrelated"]
    elif mutation == "erase_ancestry":
        state["entities"][1]["parent_refs"] = []
    else:
        state["revision"] += 1
    assert inspect(state, "descendant", pin=pin).disposition == "BLOCKED_INVALID_STATE"


def test_fresh_worker_equivalence_and_inputs_unchanged(tmp_path):
    state = machine_state()
    before = deepcopy(state)
    pin = snapshot_digest(state)
    path = tmp_path / "machine-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    fresh = json.loads(path.read_text(encoding="utf-8"))
    full = inspect(state, checkpoint={"history": ["#28", "#29", "#30", "#31"]}, pin=pin)
    latest = inspect(fresh, checkpoint={"next": "port CWA", "gates": []}, pin=pin)
    assert full == latest
    assert state == before


@pytest.mark.parametrize("field", ["gates", "entities", "source_refs", "revision", "schema_version"])
@pytest.mark.parametrize("value", [None, "", {}, False])
def test_malformed_snapshot_fails_closed(field, value):
    state = machine_state()
    state[field] = value
    assert inspect(state).disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("field", ["gate_id", "generation", "state", "scope", "blocked_actions", "inherit_to_children", "release"])
def test_missing_required_gate_fields_fail_closed(field):
    state = machine_state()
    del state["gates"][0][field]
    assert inspect(state).disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("change", [
    {"state": "approved"}, {"generation": True}, {"generation": 0},
    {"inherit_to_children": False}, {"blocked_actions": []},
    {"scope": {"objective_refs": [], "lineage_refs": []}}, {"gate_id": " "},
])
def test_malformed_gate_fields_fail_closed(change):
    state = machine_state()
    state["gates"][0].update(change)
    assert inspect(state).disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("action", BLOCKED)
def test_snapshot_cannot_omit_a_required_blocked_action(action):
    state = machine_state()
    state["gates"][0]["blocked_actions"].remove(action)
    assert inspect(state).disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("defect", ["cycle", "missing_parent", "missing_gate", "duplicate_node", "duplicate_gate"])
def test_graph_inconsistency_including_disconnected_records_blocks(defect):
    state = machine_state()
    disconnected = child("disconnected", [])
    state["entities"].append(disconnected)
    if defect == "cycle":
        disconnected["parent_refs"] = ["disconnected"]
    elif defect == "missing_parent":
        disconnected["parent_refs"] = ["absent"]
    elif defect == "missing_gate":
        disconnected["governance_gate_refs"] = ["absent"]
    elif defect == "duplicate_node":
        state["entities"].append(deepcopy(disconnected))
    else:
        state["gates"].append(deepcopy(state["gates"][0]))
    assert inspect(state).disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("proposal", [None, {}, {"entity_id": "root", "action": "execute"},
    {"entity_id": "unknown", "action": "claim"}, {"entity_id": "root", "action": []},
    {"entity_id": "root", "action": "claim", "released": True}])
def test_invalid_proposal_cannot_grant_authority(proposal):
    state = machine_state()
    assert evaluate(state, proposal, trusted_current_digest=snapshot_digest(state)).disposition == "BLOCKED_INVALID_STATE"


def test_missing_machine_authority_is_blocked():
    assert evaluate(None, {}, trusted_current_digest=None).disposition == "BLOCKED_INVALID_STATE"
    assert evaluate(machine_state(), {"entity_id": "root", "action": "claim"},
                    trusted_current_digest=None).disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("action", ["read", "static_analysis", "specification", "test_design"])
def test_nongated_action_is_not_an_execution_authorization(action):
    result = inspect(machine_state(), action=action)
    assert result.disposition == "NO_MATCHING_BLOCK_NOT_AUTHORIZATION"
    assert result.effective_active_gates
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_unrelated_scope_cannot_claim_external_enforcement():
    state = machine_state()
    state["entities"].append(child("unrelated", []))
    result = inspect(state, "unrelated")
    assert result.disposition == "NO_MATCHING_BLOCK_NOT_AUTHORIZATION"
    assert result.effective_active_gates == ()
    assert result.external_write_enforcement == "NOT_ENFORCED"
