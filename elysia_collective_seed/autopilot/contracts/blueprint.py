"""Executable governance bridge blueprint; never a production write guard.

This module makes issuance, classification, ticket fencing, queue attachment and
authorized-progress proof obligations executable without importing Guardian,
TaskLedger, Git, providers, or any operational mutation path. A successful
reference decision is not permission to mutate a repository.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

from jsonschema import Draft202012Validator

from .admission import AdmissionError, validate_snapshot_version
from .checkpoint_reference import FORMAT_CHECKER, snapshot_digest


BRIDGE_SCHEMA = json.loads(
    Path(__file__).with_name("governance_bridge.schema.json").read_text(encoding="utf-8")
)
ADMISSION_RECORD_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/trusted_admission_record"},
    format_checker=FORMAT_CHECKER,
)
TICKET_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/mutation_authorization_ticket"},
    format_checker=FORMAT_CHECKER,
)
MUTATION_RESULT_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/mutation_result"},
    format_checker=FORMAT_CHECKER,
)
VERIFICATION_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/verification_evidence"},
    format_checker=FORMAT_CHECKER,
)
TRUSTED_TASK_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/trusted_task_record"},
    format_checker=FORMAT_CHECKER,
)
PROGRESSION_AUTHORIZATION_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/progression_authorization"},
    format_checker=FORMAT_CHECKER,
)
BRIDGE_CONTROL_STATE_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/bridge_control_state"},
    format_checker=FORMAT_CHECKER,
)
GOVERNANCE_CONTROL_V2_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/governance_control_state_v2"}, format_checker=FORMAT_CHECKER,
)
EFFECT_TRANSACTION_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/effect_transaction"}, format_checker=FORMAT_CHECKER,
)
EFFECT_RECEIPT_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/exact_effect_receipt"}, format_checker=FORMAT_CHECKER,
)
MUTATION_RESULT_V2_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/mutation_result_v2"}, format_checker=FORMAT_CHECKER,
)
VERIFIER_CLAIM_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/verifier_claim"}, format_checker=FORMAT_CHECKER,
)
VERIFICATION_RECORD_V2_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/verification_record_v2"}, format_checker=FORMAT_CHECKER,
)
PROGRESS_TOKEN_V2_VALIDATOR = Draft202012Validator(
    {"$schema": BRIDGE_SCHEMA["$schema"], "$defs": BRIDGE_SCHEMA["$defs"],
     "$ref": "#/$defs/progress_token_v2"}, format_checker=FORMAT_CHECKER,
)

COMPOSED_MEDIATED_BOUNDARIES = frozenset({
    "live_mutation",
    "repository_file_write",
    "task_claim",
    "queue_objective_attach",
    "authorized_progress",
})
PARTIAL_BOUNDARIES = frozenset({"mutation_engine._direct_apply_mutation"})
EXTERNAL_WRITERS = frozenset({
    "git_cli", "github_api", "cursor_shell", "codex_shell",
    "third_party_git_client", "human_local_git",
})
KNOWN_MEDIATED_WRITERS = frozenset({
    "mutation.py.apply",
    "mutation_engine._direct_apply_mutation",
    "implementer/repo_adapter.apply_patch",
    "MutationPublisher.publish_mutation",
    "MutationPublisher.write_text",
    "MetaCoder.apply_mutation",
})
PROGRESS_STATES = frozenset({
    "OBSERVED_UNTRUSTED",
    "PRESERVED_EVIDENCE",
    "ADMITTED",
    "AUTHORIZED_TO_EXECUTE",
    "EXECUTED_PENDING_VERIFICATION",
    "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION",
    "AUTHORIZED_PROGRESS",
})

CONTENT_FACT_ACTIONS = {
    "documentation_text": "docs_only",
    "test_code": "test_only",
    "schema_contract": "schema_spec_write",
    "runtime_code": "semantic_code_write",
    "generated_runtime_code": "semantic_code_write",
    "repository_ref_update": "repo_write",
    "integration_change": "integration",
    "merge_operation": "merge",
    "deploy_operation": "deploy",
    "external_effect": "external_write",
    "permission_change": "permission_change",
    "private_data_access": "private_data_access",
    "static_read": "static_read",
}


class BlueprintError(ValueError):
    """A normative bridge proof obligation failed closed."""


@dataclass(frozen=True)
class BridgeDecision:
    disposition: str
    reason: str = ""
    production_enforcement: str = "NOT_IMPLEMENTED"
    cross_universe_enforcement: str = "NOT_IMPLEMENTED"
    external_write_enforcement: str = "NOT_ENFORCED"


def _digest(value: Mapping) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def bridge_record_digest(value: Mapping) -> str:
    """Content identity for trusted pinning; never authentication by itself."""
    return _digest(value)


def _time(value: str) -> datetime:
    if not isinstance(value, str):
        raise BlueprintError("invalid_time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BlueprintError("invalid_time") from exc
    if parsed.tzinfo is None:
        raise BlueprintError("invalid_time")
    return parsed.astimezone(timezone.utc)


def _refs(value, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if (not isinstance(value, (list, tuple))
            or (not allow_empty and not value)
            or any(type(item) is not str or not item.strip() or item != item.strip()
                   for item in value)
            or len(set(value)) != len(value)):
        raise BlueprintError(f"invalid_{name}")
    return tuple(value)


def _canonical_write_set(write_set):
    """Validate an exact, deterministic effect set; do not repair worker input."""
    if not isinstance(write_set, list) or not write_set:
        raise BlueprintError("invalid_classified_write_set")
    normalized = []
    for effect in write_set:
        if not isinstance(effect, dict) or set(effect) != {
            "path", "operation", "effect_digest", "action_classes",
        }:
            raise BlueprintError("invalid_classified_write_set")
        path = effect["path"]
        if (type(path) is not str or not path or path != path.strip()
                or "\\" in path or path.startswith("/")
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            raise BlueprintError("noncanonical_write_set")
        if effect["operation"] not in {"create", "update", "delete", "rename"}:
            raise BlueprintError("invalid_classified_write_set")
        digest = effect["effect_digest"]
        if (type(digest) is not str or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise BlueprintError("invalid_classified_write_set")
        actions = sorted(_refs(effect["action_classes"], "write_effect_actions"))
        if any(action not in set(CONTENT_FACT_ACTIONS.values()) for action in actions):
            raise BlueprintError("invalid_classified_write_set")
        normalized.append({
            "path": path,
            "operation": effect["operation"],
            "effect_digest": digest,
            "action_classes": actions,
        })
    ordered = sorted(
        normalized,
        key=lambda item: (item["path"], item["operation"], item["effect_digest"]),
    )
    if normalized != ordered or len({item["path"] for item in ordered}) != len(ordered):
        raise BlueprintError("noncanonical_write_set")
    return ordered


def classified_write_set_digest(write_set) -> str:
    """Content identity for canonical classified effects."""
    canonical = _canonical_write_set(write_set)
    return _digest({"write_set_version": 1, "effects": canonical})


def ticket_consumption_identity(ticket) -> str:
    """Identity consumed atomically; a nonce alone cannot authorize a sibling ticket."""
    if not isinstance(ticket, Mapping):
        raise BlueprintError("invalid_ticket")
    required = ("ticket_id", "nonce", "state_digest")
    if any(type(ticket.get(field)) is not str for field in required):
        raise BlueprintError("invalid_ticket")
    return _digest({field: ticket[field] for field in required})


def _validate_control_state(state, trusted_digest):
    if (not BRIDGE_CONTROL_STATE_VALIDATOR.is_valid(state)
            or type(trusted_digest) is not str
            or _digest(state) != trusted_digest):
        raise BlueprintError("bridge_control_state_not_current_or_not_pinned")
    return state


def _advance_control_state(state, **updates):
    advanced = deepcopy(state)
    advanced["registry_generation"] += 1
    for field, value in updates.items():
        advanced[field] = deepcopy(value)
    if not BRIDGE_CONTROL_STATE_VALIDATOR.is_valid(advanced):
        raise BlueprintError("invalid_bridge_control_state_transition")
    return advanced


def assess_composed_boundary_plan(boundaries: Iterable[str]) -> BridgeDecision:
    """Assess blueprint completeness, never actual runtime coverage."""
    try:
        supplied = frozenset(boundaries)
    except TypeError:
        return BridgeDecision("INCOMPLETE_NOT_ENFORCED", "invalid_boundary_plan")
    missing = sorted(COMPOSED_MEDIATED_BOUNDARIES - supplied)
    if missing:
        return BridgeDecision("INCOMPLETE_NOT_ENFORCED", "missing:" + ",".join(missing))
    return BridgeDecision(
        "COMPOSED_MULTI_BOUNDARY_DESIGN",
        "normative_plan_complete_repository_side_enforcement_still_required",
    )


def classify_authoritatively(
    effect, *, bridge_control_state, trusted_control_state_digest,
    worker_proposal=None,
):
    """Classify trusted observed effects; worker labels/objectives are ignored.

    Production must derive these facts from the intended operation, target and
    content inspection. Passing this dictionary is only a reference-model stand-in
    for that authenticated classifier boundary.
    """
    del worker_proposal
    if not isinstance(effect, dict) or set(effect) != {
        "classifier_id", "classifier_generation", "classifier_version",
        "classifier_provenance", "admitted_entity_id", "admission_generation",
        "objective_refs", "governance_lineage_refs", "content_facts",
        "classified_write_set", "staged_patch_digest", "dynamic_effect_policy",
        "mutation_target", "ambiguous_action", "ambiguous_objective",
        "evidence_refs",
    }:
        raise BlueprintError("invalid_trusted_effect")
    control = _validate_control_state(
        bridge_control_state, trusted_control_state_digest
    )
    registry = {}
    for classifier in control["classifiers"]:
        if (not isinstance(classifier, Mapping)
                or set(classifier) != {
                    "classifier_id", "classifier_generation", "classifier_version",
                    "provenance",
                }
                or type(classifier["classifier_id"]) is not str
                or type(classifier["classifier_generation"]) is not int
                or classifier["classifier_generation"] < 1
                or type(classifier["classifier_version"]) is not str
                or not classifier["classifier_version"].strip()):
            raise BlueprintError("invalid_classifier_registry")
        _refs(classifier["provenance"], "classifier_provenance")
        key = (classifier["classifier_id"], classifier["classifier_generation"])
        if key in registry:
            raise BlueprintError("duplicate_classifier")
        registry[key] = classifier
    key = (effect["classifier_id"], effect["classifier_generation"])
    if key not in registry:
        raise BlueprintError("unknown_classifier")
    if effect["classifier_provenance"] != registry[key]["provenance"]:
        raise BlueprintError("classifier_provenance_mismatch")
    if effect["classifier_version"] != registry[key]["classifier_version"]:
        raise BlueprintError("classifier_version_mismatch")
    if effect["ambiguous_action"] is not False or effect["ambiguous_objective"] is not False:
        raise BlueprintError("ambiguous_classification")
    objectives = _refs(effect["objective_refs"], "objective_refs")
    governance_lineage = _refs(
        effect["governance_lineage_refs"], "governance_lineage_refs"
    )
    facts = _refs(effect["content_facts"], "content_facts")
    evidence = _refs(effect["evidence_refs"], "classification_evidence")
    mutation_target = effect["mutation_target"]
    if (not isinstance(mutation_target, dict)
            or mutation_target.get("surface") not in
            COMPOSED_MEDIATED_BOUNDARIES | {"repository_side"}):
        raise BlueprintError("unknown_target_surface")
    if type(effect["admitted_entity_id"]) is not str or not effect["admitted_entity_id"]:
        raise BlueprintError("invalid_entity")
    if type(effect["admission_generation"]) is not int or effect["admission_generation"] < 1:
        raise BlueprintError("invalid_admission_generation")
    if any(fact not in CONTENT_FACT_ACTIONS for fact in facts):
        raise BlueprintError("ambiguous_classification")
    actions = tuple(sorted({CONTENT_FACT_ACTIONS[fact] for fact in facts}))
    write_set = _canonical_write_set(effect["classified_write_set"])
    write_actions = {action for item in write_set for action in item["action_classes"]}
    if write_actions != set(actions):
        raise BlueprintError("write_set_action_mismatch")
    policy = effect["dynamic_effect_policy"]
    if (not isinstance(policy, dict)
            or set(policy) != {"mode", "approved_namespaces"}):
        raise BlueprintError("invalid_dynamic_effect_policy")
    if policy["mode"] == "reclassify_after_materialization":
        raise BlueprintError("generated_effect_reclassification_required")
    if policy["mode"] != "exact_staged_patch":
        raise BlueprintError("invalid_dynamic_effect_policy")
    namespaces = _refs(
        policy["approved_namespaces"], "approved_namespaces", allow_empty=True
    )
    for namespace in namespaces:
        if ("\\" in namespace or namespace.startswith("/")
                or any(part in {"", ".", ".."} for part in namespace.split("/"))):
            raise BlueprintError("invalid_dynamic_effect_policy")
    if namespaces and any(
        not any(item["path"] == ns or item["path"].startswith(ns + "/")
                for ns in namespaces)
        for item in write_set
    ):
        raise BlueprintError("generated_effect_outside_approved_namespace")
    staged_patch_digest = effect["staged_patch_digest"]
    if (type(staged_patch_digest) is not str or len(staged_patch_digest) != 64
            or any(char not in "0123456789abcdef" for char in staged_patch_digest)):
        raise BlueprintError("invalid_staged_patch_digest")
    write_set_digest = classified_write_set_digest(write_set)
    result = {
        "classification_status": "AUTHORITATIVE_REFERENCE_CLASSIFICATION",
        "classifier_id": effect["classifier_id"],
        "classifier_generation": effect["classifier_generation"],
        "classifier_version": effect["classifier_version"],
        "admitted_entity_id": effect["admitted_entity_id"],
        "admission_generation": effect["admission_generation"],
        "objective_refs": list(objectives),
        "governance_lineage_refs": list(governance_lineage),
        "action_classes": list(actions),
        "mutation_target": deepcopy(mutation_target),
        "classified_write_set": write_set,
        "write_set_digest": write_set_digest,
        "staged_patch_digest": staged_patch_digest,
        "dynamic_effect_policy": deepcopy(policy),
        "evidence_refs": list(evidence),
    }
    result["classification_digest"] = _digest(result)
    return result


def _effective_scopes(snapshot):
    nodes = {node["entity_id"]: node for node in snapshot["admissions"]}
    if len(nodes) != len(snapshot["admissions"]):
        raise BlueprintError("duplicate_admission")
    scopes = {}
    pending = set(nodes)
    while pending:
        progressed = False
        for entity_id in sorted(pending):
            node = nodes[entity_id]
            if any(parent not in nodes for parent in node["parent_refs"]):
                raise BlueprintError("missing_parent")
            if any(parent not in scopes for parent in node["parent_refs"]):
                continue
            objectives = set(node["objective_refs"])
            repository_lineage = set(node["repository_lineage_refs"])
            governance_lineage = set(node["governance_lineage_refs"])
            gate_refs = set(node["governance_gate_refs"])
            for parent in node["parent_refs"]:
                objectives.update(scopes[parent][0])
                repository_lineage.update(scopes[parent][1])
                governance_lineage.update(scopes[parent][2])
                gate_refs.update(scopes[parent][3])
            scopes[entity_id] = objectives, repository_lineage, governance_lineage, gate_refs
            pending.remove(entity_id)
            progressed = True
        if not progressed:
            raise BlueprintError("ancestry_cycle")
    return nodes, scopes


def issue_trusted_admission_record(
    snapshot,
    entity_id,
    classification,
    *,
    trusted_mutation_target,
    trusted_current_digest,
    trusted_classification_digest,
    issuance_generation,
    issued_at,
    expires_at,
    issuer,
    issuer_provenance,
    minimum_snapshot_generation=None,
):
    """Issue the per-attempt trusted record from stored admission and trusted facts."""
    try:
        validate_snapshot_version(snapshot, minimum_generation=minimum_snapshot_generation)
    except AdmissionError as exc:
        raise BlueprintError(str(exc)) from exc
    if snapshot_digest(snapshot) != trusted_current_digest:
        raise BlueprintError("snapshot_not_current_or_not_pinned")
    if (not isinstance(classification, dict)
            or classification.get("classification_status") != "AUTHORITATIVE_REFERENCE_CLASSIFICATION"):
        raise BlueprintError("trusted_classification_required")
    unsigned_classification = deepcopy(classification)
    supplied_classification_digest = unsigned_classification.pop("classification_digest", None)
    if (type(trusted_classification_digest) is not str
            or supplied_classification_digest != trusted_classification_digest
            or _digest(unsigned_classification) != trusted_classification_digest):
        raise BlueprintError("classification_not_current_or_not_pinned")
    if type(entity_id) is not str:
        raise BlueprintError("invalid_entity")
    nodes, scopes = _effective_scopes(snapshot)
    if entity_id not in nodes:
        raise BlueprintError("unknown_entity")
    node = nodes[entity_id]
    objectives, repository_lineage, governance_lineage, gate_refs = scopes[entity_id]
    if (classification.get("admitted_entity_id") != entity_id
            or classification.get("admission_generation") != node["admission_generation"]):
        raise BlueprintError("classification_admission_identity_mismatch")
    if set(classification.get("objective_refs", ())) != objectives:
        raise BlueprintError("objective_attachment_mismatch")
    if set(classification.get("governance_lineage_refs", ())) != governance_lineage:
        raise BlueprintError("classification_governance_lineage_mismatch")
    actions = set(classification.get("action_classes", ()))
    if not actions or not actions.issubset(set(node["action_classes"])):
        raise BlueprintError("action_not_admitted")
    if (not isinstance(trusted_mutation_target, dict)
            or trusted_mutation_target != classification.get("mutation_target")):
        raise BlueprintError("mutation_target_mismatch")
    if type(issuance_generation) is not int or issuance_generation < node["admission_generation"]:
        raise BlueprintError("issuance_generation_rollback")
    if _time(expires_at) <= _time(issued_at):
        raise BlueprintError("invalid_freshness_window")
    _refs(issuer_provenance, "issuer_provenance")
    if not isinstance(issuer, dict):
        raise BlueprintError("invalid_issuer")
    authorities = {
        (authority["authority_id"], authority["authority_generation"]): authority
        for authority in snapshot["admission_authorities"]
    }
    authority = authorities.get((issuer.get("authority_id"), issuer.get("authority_generation")))
    if not authority or authority["authority_kind"] != "trusted_repository_control_plane":
        raise BlueprintError("unknown_issuance_authority")
    gates = {gate["gate_id"]: gate for gate in snapshot["gates"]}
    applicable = sorted(
        ({"gate_id": gate["gate_id"], "generation": gate["generation"]}
         for gate in gates.values()
         if (gate["gate_id"] in gate_refs
             or objectives.intersection(gate["scope"]["objective_refs"])
             or (repository_lineage | governance_lineage).intersection(
                 gate["scope"]["lineage_refs"]))),
        key=lambda value: (value["gate_id"], value["generation"]),
    )
    record = {
        "record_type": "TRUSTED_ADMISSION_RECORD",
        "record_version": 2,
        "entity_id": entity_id,
        "ancestry_kind": node["ancestry_kind"],
        "parent_refs": deepcopy(node["parent_refs"]),
        "repository_lineage_refs": sorted(repository_lineage),
        "governance_lineage_refs": sorted(governance_lineage),
        "objective_refs": sorted(objectives),
        "action_classes": sorted(actions),
        "applicable_gate_generations": applicable,
        "trusted_snapshot_generation": snapshot["snapshot_generation"],
        "trusted_snapshot_digest": trusted_current_digest,
        "mutation_target": deepcopy(trusted_mutation_target),
        "admission_generation": node["admission_generation"],
        "issuance_generation": issuance_generation,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "issued_by": deepcopy(issuer),
        "issuer_provenance": list(issuer_provenance),
        "classified_by": {
            "classifier_id": classification["classifier_id"],
            "classifier_generation": classification["classifier_generation"],
            "classifier_version": classification["classifier_version"],
        },
        "classification_digest": trusted_classification_digest,
        "classified_write_set": deepcopy(classification["classified_write_set"]),
        "write_set_digest": classification["write_set_digest"],
        "staged_patch_digest": classification["staged_patch_digest"],
        "classification_evidence": deepcopy(classification["evidence_refs"]),
        "human_release_evidence": [],
        "release_validation": "UNAVAILABLE",
    }
    if not ADMISSION_RECORD_VALIDATOR.is_valid(record):
        raise BlueprintError("invalid_trusted_admission_record")
    return record


def issue_mutation_authorization_ticket(
    snapshot,
    admission_record,
    *,
    trusted_current_digest,
    trusted_admission_record_digest,
    ticket_id,
    nonce,
    issued_at,
    expires_at,
    issuer_provenance,
    bridge_control_state,
    trusted_control_state_digest,
):
    """Issue a fenced reference ticket only when no effective gate blocks."""
    if not ADMISSION_RECORD_VALIDATOR.is_valid(admission_record):
        raise BlueprintError("invalid_trusted_admission_record")
    if (type(trusted_admission_record_digest) is not str
            or _digest(admission_record) != trusted_admission_record_digest):
        raise BlueprintError("admission_record_not_current_or_not_pinned")
    try:
        validate_snapshot_version(snapshot)
    except AdmissionError as exc:
        raise BlueprintError(str(exc)) from exc
    if (snapshot_digest(snapshot) != trusted_current_digest
            or admission_record["trusted_snapshot_digest"] != trusted_current_digest
            or admission_record["trusted_snapshot_generation"] != snapshot["snapshot_generation"]):
        raise BlueprintError("stale_snapshot")
    if (_time(issued_at) < _time(admission_record["issued_at"])
            or _time(expires_at) > _time(admission_record["expires_at"])
            or _time(expires_at) <= _time(issued_at)):
        raise BlueprintError("invalid_ticket_freshness")
    _refs(issuer_provenance, "issuer_provenance")
    control = _validate_control_state(
        bridge_control_state, trusted_control_state_digest
    )
    known_ticket_ids = set(control["issued_ticket_ids"])
    known_nonces = set(control["issued_nonces"])
    if ticket_id in known_ticket_ids:
        raise BlueprintError("duplicate_ticket_id")
    if nonce in known_nonces:
        raise BlueprintError("duplicate_ticket_nonce")
    nodes, scopes = _effective_scopes(snapshot)
    node = nodes.get(admission_record["entity_id"])
    if node is None or node["admission_generation"] != admission_record["admission_generation"]:
        raise BlueprintError("stale_admission_generation")
    objectives, repository_lineage, governance_lineage, gate_refs = scopes[node["entity_id"]]
    if (set(admission_record["objective_refs"]) != objectives
            or set(admission_record["repository_lineage_refs"]) != repository_lineage
            or set(admission_record["governance_lineage_refs"]) != governance_lineage):
        raise BlueprintError("admission_scope_no_longer_current")
    if not set(admission_record["action_classes"]).issubset(node["action_classes"]):
        raise BlueprintError("admission_action_no_longer_current")
    authorities = {
        (authority["authority_id"], authority["authority_generation"]): authority
        for authority in snapshot["admission_authorities"]
    }
    issuer = admission_record["issued_by"]
    authority = authorities.get((issuer["authority_id"], issuer["authority_generation"]))
    if not authority or authority["authority_kind"] != "trusted_repository_control_plane":
        raise BlueprintError("issuance_authority_no_longer_current")
    gates = {gate["gate_id"]: gate for gate in snapshot["gates"]}
    applicable = sorted(
        ({"gate_id": gate["gate_id"], "generation": gate["generation"]}
         for gate in gates.values()
         if (gate["gate_id"] in gate_refs
             or objectives.intersection(gate["scope"]["objective_refs"])
             or (repository_lineage | governance_lineage).intersection(
                 gate["scope"]["lineage_refs"]))),
        key=lambda value: (value["gate_id"], value["generation"]),
    )
    if applicable != admission_record["applicable_gate_generations"]:
        raise BlueprintError("stale_gate_generation")
    for gate in gates.values():
        if ({"gate_id": gate["gate_id"], "generation": gate["generation"]} in applicable
                and set(admission_record["action_classes"]).intersection(gate["blocked_actions"])):
            # Release validation is unavailable under Issue #31, including for
            # structurally released gate records.
            raise BlueprintError("blocked_pending_human_release")
    ticket = {
        "record_type": "MUTATION_AUTHORIZATION_TICKET",
        "record_version": 2,
        "ticket_id": ticket_id,
        "nonce": nonce,
        "admitted_entity_id": admission_record["entity_id"],
        "admission_record_digest": trusted_admission_record_digest,
        "objective_refs": deepcopy(admission_record["objective_refs"]),
        "repository_lineage_refs": deepcopy(admission_record["repository_lineage_refs"]),
        "governance_lineage_refs": deepcopy(admission_record["governance_lineage_refs"]),
        "action_classes": deepcopy(admission_record["action_classes"]),
        "mutation_target": deepcopy(admission_record["mutation_target"]),
        "classification_digest": admission_record["classification_digest"],
        "classified_write_set": deepcopy(admission_record["classified_write_set"]),
        "write_set_digest": admission_record["write_set_digest"],
        "staged_patch_digest": admission_record["staged_patch_digest"],
        "gate_snapshot_generation": snapshot["snapshot_generation"],
        "gate_snapshot_digest": trusted_current_digest,
        "applicable_gate_generations": applicable,
        "admission_generation": admission_record["admission_generation"],
        "issuance_generation": admission_record["issuance_generation"],
        "release_generations": [],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "issuer": deepcopy(admission_record["issued_by"]),
        "issuer_provenance": list(issuer_provenance),
    }
    ticket["state_digest"] = _digest(ticket)
    if not TICKET_VALIDATOR.is_valid(ticket):
        raise BlueprintError("invalid_mutation_authorization_ticket")
    advanced = _advance_control_state(
        control,
        issued_ticket_ids=sorted(known_ticket_ids | {ticket_id}),
        issued_nonces=sorted(known_nonces | {nonce}),
        issued_ticket_identities=sorted(
            set(control["issued_ticket_identities"])
            | {ticket_consumption_identity(ticket)}
        ),
    )
    return ticket, advanced


def ticket_current_state(ticket):
    """Construct the exact CAS state a real boundary would obtain independently."""
    return {
        "objective_refs": deepcopy(ticket["objective_refs"]),
        "admission_record_digest": ticket["admission_record_digest"],
        "repository_lineage_refs": deepcopy(ticket["repository_lineage_refs"]),
        "governance_lineage_refs": deepcopy(ticket["governance_lineage_refs"]),
        "mutation_target": deepcopy(ticket["mutation_target"]),
        "classification_digest": ticket["classification_digest"],
        "write_set_digest": ticket["write_set_digest"],
        "staged_patch_digest": ticket["staged_patch_digest"],
        "snapshot_generation": ticket["gate_snapshot_generation"],
        "snapshot_digest": ticket["gate_snapshot_digest"],
        "applicable_gate_generations": deepcopy(ticket["applicable_gate_generations"]),
        "admission_generation": ticket["admission_generation"],
        "issuance_generation": ticket["issuance_generation"],
        "release_generations": deepcopy(ticket["release_generations"]),
    }


def consume_mutation_authorization_ticket(
    ticket,
    current_state,
    *,
    requested_actions,
    current_time,
    actual_effect,
    bridge_control_state,
    trusted_control_state_digest,
):
    """Compare-and-swap proof: checked state must equal mutated state."""
    try:
        control = _validate_control_state(
            bridge_control_state, trusted_control_state_digest
        )
    except BlueprintError as exc:
        return BridgeDecision("REJECTED_NOT_AUTHORIZED", str(exc)), bridge_control_state
    reject = lambda reason: (BridgeDecision("REJECTED_NOT_AUTHORIZED", reason), control)
    if not TICKET_VALIDATOR.is_valid(ticket):
        return reject("invalid_ticket")
    unsigned = deepcopy(ticket)
    digest = unsigned.pop("state_digest")
    if _digest(unsigned) != digest:
        return reject("ticket_tampered")
    try:
        now = _time(current_time)
        if now < _time(ticket["issued_at"]) or now >= _time(ticket["expires_at"]):
            return reject("ticket_expired_or_not_yet_valid")
        actions = set(_refs(requested_actions, "requested_actions"))
    except BlueprintError as exc:
        return reject(str(exc))
    consumption_identity = ticket_consumption_identity(ticket)
    if (ticket["ticket_id"] not in control["issued_ticket_ids"]
            or ticket["nonce"] not in control["issued_nonces"]
            or consumption_identity not in control["issued_ticket_identities"]):
        return reject("ticket_not_authoritatively_issued")
    consumed_identities = control["consumed_ticket_identities"]
    if consumption_identity in set(consumed_identities):
        return reject("ticket_replay")
    if not actions.issubset(set(ticket["action_classes"])):
        return reject("ticket_scope_exceeded")
    if not isinstance(actual_effect, dict) or set(actual_effect) != {
        "mutation_target", "classified_write_set", "staged_patch_digest",
        "classification_digest",
    }:
        return reject("BLOCKED_EFFECT_MISMATCH")
    try:
        actual_write_set = _canonical_write_set(actual_effect["classified_write_set"])
        actual_write_set_digest = classified_write_set_digest(actual_write_set)
    except BlueprintError:
        return reject("BLOCKED_EFFECT_MISMATCH")
    if (actual_effect["mutation_target"] != ticket["mutation_target"]
            or actual_effect["classification_digest"] != ticket["classification_digest"]
            or actual_effect["staged_patch_digest"] != ticket["staged_patch_digest"]
            or actual_write_set != ticket["classified_write_set"]
            or actual_write_set_digest != ticket["write_set_digest"]):
        return reject("BLOCKED_EFFECT_MISMATCH")
    expected = ticket_current_state(ticket)
    if not isinstance(current_state, dict) or set(current_state) != set(expected):
        return reject("invalid_current_state")
    comparisons = (
        ("admission_record_digest", "admission_record_changed"),
        ("objective_refs", "objective_changed"),
        ("repository_lineage_refs", "ancestry_changed"),
        ("governance_lineage_refs", "governance_lineage_changed"),
        ("mutation_target", "mutation_target_or_head_changed"),
        ("classification_digest", "classification_changed"),
        ("write_set_digest", "classified_write_set_changed"),
        ("staged_patch_digest", "staged_patch_changed"),
        ("snapshot_generation", "gate_generation_changed"),
        ("snapshot_digest", "snapshot_stale"),
        ("applicable_gate_generations", "gate_generation_changed"),
        ("admission_generation", "admission_generation_changed"),
        ("issuance_generation", "issuance_generation_changed"),
        ("release_generations", "human_release_revoked_or_superseded"),
    )
    for field, reason in comparisons:
        if current_state[field] != expected[field]:
            return reject(reason)
    advanced = _advance_control_state(
        control,
        consumed_ticket_identities=sorted(
            set(consumed_identities) | {consumption_identity}
        ),
    )
    return (BridgeDecision(
        "CONSUMABLE_REFERENCE_TICKET_NOT_PRODUCTION_AUTHORITY",
        "atomic_boundary_must_consume_with_the_mutation",
    ), advanced)


def issue_trusted_task_record(
    worker_task,
    admission_record,
    *,
    owner,
    bridge_control_state,
    trusted_control_state_digest,
):
    """Bind one exact task payload to its authoritative admitted owner."""
    if not isinstance(worker_task, dict):
        raise BlueprintError("invalid_worker_proposal")
    if not ADMISSION_RECORD_VALIDATOR.is_valid(admission_record):
        raise BlueprintError("trusted_admission_required")
    required = {
        "task_id", "admitted_entity_id", "parent_entity_refs", "objective_refs",
        "governance_lineage_refs", "admission_generation",
    }
    if not required.issubset(worker_task):
        raise BlueprintError("task_admission_binding_required")
    if (worker_task["task_id"] != admission_record["entity_id"]
            or worker_task["admitted_entity_id"] != admission_record["entity_id"]):
        raise BlueprintError("task_admission_identity_mismatch")
    if (worker_task["parent_entity_refs"] != admission_record["parent_refs"]
            or worker_task["objective_refs"] != admission_record["objective_refs"]
            or worker_task["governance_lineage_refs"] !=
            admission_record["governance_lineage_refs"]
            or worker_task["admission_generation"] !=
            admission_record["admission_generation"]):
        raise BlueprintError("task_admission_provenance_mismatch")
    control = _validate_control_state(
        bridge_control_state, trusted_control_state_digest
    )
    if admission_record["entity_id"] in set(control["issued_task_ids"]):
        raise BlueprintError("duplicate_task_identity")
    if not isinstance(owner, dict):
        raise BlueprintError("invalid_task_owner")
    matches = [entry for entry in control["task_owners"]
               if isinstance(entry, Mapping)
               and entry.get("task_id") == admission_record["entity_id"]
               and entry.get("admitted_entity_id") == admission_record["entity_id"]
               and entry.get("owned_by") == owner]
    if len(matches) != 1:
        raise BlueprintError("untrusted_or_ambiguous_task_owner")
    record = {
        "record_type": "TRUSTED_TASK_RECORD",
        "record_version": 1,
        "task_id": admission_record["entity_id"],
        "admitted_entity_id": admission_record["entity_id"],
        "parent_entity_refs": deepcopy(admission_record["parent_refs"]),
        "objective_refs": deepcopy(admission_record["objective_refs"]),
        "governance_lineage_refs": deepcopy(admission_record["governance_lineage_refs"]),
        "admission_generation": admission_record["admission_generation"],
        "admission_record_digest": _digest(admission_record),
        "worker_payload_digest": _digest(worker_task),
        "owned_by": deepcopy(owner),
    }
    if not TRUSTED_TASK_VALIDATOR.is_valid(record):
        raise BlueprintError("invalid_trusted_task_record")
    advanced = _advance_control_state(
        control,
        issued_task_ids=sorted(
            set(control["issued_task_ids"]) | {record["task_id"]}
        ),
    )
    return record, advanced


def attach_task_or_queue_record(
    worker_task,
    admission_record,
    *,
    trusted_task_record=None,
    trusted_task_record_digest=None,
    bridge_control_state=None,
    trusted_control_state_digest=None,
):
    """Attach one independently pinned task identity; worker prose grants nothing."""
    if not isinstance(worker_task, dict):
        raise BlueprintError("invalid_worker_proposal")
    if not ADMISSION_RECORD_VALIDATOR.is_valid(admission_record):
        raise BlueprintError("trusted_admission_required")
    if (not TRUSTED_TASK_VALIDATOR.is_valid(trusted_task_record)
            or trusted_task_record_digest != _digest(trusted_task_record)):
        raise BlueprintError("trusted_task_record_required")
    control = _validate_control_state(
        bridge_control_state, trusted_control_state_digest
    )
    if trusted_task_record["task_id"] not in control["issued_task_ids"]:
        raise BlueprintError("task_not_authoritatively_issued")
    owner_matches = [entry for entry in control["task_owners"]
                     if entry["task_id"] == trusted_task_record["task_id"]
                     and entry["admitted_entity_id"] ==
                     trusted_task_record["admitted_entity_id"]
                     and entry["owned_by"] == trusted_task_record["owned_by"]]
    if len(owner_matches) != 1:
        raise BlueprintError("untrusted_or_ambiguous_task_owner")
    if trusted_task_record["task_id"] in set(control["attached_task_ids"]):
        raise BlueprintError("duplicate_task_attachment")
    expected = {
        "task_id": admission_record["entity_id"],
        "admitted_entity_id": admission_record["entity_id"],
        "parent_entity_refs": admission_record["parent_refs"],
        "objective_refs": admission_record["objective_refs"],
        "governance_lineage_refs": admission_record["governance_lineage_refs"],
        "admission_generation": admission_record["admission_generation"],
        "admission_record_digest": _digest(admission_record),
        "worker_payload_digest": _digest(worker_task),
    }
    if any(trusted_task_record.get(field) != value
           for field, value in expected.items()):
        raise BlueprintError("task_admission_provenance_mismatch")
    attachment = {
        "attachment_status": "ADMITTED_REFERENCE_ONLY",
        "task_id": trusted_task_record["task_id"],
        "admitted_entity_id": admission_record["entity_id"],
        "parent_entity_refs": deepcopy(admission_record["parent_refs"]),
        "objective_refs": deepcopy(admission_record["objective_refs"]),
        "governance_lineage_refs": deepcopy(admission_record["governance_lineage_refs"]),
        "admission_generation": admission_record["admission_generation"],
        "admission_record_digest": _digest(admission_record),
        "trusted_task_record_digest": trusted_task_record_digest,
        "trusted_task_record": deepcopy(trusted_task_record),
        "worker_proposal": deepcopy(worker_task),
        "trusted_admission_record": deepcopy(admission_record),
    }
    advanced = _advance_control_state(
        control,
        attached_task_ids=sorted(
            set(control["attached_task_ids"]) | {trusted_task_record["task_id"]}
        ),
    )
    return attachment, advanced


def restore_task_or_queue_attachment(persisted):
    """Restart never reconstructs authority from worker text."""
    if not isinstance(persisted, dict):
        return BridgeDecision(
            "QUARANTINED_MISSING_TRUSTED_LINEAGE",
            "restart_requires_persisted_trusted_admission",
        )
    record = persisted.get("trusted_admission_record")
    if not ADMISSION_RECORD_VALIDATOR.is_valid(record):
        return BridgeDecision(
            "QUARANTINED_MISSING_TRUSTED_LINEAGE",
            "restart_requires_persisted_trusted_admission",
        )
    task_record = persisted.get("trusted_task_record")
    if (not TRUSTED_TASK_VALIDATOR.is_valid(task_record)
            or persisted.get("trusted_task_record_digest") != _digest(task_record)
            or task_record.get("worker_payload_digest") !=
            _digest(persisted.get("worker_proposal", {}))):
        return BridgeDecision(
            "QUARANTINED_PROVENANCE_MISMATCH",
            "restart_requires_persisted_trusted_task_ownership",
        )
    expected = {
        "task_id": record["entity_id"],
        "admitted_entity_id": record["entity_id"],
        "parent_entity_refs": record["parent_refs"],
        "objective_refs": record["objective_refs"],
        "governance_lineage_refs": record["governance_lineage_refs"],
        "admission_generation": record["admission_generation"],
        "admission_record_digest": _digest(record),
        "trusted_task_record_digest": _digest(task_record),
    }
    task_expected = {key: value for key, value in expected.items()
                     if key != "trusted_task_record_digest"}
    if (any(persisted.get(field) != value for field, value in expected.items())
            or any(task_record.get(field) != value
                   for field, value in task_expected.items())):
        return BridgeDecision(
            "QUARANTINED_PROVENANCE_MISMATCH",
            "persisted_task_admission_binding_changed",
        )
    return BridgeDecision("ADMITTED_REFERENCE_ONLY", "ticket_still_required")


def execution_context_digest(context):
    """Digest immutable admission and ticket state across cycles and restarts."""
    if not isinstance(context, Mapping):
        raise BlueprintError("missing_execution_admission_context")
    immutable = {
        key: deepcopy(value) for key, value in context.items()
        if key not in {"provider", "session", "context_digest"}
    }
    return _digest(immutable)


def carry_execution_context(context, *, provider, session):
    """Provider/session changes preserve, and cannot replace, admitted identity."""
    required = {
        "admitted_entity_id", "admission_record_digest", "ticket_id", "nonce",
        "classification_digest", "write_set_digest", "objective_refs",
        "repository_lineage_refs", "governance_lineage_refs",
        "applicable_gate_generations", "admission_generation",
        "snapshot_generation", "snapshot_digest",
        "ticket_state_digest", "ticket_consumption_identity", "context_digest",
    }
    if not isinstance(context, dict) or not required.issubset(context):
        raise BlueprintError("missing_execution_admission_context")
    if context["context_digest"] != execution_context_digest(context):
        raise BlueprintError("execution_context_digest_mismatch")
    result = deepcopy(context)
    result["provider"] = provider
    result["session"] = session
    return result


def ticket_bound_actual_effect(ticket):
    """Reference fixture shape; production must derive this from the real attempt."""
    return {
        "mutation_target": deepcopy(ticket["mutation_target"]),
        "classified_write_set": deepcopy(ticket["classified_write_set"]),
        "staged_patch_digest": ticket["staged_patch_digest"],
        "classification_digest": ticket["classification_digest"],
    }


def record_mutation_result(
    ticket,
    actual_effect,
    *,
    result_identity,
    mutation_status,
    evidence_persisted,
    bridge_control_state,
    trusted_control_state_digest,
):
    """Create a fail-closed effect receipt after a single consumed attempt."""
    if not TICKET_VALIDATOR.is_valid(ticket):
        raise BlueprintError("invalid_ticket")
    unsigned_ticket = deepcopy(ticket)
    supplied_ticket_digest = unsigned_ticket.pop("state_digest")
    if _digest(unsigned_ticket) != supplied_ticket_digest:
        raise BlueprintError("invalid_ticket")
    consumption_identity = ticket_consumption_identity(ticket)
    control = _validate_control_state(
        bridge_control_state, trusted_control_state_digest
    )
    if consumption_identity not in set(control["consumed_ticket_identities"]):
        raise BlueprintError("consumed_ticket_required")
    if ticket_bound_actual_effect(ticket) != actual_effect:
        raise BlueprintError("BLOCKED_EFFECT_MISMATCH")
    if mutation_status not in {"succeeded", "failed", "partial"}:
        raise BlueprintError("invalid_mutation_status")
    if type(evidence_persisted) is not bool:
        raise BlueprintError("invalid_evidence_status")
    if not isinstance(result_identity, dict):
        raise BlueprintError("invalid_result_identity")
    if result_identity.get("write_set_digest") != ticket["write_set_digest"]:
        raise BlueprintError("invalid_result_identity")
    if mutation_status == "succeeded" and evidence_persisted:
        authority_state = "EXECUTED_PENDING_VERIFICATION"
    elif mutation_status == "succeeded":
        authority_state = "QUARANTINED_INCOMPLETE_EVIDENCE"
    elif mutation_status == "partial":
        authority_state = "QUARANTINED_PARTIAL_MUTATION"
    else:
        authority_state = "QUARANTINED_MUTATION_FAILED"
    result = {
        "record_type": "MUTATION_RESULT",
        "record_version": 1,
        "ticket_id": ticket["ticket_id"],
        "ticket_nonce": ticket["nonce"],
        "ticket_consumption_identity": consumption_identity,
        "ticket_state_digest": ticket["state_digest"],
        "bridge_control_state_digest": trusted_control_state_digest,
        "bridge_control_state_generation": control["registry_generation"],
        "admission_record_digest": ticket["admission_record_digest"],
        "classification_digest": ticket["classification_digest"],
        "write_set_digest": ticket["write_set_digest"],
        "staged_patch_digest": ticket["staged_patch_digest"],
        "result_identity": deepcopy(result_identity),
        "mutation_status": mutation_status,
        "evidence_persisted": evidence_persisted,
        "authority_state": authority_state,
    }
    result["result_record_digest"] = _digest(result)
    if not MUTATION_RESULT_VALIDATOR.is_valid(result):
        raise BlueprintError("invalid_mutation_result")
    return result


def record_verification_evidence(
    mutation_result,
    *,
    observed_result_identity,
    verdict,
    verifier_id,
    verifier_generation,
    verifier_provenance,
    bridge_control_state,
    trusted_control_state_digest,
):
    """Bind technical verification to one immutable mutation result identity."""
    if not MUTATION_RESULT_VALIDATOR.is_valid(mutation_result):
        raise BlueprintError("invalid_mutation_result")
    unsigned_result = deepcopy(mutation_result)
    supplied_result_digest = unsigned_result.pop("result_record_digest")
    if _digest(unsigned_result) != supplied_result_digest:
        raise BlueprintError("invalid_mutation_result")
    _refs(verifier_provenance, "verifier_provenance")
    control = _validate_control_state(
        bridge_control_state, trusted_control_state_digest
    )
    matches = [entry for entry in control["verifiers"]
               if isinstance(entry, Mapping)
               and entry.get("verifier_id") == verifier_id
               and entry.get("verifier_generation") == verifier_generation
               and entry.get("provenance") == list(verifier_provenance)]
    if len(matches) != 1:
        raise BlueprintError("untrusted_or_ambiguous_verifier")
    if verdict not in {"PASS", "FAIL"}:
        raise BlueprintError("invalid_verification_verdict")
    evidence = {
        "record_type": "VERIFICATION_EVIDENCE",
        "record_version": 1,
        "mutation_result_digest": mutation_result["result_record_digest"],
        "ticket_id": mutation_result["ticket_id"],
        "result_identity": deepcopy(observed_result_identity),
        "verdict": verdict,
        "verifier_id": verifier_id,
        "verifier_generation": verifier_generation,
        "verifier_provenance": list(verifier_provenance),
        "bridge_control_state_digest": trusted_control_state_digest,
        "bridge_control_state_generation": control["registry_generation"],
    }
    evidence["verification_digest"] = _digest(evidence)
    if not VERIFICATION_VALIDATOR.is_valid(evidence):
        raise BlueprintError("invalid_verification_evidence")
    return evidence


def _assess_provenance_chain(
    admission_record,
    ticket,
    mutation_result,
    verification,
    *,
    current_result_identity,
):
    """Validate Admission → Ticket → Effect → Result → Verification provenance."""
    blocked = lambda reason: BridgeDecision("BLOCKED_PROVENANCE_MISMATCH", reason)
    if (not ADMISSION_RECORD_VALIDATOR.is_valid(admission_record)
            or not TICKET_VALIDATOR.is_valid(ticket)
            or not MUTATION_RESULT_VALIDATOR.is_valid(mutation_result)
            or not VERIFICATION_VALIDATOR.is_valid(verification)):
        return blocked("invalid_provenance_record")
    unsigned_ticket = deepcopy(ticket)
    ticket_digest = unsigned_ticket.pop("state_digest")
    unsigned_result = deepcopy(mutation_result)
    result_digest = unsigned_result.pop("result_record_digest")
    unsigned_verification = deepcopy(verification)
    verification_digest = unsigned_verification.pop("verification_digest")
    if (_digest(unsigned_ticket) != ticket_digest
            or _digest(unsigned_result) != result_digest
            or _digest(unsigned_verification) != verification_digest):
        return blocked("tampered_provenance_record")
    if (_digest(admission_record) != ticket["admission_record_digest"]
            or mutation_result["ticket_id"] != ticket["ticket_id"]
            or mutation_result["ticket_nonce"] != ticket["nonce"]
            or mutation_result["ticket_consumption_identity"] !=
            ticket_consumption_identity(ticket)
            or mutation_result["ticket_state_digest"] != ticket["state_digest"]
            or mutation_result["classification_digest"] != ticket["classification_digest"]
            or mutation_result["write_set_digest"] != ticket["write_set_digest"]):
        return blocked("authority_chain_link_mismatch")
    if (verification["mutation_result_digest"] != mutation_result["result_record_digest"]
            or verification["ticket_id"] != ticket["ticket_id"]):
        return blocked("verification_ticket_or_result_mismatch")
    if (mutation_result["mutation_status"] != "succeeded"
            or mutation_result["evidence_persisted"] is not True
            or mutation_result["authority_state"] != "EXECUTED_PENDING_VERIFICATION"):
        return BridgeDecision(
            "QUARANTINED_INCOMPLETE_EVIDENCE",
            "mutation_or_evidence_not_complete",
        )
    if (verification["verdict"] != "PASS"
            or verification["result_identity"] != mutation_result["result_identity"]
            or current_result_identity != mutation_result["result_identity"]):
        return blocked("stale_or_different_result_identity")
    return BridgeDecision("PROVENANCE_CHAIN_VALID_REFERENCE_ONLY")


def issue_progression_authorization(
    admission_record,
    ticket,
    mutation_result,
    verification,
    *,
    current_result_identity,
    authority,
    authority_provenance,
    bridge_control_state,
    trusted_control_state_digest,
):
    """Issue a trusted progression decision only for one complete exact chain."""
    chain = _assess_provenance_chain(
        admission_record, ticket, mutation_result, verification,
        current_result_identity=current_result_identity,
    )
    if chain.disposition != "PROVENANCE_CHAIN_VALID_REFERENCE_ONLY":
        raise BlueprintError(chain.reason)
    _refs(authority_provenance, "progression_authority_provenance")
    if not isinstance(authority, dict):
        raise BlueprintError("invalid_progression_authority")
    control = _validate_control_state(
        bridge_control_state, trusted_control_state_digest
    )
    matches = [entry for entry in control["progression_authorities"]
               if isinstance(entry, Mapping)
               and entry.get("authority_id") == authority.get("authority_id")
               and entry.get("authority_generation") ==
               authority.get("authority_generation")
               and entry.get("provenance") == list(authority_provenance)]
    if len(matches) != 1:
        raise BlueprintError("untrusted_or_ambiguous_progression_authority")
    decision = {
        "record_type": "PROGRESSION_AUTHORIZATION",
        "record_version": 1,
        "admission_record_digest": _digest(admission_record),
        "ticket_state_digest": ticket["state_digest"],
        "ticket_consumption_identity": ticket_consumption_identity(ticket),
        "mutation_result_digest": mutation_result["result_record_digest"],
        "verification_digest": verification["verification_digest"],
        "result_identity": deepcopy(current_result_identity),
        "authorized_by": deepcopy(authority),
        "authority_provenance": list(authority_provenance),
        "bridge_control_state_digest": trusted_control_state_digest,
        "bridge_control_state_generation": control["registry_generation"],
    }
    decision["progression_authorization_digest"] = _digest(decision)
    if not PROGRESSION_AUTHORIZATION_VALIDATOR.is_valid(decision):
        raise BlueprintError("invalid_progression_authorization")
    return decision


def authorize_progress_chain(
    admission_record,
    ticket,
    mutation_result,
    verification,
    progression_authorization,
    *,
    current_result_identity,
    bridge_control_state,
    trusted_control_state_digest,
):
    """Consume one authenticated progression decision for the exact full chain."""
    chain = _assess_provenance_chain(
        admission_record, ticket, mutation_result, verification,
        current_result_identity=current_result_identity,
    )
    if chain.disposition != "PROVENANCE_CHAIN_VALID_REFERENCE_ONLY":
        return chain
    blocked = lambda reason: BridgeDecision("BLOCKED_PROVENANCE_MISMATCH", reason)
    try:
        control = _validate_control_state(
            bridge_control_state, trusted_control_state_digest
        )
    except BlueprintError as exc:
        return blocked(str(exc))
    if not PROGRESSION_AUTHORIZATION_VALIDATOR.is_valid(progression_authorization):
        return blocked("trusted_progression_authorization_required")
    unsigned = deepcopy(progression_authorization)
    supplied_digest = unsigned.pop("progression_authorization_digest")
    if _digest(unsigned) != supplied_digest:
        return blocked("tampered_progression_authorization")
    expected = {
        "admission_record_digest": _digest(admission_record),
        "ticket_state_digest": ticket["state_digest"],
        "ticket_consumption_identity": ticket_consumption_identity(ticket),
        "mutation_result_digest": mutation_result["result_record_digest"],
        "verification_digest": verification["verification_digest"],
        "result_identity": current_result_identity,
        "bridge_control_state_digest": trusted_control_state_digest,
        "bridge_control_state_generation": control["registry_generation"],
    }
    if any(progression_authorization.get(field) != value
           for field, value in expected.items()):
        return blocked("progression_authorization_chain_mismatch")
    authority = progression_authorization["authorized_by"]
    provenance = progression_authorization["authority_provenance"]
    matches = [entry for entry in control["progression_authorities"]
               if isinstance(entry, Mapping)
               and entry.get("authority_id") == authority.get("authority_id")
               and entry.get("authority_generation") ==
               authority.get("authority_generation")
               and entry.get("provenance") == provenance]
    if len(matches) != 1:
        return blocked("untrusted_or_ambiguous_progression_authority")
    return BridgeDecision(
        "AUTHORIZED_PROGRESS",
        "complete_authenticated_provenance_chain_reference_only",
    )


def mediated_writer_status(writer, *, integrated_writers=()):
    """Inventory classification only; it does not inspect or guard a writer."""
    if writer in set(integrated_writers):
        return BridgeDecision("REFERENCE_INTEGRATION_CLAIM_UNPROVEN")
    if writer in KNOWN_MEDIATED_WRITERS:
        return BridgeDecision("NOT_ENFORCED", "known_writer_not_integrated")
    return BridgeDecision("NOT_ENFORCED", "unknown_writer_outside_enforcement_plane")


def progress_transition(
    current_state,
    event,
    *,
    provenance_chain=None,
    current_result_identity=None,
    bridge_control_state=None,
    trusted_control_state_digest=None,
    trusted_admission_decision=False,
):
    """Keep technical verification separate from governance progression."""
    if current_state not in PROGRESS_STATES:
        raise BlueprintError("unknown_progress_state")
    if event == "preserve" and current_state == "OBSERVED_UNTRUSTED":
        return "PRESERVED_EVIDENCE"
    if event == "admit" and current_state in {"OBSERVED_UNTRUSTED", "PRESERVED_EVIDENCE"}:
        if not trusted_admission_decision:
            raise BlueprintError("trusted_admission_required")
        return "ADMITTED"
    if event == "authorize_execute" and current_state == "ADMITTED":
        if not isinstance(provenance_chain, dict) or "ticket" not in provenance_chain:
            raise BlueprintError("consumed_ticket_required")
        ticket = provenance_chain["ticket"]
        control = _validate_control_state(
            bridge_control_state, trusted_control_state_digest
        )
        if (not TICKET_VALIDATOR.is_valid(ticket)
                or ticket_consumption_identity(ticket) not in
                control["consumed_ticket_identities"]):
            raise BlueprintError("consumed_ticket_required")
        return "AUTHORIZED_TO_EXECUTE"
    if event == "execute" and current_state == "AUTHORIZED_TO_EXECUTE":
        return "EXECUTED_PENDING_VERIFICATION"
    if event == "verify_pass" and current_state in {
        "OBSERVED_UNTRUSTED", "PRESERVED_EVIDENCE", "EXECUTED_PENDING_VERIFICATION"
    }:
        return "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION"
    if event == "authorize_progress" and current_state == "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION":
        if not isinstance(provenance_chain, dict):
            raise BlueprintError("verification_is_not_authorization")
        required = {
            "admission_record", "ticket", "mutation_result", "verification",
            "progression_authorization",
        }
        if set(provenance_chain) != required:
            raise BlueprintError("verification_is_not_authorization")
        decision = authorize_progress_chain(
            provenance_chain["admission_record"], provenance_chain["ticket"],
            provenance_chain["mutation_result"], provenance_chain["verification"],
            provenance_chain["progression_authorization"],
            current_result_identity=current_result_identity,
            bridge_control_state=bridge_control_state,
            trusted_control_state_digest=trusted_control_state_digest,
        )
        if decision.disposition != "AUTHORIZED_PROGRESS":
            raise BlueprintError(decision.reason)
        return decision.disposition
    raise BlueprintError("invalid_progress_transition")


def classify_unmediated_output(*, verification_pass=False):
    """Raw external output can exist and be preserved, but remains ungoverned."""
    return {
        "state": ("VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION"
                  if verification_pass else "PRESERVED_EVIDENCE"),
        "external_write_enforcement": "NOT_ENFORCED",
        "authorized_progress": False,
    }


# Governance-v2 result/verification/progression reference path.  These records
# intentionally do not integrate a writer; they define the transaction that a
# future trusted adapter must implement atomically.
def _validate_v2_control(state, trusted_digest):
    if (not GOVERNANCE_CONTROL_V2_VALIDATOR.is_valid(state)
            or type(trusted_digest) is not str or _digest(state) != trusted_digest):
        raise BlueprintError("governance_control_state_not_current_or_not_pinned")
    history = state["state_history"]
    expected_generations = list(range(1, state["state_generation"]))
    if [entry["state_generation"] for entry in history] != expected_generations:
        raise BlueprintError("control_state_ancestry_discontinuous")
    if state["state_generation"] == 1:
        if history or state["previous_state_digest"] != "0" * 64:
            raise BlueprintError("control_state_ancestry_discontinuous")
    elif (not history
          or history[-1]["state_digest"] != state["previous_state_digest"]):
        raise BlueprintError("control_state_ancestry_discontinuous")
    return state


def _v2_principal(control, principal, role):
    if not isinstance(principal, Mapping):
        raise BlueprintError("untrusted_principal")
    matches = [item for item in control["principals"]
               if item["principal_id"] == principal.get("principal_id")
               and item["principal_generation"] == principal.get("principal_generation")
               and role in item["roles"]]
    if len(matches) != 1:
        raise BlueprintError("untrusted_principal")
    return matches[0]


def _advance_v2(control, **updates):
    current_digest = _digest(control)
    advanced = deepcopy(control)
    advanced["state_generation"] += 1
    advanced["previous_state_digest"] = current_digest
    advanced["state_history"].append({
        "state_generation": control["state_generation"],
        "state_digest": current_digest,
    })
    for key, value in updates.items():
        advanced[key] = deepcopy(value)
    if not GOVERNANCE_CONTROL_V2_VALIDATOR.is_valid(advanced):
        raise BlueprintError("invalid_governance_control_transition")
    return advanced


def canonical_git_result_identity(*, commit_sha, tree_sha, repository_head_sha,
                                  write_set_digest, effect_digest):
    """Build a discriminated result identity; commit identity is never an alias."""
    identity = {
        "kind": "git_commit", "commit_sha": commit_sha, "tree_sha": tree_sha,
        "repository_head_sha": repository_head_sha,
        "write_set_digest": write_set_digest, "effect_digest": effect_digest,
    }
    validator = Draft202012Validator({"$schema": BRIDGE_SCHEMA["$schema"],
        "$defs": BRIDGE_SCHEMA["$defs"], "$ref": "#/$defs/canonical_result_identity"})
    if not validator.is_valid(identity):
        raise BlueprintError("invalid_result_identity")
    if commit_sha != repository_head_sha:
        raise BlueprintError("commit_head_mismatch")
    return identity


def prepare_effect_transaction(ticket, actual_effect, *, transaction_id,
                               producer, repository_pre_state_sha,
                               bridge_control_state, trusted_control_state_digest):
    """Consume a ticket and append PREPARED in one reference-state transition."""
    control = _validate_v2_control(bridge_control_state, trusted_control_state_digest)
    producer_record = _v2_principal(control, producer, "producer")
    if not TICKET_VALIDATOR.is_valid(ticket):
        raise BlueprintError("invalid_ticket")
    unsigned = deepcopy(ticket)
    if _digest({k: v for k, v in unsigned.items() if k != "state_digest"}) != ticket["state_digest"]:
        raise BlueprintError("invalid_ticket")
    identity = ticket_consumption_identity(ticket)
    if identity not in control["issued_ticket_identities"]:
        raise BlueprintError("ticket_not_authoritatively_issued")
    if identity in control["consumed_ticket_identities"]:
        raise BlueprintError("ticket_replay")
    if actual_effect != ticket_bound_actual_effect(ticket):
        raise BlueprintError("BLOCKED_EFFECT_MISMATCH")
    if repository_pre_state_sha != ticket["mutation_target"]["expected_head_sha"]:
        raise BlueprintError("stale_repository_pre_state")
    if any(item["transaction_id"] == transaction_id for item in control["transactions"]):
        raise BlueprintError("duplicate_transaction")
    transaction = {
        "record_type": "EFFECT_TRANSACTION", "record_version": 2,
        "transaction_id": transaction_id, "state": "PREPARED",
        "ticket_id": ticket["ticket_id"], "ticket_state_digest": ticket["state_digest"],
        "ticket_consumption_identity": identity,
        "admission_record_digest": ticket["admission_record_digest"],
        "classification_digest": ticket["classification_digest"],
        "mutation_target": deepcopy(ticket["mutation_target"]),
        "write_set_digest": ticket["write_set_digest"],
        "staged_patch_digest": ticket["staged_patch_digest"],
        "producer": {"principal_id": producer_record["principal_id"],
                     "principal_generation": producer_record["principal_generation"],
                     "independence_group": producer_record["independence_group"]},
        "observer": None, "observer_provenance": None,
        "observation_generation": None, "observed_at": None,
        "repository_pre_state_sha": repository_pre_state_sha,
        "actual_effect_digest": _digest(actual_effect), "receipt": None,
        "result": None, "transaction_digest": "0" * 64,
    }
    transaction["transaction_digest"] = _digest({k: v for k, v in transaction.items()
                                                  if k != "transaction_digest"})
    if not EFFECT_TRANSACTION_VALIDATOR.is_valid(transaction):
        raise BlueprintError("invalid_effect_transaction")
    advanced = _advance_v2(
        control,
        consumed_ticket_identities=control["consumed_ticket_identities"] + [identity],
        transactions=control["transactions"] + [transaction],
    )
    return transaction, advanced


def observe_effect_transaction(transaction, *, observer, outcome,
                               observed_pre_state_sha, observed_post_state,
                               result_identity,
                               evidence_persisted, observed_at,
                               bridge_control_state,
                               trusted_control_state_digest):
    """Append a trusted exact-effect observation and classify crash outcomes."""
    control = _validate_v2_control(bridge_control_state, trusted_control_state_digest)
    registered = _v2_principal(control, observer, "effect_observer")
    stored = [item for item in control["transactions"]
              if item["transaction_id"] == transaction.get("transaction_id")]
    if len(stored) != 1 or stored[0] != transaction or transaction["state"] != "PREPARED":
        raise BlueprintError("transaction_not_current_prepared")
    if observed_pre_state_sha != transaction["repository_pre_state_sha"]:
        raise BlueprintError("concurrent_repository_mutation")
    if outcome not in {"succeeded", "failed", "partial", "ambiguous"}:
        raise BlueprintError("invalid_observed_outcome")
    if type(evidence_persisted) is not bool:
        raise BlueprintError("invalid_evidence_status")
    if outcome == "succeeded":
        validator = Draft202012Validator({"$schema": BRIDGE_SCHEMA["$schema"],
            "$defs": BRIDGE_SCHEMA["$defs"], "$ref": "#/$defs/canonical_result_identity"})
        if not validator.is_valid(result_identity):
            raise BlueprintError("invalid_result_identity")
        if (result_identity["write_set_digest"] != transaction["write_set_digest"] or
                result_identity["effect_digest"] != transaction["actual_effect_digest"]):
            raise BlueprintError("effect_result_digest_mismatch")
        if (result_identity["kind"] == "git_commit"
                and result_identity["commit_sha"] != result_identity["repository_head_sha"]):
            raise BlueprintError("commit_head_mismatch")
        expected_post = {
            "commit_sha": result_identity.get("commit_sha"),
            "tree_sha": result_identity.get("tree_sha"),
            "repository_head_sha": result_identity["repository_head_sha"],
            "write_set_digest": result_identity["write_set_digest"],
            "effect_digest": result_identity["effect_digest"],
        }
        if observed_post_state != expected_post:
            raise BlueprintError("commit_tree_or_effect_observation_mismatch")
    elif result_identity is not None:
        raise BlueprintError("result_identity_for_non_success")
    elif observed_post_state is not None:
        raise BlueprintError("post_state_for_non_success")
    if outcome == "partial":
        state = "QUARANTINED"
    elif outcome == "ambiguous":
        state = "RECONCILIATION_REQUIRED"
    elif not evidence_persisted:
        state = "QUARANTINED"
    elif outcome == "failed":
        state = "QUARANTINED"
    else:
        state = "OBSERVED_SUCCEEDED"
    receipt = {
        "record_type": "EXACT_EFFECT_RECEIPT", "record_version": 2,
        "transaction_id": transaction["transaction_id"],
        "ticket_id": transaction["ticket_id"],
        "ticket_state_digest": transaction["ticket_state_digest"],
        "ticket_consumption_identity": transaction["ticket_consumption_identity"],
        "admission_record_digest": transaction["admission_record_digest"],
        "classification_digest": transaction["classification_digest"],
        "mutation_target": deepcopy(transaction["mutation_target"]),
        "write_set_digest": transaction["write_set_digest"],
        "staged_patch_digest": transaction["staged_patch_digest"],
        "actual_effect_digest": transaction["actual_effect_digest"],
        "repository_pre_state_sha": observed_pre_state_sha,
        "producer": deepcopy(transaction["producer"]),
        "observer": {"principal_id": registered["principal_id"],
                     "principal_generation": registered["principal_generation"],
                     "independence_group": registered["independence_group"]},
        "observer_provenance": deepcopy(registered["provenance"]),
        "observation_generation": control["state_generation"] + 1,
        "observed_at": observed_at,
        "outcome": outcome, "result_identity": deepcopy(result_identity),
        "observed_post_state": deepcopy(observed_post_state),
        "evidence_persisted": evidence_persisted, "receipt_digest": "0" * 64,
    }
    receipt["receipt_digest"] = _digest({k: v for k, v in receipt.items()
                                         if k != "receipt_digest"})
    if not EFFECT_RECEIPT_VALIDATOR.is_valid(receipt):
        raise BlueprintError("invalid_effect_receipt")
    updated = deepcopy(transaction)
    updated.update(
        state=state, receipt=receipt, observer=deepcopy(receipt["observer"]),
        observer_provenance=deepcopy(receipt["observer_provenance"]),
        observation_generation=receipt["observation_generation"],
        observed_at=receipt["observed_at"],
    )
    updated["transaction_digest"] = _digest({k: v for k, v in updated.items()
                                              if k != "transaction_digest"})
    txs = [updated if item["transaction_id"] == updated["transaction_id"] else item
           for item in control["transactions"]]
    return updated, _advance_v2(control, transactions=txs)


def finalize_effect_transaction(transaction, *, ticket_finalization_succeeded,
                                bridge_control_state, trusted_control_state_digest):
    """Finalize only persisted success evidence; otherwise require reconciliation."""
    control = _validate_v2_control(bridge_control_state, trusted_control_state_digest)
    stored = [item for item in control["transactions"]
              if item["transaction_id"] == transaction.get("transaction_id")]
    if len(stored) != 1 or stored[0] != transaction:
        raise BlueprintError("transaction_not_current")
    if transaction["state"] != "OBSERVED_SUCCEEDED":
        raise BlueprintError("transaction_not_finalizable")
    updated = deepcopy(transaction)
    if not ticket_finalization_succeeded:
        updated["state"] = "RECONCILIATION_REQUIRED"
    else:
        receipt = transaction["receipt"]
        result = {
            "record_type": "MUTATION_RESULT", "record_version": 2,
            "transaction_id": transaction["transaction_id"],
            "ticket_id": transaction["ticket_id"],
            "ticket_state_digest": transaction["ticket_state_digest"],
            "ticket_consumption_identity": transaction["ticket_consumption_identity"],
            "admission_record_digest": transaction["admission_record_digest"],
            "classification_digest": transaction["classification_digest"],
            "mutation_target": deepcopy(transaction["mutation_target"]),
            "write_set_digest": transaction["write_set_digest"],
            "staged_patch_digest": transaction["staged_patch_digest"],
            "actual_effect_digest": transaction["actual_effect_digest"],
            "effect_receipt_digest": receipt["receipt_digest"],
            "producer": deepcopy(transaction["producer"]),
            "observer": deepcopy(receipt["observer"]),
            "observer_provenance": deepcopy(receipt["observer_provenance"]),
            "observation_generation": receipt["observation_generation"],
            "observed_at": receipt["observed_at"],
            "result_identity": deepcopy(receipt["result_identity"]),
            "authority_state": "EXECUTED_PENDING_VERIFICATION",
        }
        result["result_record_digest"] = _digest(result)
        updated.update(state="FINALIZED", result=result)
    updated["transaction_digest"] = _digest({k: v for k, v in updated.items()
                                              if k != "transaction_digest"})
    txs = [updated if item["transaction_id"] == updated["transaction_id"] else item
           for item in control["transactions"]]
    return updated.get("result"), updated, _advance_v2(control, transactions=txs)


def _validate_v2_result(result):
    if not MUTATION_RESULT_V2_VALIDATOR.is_valid(result):
        raise BlueprintError("trusted_v2_mutation_result_required")
    unsigned = deepcopy(result)
    supplied = unsigned.pop("result_record_digest")
    if _digest(unsigned) != supplied:
        raise BlueprintError("invalid_mutation_result_digest")
    return result


def issue_verifier_claim(mutation_result, *, claim_id, verifier, task_id,
                         evidence_refs, test_run_id, verification_generation,
                         issued_at, expires_at, bridge_control_state,
                         trusted_control_state_digest):
    control = _validate_v2_control(bridge_control_state, trusted_control_state_digest)
    _validate_v2_result(mutation_result)
    registered = _v2_principal(control, verifier, "verifier")
    producer = mutation_result.get("producer", {})
    if registered["principal_id"] == producer.get("principal_id"):
        raise BlueprintError("producer_cannot_verify_own_result")
    if registered["independence_group"] == producer.get("independence_group"):
        raise BlueprintError("verifier_not_independent")
    observer = mutation_result["observer"]
    if (registered["principal_id"] == observer["principal_id"]
            or registered["independence_group"] == observer["independence_group"]):
        raise BlueprintError("verifier_not_independent_from_observer")
    if claim_id in control["issued_claim_ids"]:
        raise BlueprintError("duplicate_verifier_claim")
    if _time(expires_at) <= _time(issued_at):
        raise BlueprintError("invalid_claim_window")
    claim = {
        "record_type": "VERIFIER_CLAIM", "record_version": 2,
        "claim_id": claim_id, "mutation_result_digest": mutation_result["result_record_digest"],
        "task_id": task_id, "ticket_id": mutation_result["ticket_id"],
        "ticket_state_digest": mutation_result["ticket_state_digest"],
        "ticket_consumption_identity": mutation_result["ticket_consumption_identity"],
        "admission_record_digest": mutation_result["admission_record_digest"],
        "classification_digest": mutation_result["classification_digest"],
        "effect_receipt_digest": mutation_result["effect_receipt_digest"],
        "actual_effect_digest": mutation_result["actual_effect_digest"],
        "evidence_refs": list(_refs(evidence_refs, "verification_evidence_refs")),
        "test_run_id": test_run_id,
        "verification_generation": verification_generation,
        "result_identity": deepcopy(mutation_result["result_identity"]),
        "verifier": {"principal_id": registered["principal_id"],
                     "principal_generation": registered["principal_generation"],
                     "independence_group": registered["independence_group"]},
        "governance_generation": control["governance_generation"],
        "control_state_generation": control["state_generation"],
        "issued_at": issued_at, "expires_at": expires_at, "claim_digest": "0" * 64,
    }
    claim["claim_digest"] = _digest({k: v for k, v in claim.items() if k != "claim_digest"})
    if not VERIFIER_CLAIM_VALIDATOR.is_valid(claim):
        raise BlueprintError("invalid_verifier_claim")
    advanced = _advance_v2(
        control,
        issued_claim_ids=control["issued_claim_ids"] + [claim_id],
        verifier_claims=control["verifier_claims"] + [claim],
    )
    return claim, advanced


def record_verification_v2(mutation_result, claim, *, verdict, observed_result_identity,
                           verified_at, bridge_control_state,
                           trusted_control_state_digest):
    control = _validate_v2_control(bridge_control_state, trusted_control_state_digest)
    _validate_v2_result(mutation_result)
    if not VERIFIER_CLAIM_VALIDATOR.is_valid(claim):
        raise BlueprintError("trusted_verifier_claim_required")
    unsigned_claim = deepcopy(claim)
    supplied_claim_digest = unsigned_claim.pop("claim_digest")
    if (_digest(unsigned_claim) != supplied_claim_digest
            or claim["claim_id"] not in control["issued_claim_ids"]
            or claim not in control["verifier_claims"]):
        raise BlueprintError("trusted_verifier_claim_required")
    if claim["claim_id"] in control["consumed_claim_ids"]:
        raise BlueprintError("verification_claim_replay")
    if (claim["governance_generation"] != control["governance_generation"]
            or claim["control_state_generation"] >= control["state_generation"]
            or _time(verified_at) > _time(claim["expires_at"])):
        raise BlueprintError("stale_verifier_claim")
    result_bindings = {
        "mutation_result_digest": mutation_result["result_record_digest"],
        "ticket_id": mutation_result["ticket_id"],
        "ticket_state_digest": mutation_result["ticket_state_digest"],
        "ticket_consumption_identity": mutation_result["ticket_consumption_identity"],
        "admission_record_digest": mutation_result["admission_record_digest"],
        "classification_digest": mutation_result["classification_digest"],
        "effect_receipt_digest": mutation_result["effect_receipt_digest"],
        "actual_effect_digest": mutation_result["actual_effect_digest"],
    }
    if (any(claim[field] != value for field, value in result_bindings.items())
            or claim["result_identity"] != mutation_result.get("result_identity")
            or observed_result_identity != mutation_result.get("result_identity")):
        raise BlueprintError("verification_result_mismatch")
    if verdict not in {"PASS", "FAIL"}:
        raise BlueprintError("verification_record_required")
    record = {
        "record_type": "VERIFICATION_RECORD", "record_version": 2,
        "claim_digest": claim["claim_digest"], "claim_id": claim["claim_id"],
        "mutation_result_digest": mutation_result["result_record_digest"],
        "task_id": claim["task_id"], "ticket_id": claim["ticket_id"],
        "ticket_state_digest": claim["ticket_state_digest"],
        "ticket_consumption_identity": claim["ticket_consumption_identity"],
        "admission_record_digest": claim["admission_record_digest"],
        "classification_digest": claim["classification_digest"],
        "effect_receipt_digest": claim["effect_receipt_digest"],
        "actual_effect_digest": claim["actual_effect_digest"],
        "evidence_refs": deepcopy(claim["evidence_refs"]),
        "test_run_id": claim["test_run_id"],
        "verification_generation": claim["verification_generation"],
        "result_identity": deepcopy(observed_result_identity), "verdict": verdict,
        "verifier": deepcopy(claim["verifier"]), "verified_at": verified_at,
        "verification_digest": "0" * 64,
    }
    record["verification_digest"] = _digest({k: v for k, v in record.items()
                                             if k != "verification_digest"})
    if not VERIFICATION_RECORD_V2_VALIDATOR.is_valid(record):
        raise BlueprintError("invalid_verification_record")
    advanced = _advance_v2(
        control,
        consumed_claim_ids=control["consumed_claim_ids"] + [claim["claim_id"]],
        verification_records=control["verification_records"] + [record],
    )
    return record, advanced


def _validate_verification_v2(record):
    if not VERIFICATION_RECORD_V2_VALIDATOR.is_valid(record):
        raise BlueprintError("verification_record_required")
    unsigned = deepcopy(record)
    supplied = unsigned.pop("verification_digest")
    if _digest(unsigned) != supplied:
        raise BlueprintError("invalid_verification_record_digest")
    return record


def issue_progress_token_v2(mutation_result, verification_record, *, token_id, nonce,
                            task_id, destination_state, authority, gate_snapshot_digest,
                            issue_refs=(), trust_anchor_status="UNRESOLVED",
                            bridge_control_state, trusted_control_state_digest):
    control = _validate_v2_control(bridge_control_state, trusted_control_state_digest)
    _validate_v2_result(mutation_result)
    registered = _v2_principal(control, authority, "progression_authority")
    _validate_verification_v2(verification_record)
    if verification_record not in control["verification_records"]:
        raise BlueprintError("verification_record_not_current")
    if verification_record.get("verdict") != "PASS":
        raise BlueprintError("verification_record_required")
    full_chain = {
        "mutation_result_digest": mutation_result["result_record_digest"],
        "ticket_id": mutation_result["ticket_id"],
        "ticket_state_digest": mutation_result["ticket_state_digest"],
        "ticket_consumption_identity": mutation_result["ticket_consumption_identity"],
        "admission_record_digest": mutation_result["admission_record_digest"],
        "classification_digest": mutation_result["classification_digest"],
        "effect_receipt_digest": mutation_result["effect_receipt_digest"],
        "actual_effect_digest": mutation_result["actual_effect_digest"],
        "result_identity": mutation_result["result_identity"],
    }
    if any(verification_record.get(field) != value for field, value in full_chain.items()):
        raise BlueprintError("verification_result_mismatch")
    if (verification_record["claim_id"] not in control["consumed_claim_ids"]
            or mutation_result["ticket_consumption_identity"] not in
            control["consumed_ticket_identities"]):
        raise BlueprintError("chain_not_current_or_not_consumed")
    finalized = [item for item in control["transactions"]
                 if item["transaction_id"] == mutation_result["transaction_id"]
                 and item["state"] == "FINALIZED" and item["result"] == mutation_result]
    if len(finalized) != 1:
        raise BlueprintError("finalized_transaction_required")
    if "issue:23" in set(issue_refs):
        raise BlueprintError("issue_23_human_governance_gate")
    if destination_state in {"RELEASED", "MERGED", "DEPLOYED"} and trust_anchor_status != "AVAILABLE":
        raise BlueprintError("issue_31_trust_anchor_unresolved")
    if destination_state in {"MERGED", "DEPLOYED"}:
        raise BlueprintError("authorized_progress_is_not_merge_or_deploy")
    if token_id in control["issued_progress_ids"] or nonce in control["issued_progress_nonces"]:
        raise BlueprintError("duplicate_progress_identity")
    token = {
        "record_type": "PROGRESS_TOKEN", "record_version": 2,
        "token_id": token_id, "nonce": nonce, "task_id": task_id,
        "destination_state": destination_state,
        "mutation_result_digest": mutation_result["result_record_digest"],
        "transaction_id": mutation_result["transaction_id"],
        "ticket_id": mutation_result["ticket_id"],
        "ticket_state_digest": mutation_result["ticket_state_digest"],
        "ticket_consumption_identity": mutation_result["ticket_consumption_identity"],
        "admission_record_digest": mutation_result["admission_record_digest"],
        "classification_digest": mutation_result["classification_digest"],
        "mutation_target": deepcopy(mutation_result["mutation_target"]),
        "write_set_digest": mutation_result["write_set_digest"],
        "staged_patch_digest": mutation_result["staged_patch_digest"],
        "actual_effect_digest": mutation_result["actual_effect_digest"],
        "effect_receipt_digest": mutation_result["effect_receipt_digest"],
        "claim_id": verification_record["claim_id"],
        "claim_digest": verification_record["claim_digest"],
        "verification_generation": verification_record["verification_generation"],
        "test_run_id": verification_record["test_run_id"],
        "evidence_refs": deepcopy(verification_record["evidence_refs"]),
        "verification_digest": verification_record["verification_digest"],
        "result_identity": deepcopy(mutation_result["result_identity"]),
        "governance_generation": control["governance_generation"],
        "control_state_generation": control["state_generation"] + 1,
        "gate_snapshot_digest": gate_snapshot_digest,
        "authorized_by": {"principal_id": registered["principal_id"],
                          "principal_generation": registered["principal_generation"],
                          "independence_group": registered["independence_group"]},
        "token_digest": "0" * 64,
    }
    token["token_digest"] = _digest({k: v for k, v in token.items() if k != "token_digest"})
    if not PROGRESS_TOKEN_V2_VALIDATOR.is_valid(token):
        raise BlueprintError("invalid_progress_token")
    advanced = _advance_v2(control,
        issued_progress_ids=control["issued_progress_ids"] + [token_id],
        issued_progress_nonces=control["issued_progress_nonces"] + [nonce],
        progress_tokens=control["progress_tokens"] + [token])
    return token, advanced


def consume_progress_token_v2(token, *, task_id, destination_state,
                              current_governance_generation, current_gate_snapshot_digest,
                              bridge_control_state, trusted_control_state_digest):
    control = _validate_v2_control(bridge_control_state, trusted_control_state_digest)
    if not PROGRESS_TOKEN_V2_VALIDATOR.is_valid(token):
        raise BlueprintError("trusted_progress_token_required")
    unsigned = deepcopy(token)
    supplied = unsigned.pop("token_digest")
    if (_digest(unsigned) != supplied or token["token_id"] not in control["issued_progress_ids"]
            or token["nonce"] not in control["issued_progress_nonces"]
            or token not in control["progress_tokens"]):
        raise BlueprintError("trusted_progress_token_required")
    _v2_principal(control, token["authorized_by"], "progression_authority")
    identity = _digest({"token_id": token["token_id"], "nonce": token["nonce"],
                        "token_digest": token["token_digest"]})
    if identity in control["consumed_progress_identities"]:
        raise BlueprintError("progress_token_replay")
    if token["task_id"] != task_id:
        raise BlueprintError("progress_task_mismatch")
    if token["destination_state"] != destination_state:
        raise BlueprintError("progress_destination_mismatch")
    if (token["governance_generation"] != current_governance_generation
            or current_governance_generation != control["governance_generation"]
            or token["control_state_generation"] != control["state_generation"]
            or token["gate_snapshot_digest"] != current_gate_snapshot_digest):
        raise BlueprintError("stale_progress_governance")
    if (token["ticket_consumption_identity"] not in control["consumed_ticket_identities"]
            or token["claim_id"] not in control["consumed_claim_ids"]):
        raise BlueprintError("chain_not_current_or_not_consumed")
    finalized = [item for item in control["transactions"]
                 if item["transaction_id"] == token["transaction_id"]
                 and item["state"] == "FINALIZED"
                 and item["result"]["result_record_digest"] == token["mutation_result_digest"]
                 and item["result"]["effect_receipt_digest"] == token["effect_receipt_digest"]]
    if len(finalized) != 1:
        raise BlueprintError("finalized_transaction_required")
    advanced = _advance_v2(control,
        consumed_progress_identities=control["consumed_progress_identities"] + [identity])
    return BridgeDecision("AUTHORIZED_PROGRESS", "single_consumed_governance_transition_only"), advanced
