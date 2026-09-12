"""Normative v2 admission and migration model; no production trust service."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Mapping

from jsonschema import Draft202012Validator

from .checkpoint_reference import SCHEMA, VALIDATOR, Decision, evaluate, snapshot_digest


class AdmissionError(ValueError):
    """A migration or admission input cannot be trusted by this model."""


ACTION_MIGRATION = {
    "claim": "repo_write", "semantic_write": "semantic_code_write",
    "read": "static_read", "static_analysis": "static_read",
    "specification": "schema_spec_write", "test_design": "test_only",
}
MANDATORY_GATED_ACTIONS = (
    "semantic_code_write", "repo_write", "integration", "merge", "deploy",
    "external_write", "permission_change", "private_data_access",
)
V1_SCHEMA = json.loads(Path(__file__).with_name("checkpoint_snapshot.v1.schema.json").read_text(encoding="utf-8"))
V1_VALIDATOR = Draft202012Validator(V1_SCHEMA)
AUTHORITY_VALIDATOR = Draft202012Validator({
    "$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": "#/$defs/authority",
})


def _digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_snapshot_version(snapshot, *, minimum_generation=None) -> None:
    """Reject unsupported versions and generation rollback before evaluation."""
    if (not isinstance(snapshot, dict)
            or type(snapshot.get("schema_version")) is not int
            or snapshot.get("schema_version") != 2):
        raise AdmissionError("unsupported_schema_version")
    if minimum_generation is not None and (
        type(minimum_generation) is not int
        or snapshot.get("snapshot_generation", 0) < minimum_generation
    ):
        raise AdmissionError("snapshot_generation_rollback")
    if not VALIDATOR.is_valid(snapshot):
        raise AdmissionError("invalid_v2_snapshot")


def evaluate_admitted(snapshot, entity_id, authoritative_action, *,
                       trusted_current_digest, worker_proposal=None,
                       minimum_generation=None) -> Decision:
    """Evaluate trusted admission; descriptive worker metadata grants nothing."""
    try:
        validate_snapshot_version(snapshot, minimum_generation=minimum_generation)
    except AdmissionError as exc:
        return Decision("BLOCKED_INVALID_STATE", reason=str(exc))
    # worker_proposal is retained solely to make the trust separation explicit.
    # Production must derive entity/action from trusted repository/control-plane
    # evidence and pass those values as the authoritative parameters.
    del worker_proposal
    return evaluate(
        snapshot, {"entity_id": entity_id, "action": authoritative_action},
        trusted_current_digest=trusted_current_digest,
    )


def migrate_v1_to_v2(legacy, manifest, *, trusted_source_digest,
                     trusted_authorities, minimum_target_generation=1):
    """Fail-closed public boundary for deterministic v1-to-v2 migration."""
    try:
        return _migrate_v1_to_v2(
            legacy, manifest,
            trusted_source_digest=trusted_source_digest,
            trusted_authorities=trusted_authorities,
            minimum_target_generation=minimum_target_generation,
        )
    except AdmissionError:
        raise
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise AdmissionError("malformed_migration_input") from exc


def _migrate_v1_to_v2(legacy, manifest, *, trusted_source_digest,
                      trusted_authorities, minimum_target_generation=1):
    """Deterministically migrate only with explicit classification evidence.

    This models what a trusted migration service must prove. Passing a mapping to
    this function is not authentication; callers must supply independently trusted
    authority configuration and the current source digest.
    """
    if (not isinstance(legacy, dict)
            or type(legacy.get("schema_version")) is not int
            or legacy.get("schema_version") != 1):
        raise AdmissionError("source_must_be_v1")
    if snapshot_digest(legacy) != trusted_source_digest:
        raise AdmissionError("stale_or_untrusted_source_digest")
    required_legacy = {"schema_version", "revision", "source_refs", "gates", "entities"}
    if set(legacy) != required_legacy or type(legacy["revision"]) is not int or legacy["revision"] < 1:
        raise AdmissionError("invalid_v1_snapshot")
    if not V1_VALIDATOR.is_valid(legacy):
        raise AdmissionError("invalid_v1_snapshot")
    if (not isinstance(manifest, dict)
            or type(manifest.get("from_schema_version")) is not int
            or type(manifest.get("to_schema_version")) is not int
            or manifest.get("from_schema_version") != 1
            or manifest.get("to_schema_version") != 2):
        raise AdmissionError("explicit_v1_to_v2_manifest_required")
    generation = manifest.get("target_snapshot_generation")
    if type(generation) is not int or generation <= max(legacy["revision"], minimum_target_generation - 1):
        raise AdmissionError("target_generation_not_monotonic")

    authority_ref = manifest.get("migration_authority")
    if not isinstance(authority_ref, dict):
        raise AdmissionError("missing_migration_authority")
    if (not isinstance(trusted_authorities, (list, tuple))
            or any(not isinstance(a, Mapping) for a in trusted_authorities)):
        raise AdmissionError("invalid_trusted_authority_registry")
    if any(not AUTHORITY_VALIDATOR.is_valid(dict(a)) for a in trusted_authorities):
        raise AdmissionError("invalid_trusted_authority_registry")
    trusted = {(a.get("authority_id"), a.get("authority_generation")): a
               for a in trusted_authorities}
    if len(trusted) != len(trusted_authorities):
        raise AdmissionError("duplicate_trusted_authority")
    key = (authority_ref.get("authority_id"), authority_ref.get("authority_generation"))
    authority = trusted.get(key)
    if not authority or authority.get("authority_kind") != "trusted_migration_control_plane":
        raise AdmissionError("unknown_migration_authority")

    legacy_entities = legacy["entities"]
    if not isinstance(legacy_entities, list) or any(not isinstance(e, dict) for e in legacy_entities):
        raise AdmissionError("invalid_v1_entities")
    old = {e.get("entity_id"): e for e in legacy_entities}
    decisions = manifest.get("admissions")
    if not isinstance(decisions, list) or any(not isinstance(e, dict) for e in decisions):
        raise AdmissionError("missing_admission_decisions")
    new = {e.get("entity_id"): e for e in decisions}
    if len(old) != len(legacy_entities) or len(new) != len(decisions) or set(old) != set(new):
        raise AdmissionError("migration_must_classify_every_entity_exactly_once")

    admissions = []
    for entity_id, source in old.items():
        decision = deepcopy(new[entity_id])
        root_evidence = decision.pop("root_admission_evidence", None)
        if decision.get("parent_refs") != source.get("parent_refs"):
            raise AdmissionError("migration_cannot_rewrite_ancestry")
        if decision.get("objective_refs") != source.get("objective_refs"):
            raise AdmissionError("migration_cannot_rewrite_objectives")
        if not set(source.get("lineage_refs", [])).issubset(decision.get("repository_lineage_refs", [])):
            raise AdmissionError("migration_cannot_drop_repository_lineage")
        if decision.get("governance_gate_refs") != source.get("governance_gate_refs"):
            raise AdmissionError("migration_cannot_drop_gate_refs")
        if decision.get("ancestry_kind") == "root":
            if (source.get("parent_refs") or not isinstance(root_evidence, list)
                    or not root_evidence
                    or any(type(ref) is not str or not ref.strip()
                           or ref != ref.strip() for ref in root_evidence)
                    or len(set(root_evidence)) != len(root_evidence)):
                raise AdmissionError("root_requires_explicit_migration_evidence")
        elif decision.get("ancestry_kind") == "derived":
            if not source.get("parent_refs"):
                raise AdmissionError("empty_parents_are_ambiguous_not_derived")
        else:
            raise AdmissionError("ancestry_classification_required")
        admissions.append(decision)

    try:
        gates = deepcopy(legacy["gates"])
        for gate in gates:
            mapped = [ACTION_MIGRATION.get(a, a) for a in gate["blocked_actions"]]
            gate["blocked_actions"] = list(dict.fromkeys(mapped + list(MANDATORY_GATED_ACTIONS)))
            if gate.get("release"):
                gate["release"]["actions"] = list(dict.fromkeys(ACTION_MIGRATION.get(a, a) for a in gate["release"]["actions"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AdmissionError("invalid_v1_snapshot") from exc

    migrated_at = manifest.get("migrated_at")
    evidence = manifest.get("evidence_refs")
    if not isinstance(migrated_at, str) or not isinstance(evidence, list) or not evidence:
        raise AdmissionError("migration_provenance_required")
    target = {
        "schema_version": 2,
        "snapshot_generation": generation,
        "source_refs": deepcopy(legacy["source_refs"]),
        "admission_authorities": [deepcopy(authority)],
        "gates": gates,
        "admissions": admissions,
        "migration_provenance": {
            "from_schema_version": 1,
            "source_snapshot_digest": trusted_source_digest,
            "migration_manifest_digest": _digest(manifest),
            "migrated_by": deepcopy(authority_ref),
            "migrated_at": migrated_at,
            "evidence_refs": deepcopy(evidence),
        },
    }
    validate_snapshot_version(target, minimum_generation=minimum_target_generation)
    probe = target["admissions"][0]
    semantic = evaluate(
        target,
        {"entity_id": probe["entity_id"], "action": probe["action_classes"][0]},
        trusted_current_digest=snapshot_digest(target),
    )
    if semantic.disposition == "BLOCKED_INVALID_STATE":
        raise AdmissionError(f"invalid_v2_semantics:{semantic.reason}")
    return target
