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
        "classifier_id", "classifier_generation", "classifier_provenance",
        "objective_refs", "content_facts", "source_paths", "target_surface",
        "ambiguous_action", "ambiguous_objective", "evidence_refs",
    }:
        raise BlueprintError("invalid_trusted_effect")
    if not isinstance(trusted_classifiers, (list, tuple)):
        raise BlueprintError("invalid_classifier_registry")
    registry = {}
    for classifier in trusted_classifiers:
        if (not isinstance(classifier, Mapping)
                or set(classifier) != {"classifier_id", "classifier_generation", "provenance"}
                or type(classifier["classifier_id"]) is not str
                or type(classifier["classifier_generation"]) is not int
                or classifier["classifier_generation"] < 1):
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
    if effect["ambiguous_action"] is not False or effect["ambiguous_objective"] is not False:
        raise BlueprintError("ambiguous_classification")
    objectives = _refs(effect["objective_refs"], "objective_refs")
    facts = _refs(effect["content_facts"], "content_facts")
    _refs(effect["source_paths"], "source_paths")
    evidence = _refs(effect["evidence_refs"], "classification_evidence")
    if effect["target_surface"] not in COMPOSED_MEDIATED_BOUNDARIES | {"repository_side"}:
        raise BlueprintError("unknown_target_surface")
    if any(fact not in CONTENT_FACT_ACTIONS for fact in facts):
        raise BlueprintError("ambiguous_classification")
    actions = tuple(sorted({CONTENT_FACT_ACTIONS[fact] for fact in facts}))
    result = {
        "classification_status": "AUTHORITATIVE_REFERENCE_CLASSIFICATION",
        "classifier_id": effect["classifier_id"],
        "classifier_generation": effect["classifier_generation"],
        "objective_refs": list(objectives),
        "action_classes": list(actions),
        "target_surface": effect["target_surface"],
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
    if set(classification.get("objective_refs", ())) != objectives:
        raise BlueprintError("objective_attachment_mismatch")
    actions = set(classification.get("action_classes", ()))
    if not actions or not actions.issubset(set(node["action_classes"])):
        raise BlueprintError("action_not_admitted")
    if (not isinstance(trusted_mutation_target, dict)
            or trusted_mutation_target.get("surface") != classification.get("target_surface")):
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
        "record_version": 1,
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
        },
        "classification_digest": trusted_classification_digest,
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
        "record_version": 1,
        "ticket_id": ticket_id,
        "nonce": nonce,
        "admitted_entity_id": admission_record["entity_id"],
        "admission_record_digest": trusted_admission_record_digest,
        "objective_refs": deepcopy(admission_record["objective_refs"]),
        "repository_lineage_refs": deepcopy(admission_record["repository_lineage_refs"]),
        "governance_lineage_refs": deepcopy(admission_record["governance_lineage_refs"]),
        "action_classes": deepcopy(admission_record["action_classes"]),
        "mutation_target": deepcopy(admission_record["mutation_target"]),
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
    consumed_nonces=(),
):
    """Compare-and-swap proof: checked state must equal mutated state."""
    reject = lambda reason: (BridgeDecision("REJECTED_NOT_AUTHORIZED", reason),
                             frozenset(consumed_nonces))
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
    if ticket["nonce"] in set(consumed_nonces):
        return reject("ticket_replay")
    if not actions.issubset(set(ticket["action_classes"])):
        return reject("ticket_scope_exceeded")
    expected = ticket_current_state(ticket)
    if not isinstance(current_state, dict) or set(current_state) != set(expected):
        return reject("invalid_current_state")
    comparisons = (
        ("admission_record_digest", "admission_record_changed"),
        ("objective_refs", "objective_changed"),
        ("repository_lineage_refs", "ancestry_changed"),
        ("governance_lineage_refs", "governance_lineage_changed"),
        ("mutation_target", "mutation_target_or_head_changed"),
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
    consumed = frozenset(set(consumed_nonces) | {ticket["nonce"]})
    return (BridgeDecision(
        "CONSUMABLE_REFERENCE_TICKET_NOT_PRODUCTION_AUTHORITY",
        "atomic_boundary_must_consume_with_the_mutation",
    ), consumed)


def attach_task_or_queue_record(worker_task, admission_record):
    """Attach trusted identity; queue/task IDs and worker prose grant nothing."""
    if not isinstance(worker_task, dict):
        raise BlueprintError("invalid_worker_proposal")
    if not ADMISSION_RECORD_VALIDATOR.is_valid(admission_record):
        raise BlueprintError("trusted_admission_required")
    return {
        "attachment_status": "ADMITTED_REFERENCE_ONLY",
        "worker_proposal": deepcopy(worker_task),
        "trusted_admission_record": deepcopy(admission_record),
    }


def restore_task_or_queue_attachment(persisted):
    """Restart never reconstructs authority from worker text."""
    if (not isinstance(persisted, dict)
            or not ADMISSION_RECORD_VALIDATOR.is_valid(
                persisted.get("trusted_admission_record"))):
        return BridgeDecision(
            "QUARANTINED_MISSING_TRUSTED_LINEAGE",
            "restart_requires_persisted_trusted_admission",
        )
    return BridgeDecision("ADMITTED_REFERENCE_ONLY", "ticket_still_required")


def carry_execution_context(context, *, provider, session):
    """Provider/session changes preserve, and cannot replace, admitted identity."""
    required = {
        "admitted_entity_id", "objective_refs", "governance_lineage_refs",
        "applicable_gate_generations", "admission_generation",
        "snapshot_generation", "snapshot_digest",
    }
    if not isinstance(context, dict) or not required.issubset(context):
        raise BlueprintError("missing_execution_admission_context")
    result = deepcopy(context)
    result["provider"] = provider
    result["session"] = session
    return result


def progress_transition(
    current_state,
    event,
    *,
    ticket_consumed=False,
    trusted_progression_decision=False,
):
    """Keep technical verification separate from governance progression."""
    if current_state not in PROGRESS_STATES:
        raise BlueprintError("unknown_progress_state")
    if event == "preserve" and current_state == "OBSERVED_UNTRUSTED":
        return "PRESERVED_EVIDENCE"
    if event == "admit" and current_state in {"OBSERVED_UNTRUSTED", "PRESERVED_EVIDENCE"}:
        if not trusted_progression_decision:
            raise BlueprintError("trusted_admission_required")
        return "ADMITTED"
    if event == "authorize_execute" and current_state == "ADMITTED":
        if not ticket_consumed:
            raise BlueprintError("consumed_ticket_required")
        return "AUTHORIZED_TO_EXECUTE"
    if event == "execute" and current_state == "AUTHORIZED_TO_EXECUTE":
        return "EXECUTED_PENDING_VERIFICATION"
    if event == "verify_pass" and current_state in {
        "OBSERVED_UNTRUSTED", "PRESERVED_EVIDENCE", "EXECUTED_PENDING_VERIFICATION"
    }:
        return "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION"
    if event == "authorize_progress" and current_state == "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION":
        if not (ticket_consumed and trusted_progression_decision):
            raise BlueprintError("verification_is_not_authorization")
        return "AUTHORIZED_PROGRESS"
    raise BlueprintError("invalid_progress_transition")


def classify_unmediated_output(*, verification_pass=False):
    """Raw external output can exist and be preserved, but remains ungoverned."""
    return {
        "state": ("VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION"
                  if verification_pass else "PRESERVED_EVIDENCE"),
        "external_write_enforcement": "NOT_ENFORCED",
        "authorized_progress": False,
    }
