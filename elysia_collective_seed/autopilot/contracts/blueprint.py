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


def classify_authoritatively(effect, *, trusted_classifiers, worker_proposal=None):
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
    if not isinstance(trusted_classifiers, (list, tuple)):
        raise BlueprintError("invalid_classifier_registry")
    registry = {}
    for classifier in trusted_classifiers:
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
    issued_ticket_ids,
    issued_nonces,
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
    known_ticket_ids = set(_refs(issued_ticket_ids, "issued_ticket_ids", allow_empty=True))
    known_nonces = set(_refs(issued_nonces, "issued_nonces", allow_empty=True))
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
    return ticket


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
    trusted_consumed_ticket_identities,
):
    """Compare-and-swap proof: checked state must equal mutated state."""
    reject = lambda reason: (BridgeDecision("REJECTED_NOT_AUTHORIZED", reason),
                             frozenset(trusted_consumed_ticket_identities))
    if not TICKET_VALIDATOR.is_valid(ticket):
        return reject("invalid_ticket")
    unsigned = deepcopy(ticket)
    digest = unsigned.pop("state_digest")
    if _digest(unsigned) != digest:
        return reject("ticket_tampered")
    try:
        consumed_input = (sorted(trusted_consumed_ticket_identities)
                          if isinstance(trusted_consumed_ticket_identities,
                                        (set, frozenset))
                          else trusted_consumed_ticket_identities)
        consumed_identities = _refs(
            consumed_input,
            "trusted_consumed_ticket_identities",
            allow_empty=True,
        )
        if any(len(value) != 64 or any(char not in "0123456789abcdef"
                                       for char in value)
               for value in consumed_identities):
            return reject("invalid_consumption_registry")
        now = _time(current_time)
        if now < _time(ticket["issued_at"]) or now >= _time(ticket["expires_at"]):
            return reject("ticket_expired_or_not_yet_valid")
        actions = set(_refs(requested_actions, "requested_actions"))
    except BlueprintError as exc:
        return reject(str(exc))
    consumption_identity = ticket_consumption_identity(ticket)
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
    consumed = frozenset(
        set(consumed_identities) | {consumption_identity}
    )
    return (BridgeDecision(
        "CONSUMABLE_REFERENCE_TICKET_NOT_PRODUCTION_AUTHORITY",
        "atomic_boundary_must_consume_with_the_mutation",
    ), consumed)


def issue_trusted_task_record(
    worker_task,
    admission_record,
    *,
    owner,
    authoritative_task_owners,
    issued_task_ids,
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
    if admission_record["entity_id"] in set(
        _refs(issued_task_ids, "issued_task_ids", allow_empty=True)
    ):
        raise BlueprintError("duplicate_task_identity")
    if not isinstance(owner, dict):
        raise BlueprintError("invalid_task_owner")
    if not isinstance(authoritative_task_owners, (list, tuple)):
        raise BlueprintError("invalid_task_owner_registry")
    matches = [entry for entry in authoritative_task_owners
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
    return record


def attach_task_or_queue_record(
    worker_task,
    admission_record,
    *,
    trusted_task_record=None,
    trusted_task_record_digest=None,
    attached_task_ids=(),
):
    """Attach one independently pinned task identity; worker prose grants nothing."""
    if not isinstance(worker_task, dict):
        raise BlueprintError("invalid_worker_proposal")
    if not ADMISSION_RECORD_VALIDATOR.is_valid(admission_record):
        raise BlueprintError("trusted_admission_required")
    if (not TRUSTED_TASK_VALIDATOR.is_valid(trusted_task_record)
            or trusted_task_record_digest != _digest(trusted_task_record)):
        raise BlueprintError("trusted_task_record_required")
    if trusted_task_record["task_id"] in set(attached_task_ids):
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
    return {
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


def carry_execution_context(context, *, provider, session):
    """Provider/session changes preserve, and cannot replace, admitted identity."""
    required = {
        "admitted_entity_id", "admission_record_digest", "ticket_id", "nonce",
        "classification_digest", "write_set_digest", "objective_refs",
        "repository_lineage_refs", "governance_lineage_refs",
        "applicable_gate_generations", "admission_generation",
        "snapshot_generation", "snapshot_digest",
    }
    if not isinstance(context, dict) or not required.issubset(context):
        raise BlueprintError("missing_execution_admission_context")
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
    trusted_consumed_ticket_identities,
):
    """Create a fail-closed effect receipt after a single consumed attempt."""
    if not TICKET_VALIDATOR.is_valid(ticket):
        raise BlueprintError("invalid_ticket")
    unsigned_ticket = deepcopy(ticket)
    supplied_ticket_digest = unsigned_ticket.pop("state_digest")
    if _digest(unsigned_ticket) != supplied_ticket_digest:
        raise BlueprintError("invalid_ticket")
    consumption_identity = ticket_consumption_identity(ticket)
    consumed_input = (sorted(trusted_consumed_ticket_identities)
                      if isinstance(trusted_consumed_ticket_identities,
                                    (set, frozenset))
                      else trusted_consumed_ticket_identities)
    consumed_identities = _refs(
        consumed_input,
        "trusted_consumed_ticket_identities",
        allow_empty=True,
    )
    if consumption_identity not in set(consumed_identities):
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
    trusted_verifiers,
):
    """Bind technical verification to one immutable mutation result identity."""
    if not MUTATION_RESULT_VALIDATOR.is_valid(mutation_result):
        raise BlueprintError("invalid_mutation_result")
    unsigned_result = deepcopy(mutation_result)
    supplied_result_digest = unsigned_result.pop("result_record_digest")
    if _digest(unsigned_result) != supplied_result_digest:
        raise BlueprintError("invalid_mutation_result")
    _refs(verifier_provenance, "verifier_provenance")
    if not isinstance(trusted_verifiers, (list, tuple)):
        raise BlueprintError("invalid_verifier_registry")
    matches = [entry for entry in trusted_verifiers
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
    trusted_progression_authorities,
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
    if not isinstance(trusted_progression_authorities, (list, tuple)):
        raise BlueprintError("invalid_progression_authority_registry")
    matches = [entry for entry in trusted_progression_authorities
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
    trusted_progression_authorities,
):
    """Consume one authenticated progression decision for the exact full chain."""
    chain = _assess_provenance_chain(
        admission_record, ticket, mutation_result, verification,
        current_result_identity=current_result_identity,
    )
    if chain.disposition != "PROVENANCE_CHAIN_VALID_REFERENCE_ONLY":
        return chain
    blocked = lambda reason: BridgeDecision("BLOCKED_PROVENANCE_MISMATCH", reason)
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
    }
    if any(progression_authorization.get(field) != value
           for field, value in expected.items()):
        return blocked("progression_authorization_chain_mismatch")
    authority = progression_authorization["authorized_by"]
    provenance = progression_authorization["authority_provenance"]
    if not isinstance(trusted_progression_authorities, (list, tuple)):
        return blocked("invalid_progression_authority_registry")
    matches = [entry for entry in trusted_progression_authorities
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
    trusted_progression_authorities=(),
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
            trusted_progression_authorities=trusted_progression_authorities,
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
