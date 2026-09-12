"""Regression coverage for trusted-admission fail-closed boundaries.

These assertions state the fail-closed behavior promised by
GOVERNANCE_V2_ADMISSION.md. They live outside the candidate worktree.
"""
from copy import deepcopy

import pytest

from elysia_collective_seed.autopilot.contracts.admission import (
    AdmissionError,
    evaluate_admitted,
    migrate_v1_to_v2,
    validate_snapshot_version,
)
from elysia_collective_seed.autopilot.contracts.checkpoint_reference import snapshot_digest

AUTHORITY = {
    "authority_id": "migration-control-plane",
    "authority_kind": "trusted_migration_control_plane",
    "authority_generation": 4,
    "source_refs": ["vega:independent-registry"],
}
AUTHORITY_REF = {"authority_id": "migration-control-plane", "authority_generation": 4}
OLD_BLOCKS = ["claim", "repo_write", "semantic_write", "integration", "merge", "deploy", "external_write"]


def legacy_v1():
    return {
        "schema_version": 1,
        "revision": 7,
        "source_refs": ["vega:v1"],
        "gates": [{
            "gate_id": "gate:23",
            "generation": 3,
            "kind": "human_governance_required",
            "state": "active",
            "scope": {"objective_refs": ["issue:23"], "lineage_refs": ["governance:23"]},
            "inherit_to_children": True,
            "blocked_actions": OLD_BLOCKS[:],
            "reason": "human decision required",
            "source_refs": ["issue:29"],
            "release": None,
        }],
        "entities": [
            {
                "entity_id": "root",
                "parent_refs": [],
                "objective_refs": ["issue:23"],
                "lineage_refs": ["branch:restack"],
                "governance_gate_refs": ["gate:23"],
            },
            {
                "entity_id": "child",
                "parent_refs": ["root"],
                "objective_refs": ["task:renamed"],
                "lineage_refs": ["commit:child"],
                "governance_gate_refs": [],
            },
        ],
    }


def admission(entity, ancestry_kind, entity_kind):
    result = {
        "entity_id": entity["entity_id"],
        "entity_kind": entity_kind,
        "ancestry_kind": ancestry_kind,
        "parent_refs": deepcopy(entity["parent_refs"]),
        "repository_lineage_refs": deepcopy(entity["lineage_refs"]),
        "governance_lineage_refs": ["governance:23"],
        "objective_refs": deepcopy(entity["objective_refs"]),
        "action_classes": ["semantic_code_write"],
        "admission_generation": 8,
        "admitted_by": deepcopy(AUTHORITY_REF),
        "admission_source": ["vega:manifest"],
        "admission_evidence": ["vega:repository-proof"],
        "admitted_at": "2026-09-12T00:00:00Z",
        "governance_gate_refs": deepcopy(entity["governance_gate_refs"]),
    }
    if ancestry_kind == "root":
        result["root_admission_evidence"] = ["vega:explicit-root-proof"]
    return result


def manifest(source):
    return {
        "from_schema_version": 1,
        "to_schema_version": 2,
        "target_snapshot_generation": 8,
        "migration_authority": deepcopy(AUTHORITY_REF),
        "migrated_at": "2026-09-12T00:00:00Z",
        "evidence_refs": ["vega:migration-review"],
        "admissions": [
            admission(source["entities"][0], "root", "objective"),
            admission(source["entities"][1], "derived", "commit"),
        ],
    }


def migrate(source, plan=None, authorities=None):
    return migrate_v1_to_v2(
        source,
        plan if plan is not None else manifest(source),
        trusted_source_digest=snapshot_digest(source),
        trusted_authorities=authorities if authorities is not None else [AUTHORITY],
    )


def test_control_semantic_restack_remains_blocked_and_worker_labels_are_ignored():
    source = legacy_v1()
    target = migrate(source)
    result = evaluate_admitted(
        target,
        "child",
        "semantic_code_write",
        trusted_current_digest=snapshot_digest(target),
        worker_proposal={
            "ancestry_kind": "root",
            "objective_refs": ["friendly:unrelated"],
            "action": "docs_only",
        },
    )
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.effective_active_gates == (("gate:23", 3),)
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_control_wrong_digest_and_unknown_authority_block():
    source = legacy_v1()
    target = migrate(source)
    assert evaluate_admitted(
        target, "root", "semantic_code_write", trusted_current_digest="0" * 64
    ).disposition == "BLOCKED_INVALID_STATE"
    target["admissions"][0]["admitted_by"] = {
        "authority_id": "worker", "authority_generation": 1
    }
    assert evaluate_admitted(
        target, "root", "semantic_code_write", trusted_current_digest=snapshot_digest(target)
    ).disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("version", [True, 1.0])
def test_migration_rejects_non_integer_exact_v1_version(version):
    source = legacy_v1()
    source["schema_version"] = version
    with pytest.raises(AdmissionError, match="source_must_be_v1"):
        migrate(source)


@pytest.mark.parametrize("version", [2.0])
def test_v2_validator_rejects_non_integer_runtime_version(version):
    source = legacy_v1()
    target = migrate(source)
    target["schema_version"] = version
    with pytest.raises(AdmissionError, match="unsupported_schema_version"):
        validate_snapshot_version(target)


def test_migration_wraps_malformed_legacy_gate_as_admission_error():
    source = legacy_v1()
    del source["gates"][0]["blocked_actions"]
    with pytest.raises(AdmissionError):
        migrate(source)


def test_migration_rejects_missing_parent_before_returning_snapshot():
    source = legacy_v1()
    source["entities"][1]["parent_refs"] = ["absent-parent"]
    target_manifest = manifest(source)
    with pytest.raises(AdmissionError, match="parent|ancestry|invalid",):
        migrate(source, target_manifest)


def test_migration_rejects_duplicate_gate_identity_before_returning_snapshot():
    source = legacy_v1()
    source["gates"].append(deepcopy(source["gates"][0]))
    with pytest.raises(AdmissionError, match="duplicate|invalid"):
        migrate(source)


def test_migration_rejects_duplicate_trusted_authority_identity():
    source = legacy_v1()
    duplicate = deepcopy(AUTHORITY)
    duplicate["source_refs"] = ["vega:conflicting-registry-entry"]
    with pytest.raises(AdmissionError, match="duplicate|authority"):
        migrate(source, authorities=[AUTHORITY, duplicate])


def test_migration_rejects_admission_bound_to_unregistered_authority():
    source = legacy_v1()
    target_manifest = manifest(source)
    target_manifest["admissions"][1]["admitted_by"] = {
        "authority_id": "worker", "authority_generation": 1
    }
    with pytest.raises(AdmissionError, match="authority|invalid"):
        migrate(source, target_manifest)


def test_declared_datetime_format_is_enforced_by_reference_validator():
    source = legacy_v1()
    target = migrate(source)
    target["admissions"][0]["admitted_at"] = "not-a-date-time"
    with pytest.raises(AdmissionError, match="invalid_v2_snapshot"):
        validate_snapshot_version(target)

@pytest.mark.parametrize("version", [None, False, 0, 1, 3, 999, "2"])
def test_control_unknown_downgrade_forward_v2_versions_block(version):
    source = legacy_v1()
    target = migrate(source)
    target["schema_version"] = version
    with pytest.raises(AdmissionError):
        validate_snapshot_version(target)


def test_control_generation_rollback_and_stale_source_digest_block():
    source = legacy_v1()
    target = migrate(source)
    with pytest.raises(AdmissionError, match="snapshot_generation_rollback"):
        validate_snapshot_version(target, minimum_generation=9)
    with pytest.raises(AdmissionError, match="stale_or_untrusted_source_digest"):
        migrate_v1_to_v2(
            source,
            manifest(source),
            trusted_source_digest="0" * 64,
            trusted_authorities=[AUTHORITY],
        )


def test_control_missing_root_evidence_blocks():
    source = legacy_v1()
    target_manifest = manifest(source)
    target_manifest["admissions"][0].pop("root_admission_evidence")
    with pytest.raises(AdmissionError, match="root_requires_explicit_migration_evidence"):
        migrate(source, target_manifest)


@pytest.mark.parametrize(
    ("entity_index", "field", "replacement"),
    [
        (0, "objective_refs", ["friendly:replacement"]),
        (1, "parent_refs", ["friendly:replacement"]),
        (0, "governance_gate_refs", []),
        (1, "repository_lineage_refs", ["branch:friendly"]),
        (1, "governance_lineage_refs", []),
    ],
)
def test_control_migration_cannot_drop_or_rewrite_scope(entity_index, field, replacement):
    source = legacy_v1()
    target_manifest = manifest(source)
    target_manifest["admissions"][entity_index][field] = replacement
    with pytest.raises(AdmissionError):
        migrate(source, target_manifest)


def test_control_released_assertion_remains_blocked_and_unvalidated():
    source = legacy_v1()
    gate = source["gates"][0]
    gate["state"] = "released"
    gate["release"] = {
        "gate_id": gate["gate_id"],
        "generation": gate["generation"],
        "scope": deepcopy(gate["scope"]),
        "actions": OLD_BLOCKS[:],
        "asserted_human": "owner",
        "transport": "app",
        "application": "connector",
        "evidence_refs": ["vega:unverified-release"],
    }
    target = migrate(source)
    result = evaluate_admitted(
        target, "child", "semantic_code_write", trusted_current_digest=snapshot_digest(target)
    )
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_control_unrelated_no_match_never_reports_authorization():
    source = legacy_v1()
    source["entities"] = [source["entities"][0]]
    source["entities"][0]["objective_refs"] = ["issue:999"]
    source["entities"][0]["lineage_refs"] = ["branch:unrelated"]
    source["entities"][0]["governance_gate_refs"] = []
    target_manifest = manifest(legacy_v1())
    root_decision = admission(source["entities"][0], "root", "task")
    root_decision["action_classes"] = ["static_read"]
    target_manifest["admissions"] = [root_decision]
    target = migrate(source, target_manifest)
    result = evaluate_admitted(
        target, "root", "static_read", trusted_current_digest=snapshot_digest(target)
    )
    assert result.disposition == "NO_MATCHING_BLOCK_NOT_AUTHORIZATION"
    assert result.external_write_enforcement == "NOT_ENFORCED"


def test_control_repository_and_governance_lineage_each_preserve_gate_match():
    source = legacy_v1()
    for matching_ref, repository_refs, governance_ref in [
        ("commit:child", ["commit:child"], "governance:unrelated"),
        ("governance:semantic-restack", ["commit:child", "commit:unrelated"], "governance:semantic-restack"),
    ]:
        case = deepcopy(source)
        case["gates"][0]["scope"]["objective_refs"] = ["issue:unrelated"]
        case["gates"][0]["scope"]["lineage_refs"] = [matching_ref]
        target_manifest = manifest(case)
        target_manifest["admissions"][1]["repository_lineage_refs"] = repository_refs
        target_manifest["admissions"][1]["governance_lineage_refs"] = [governance_ref]
        target = migrate(case, target_manifest)
        result = evaluate_admitted(
            target, "child", "semantic_code_write", trusted_current_digest=snapshot_digest(target)
        )
        assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"


def test_migration_wraps_noniterable_authority_config_as_admission_error():
    source = legacy_v1()
    with pytest.raises(AdmissionError):
        migrate_v1_to_v2(
            source,
            manifest(source),
            trusted_source_digest=snapshot_digest(source),
            trusted_authorities=None,
        )




@pytest.mark.parametrize("timestamp", ["2026-09-12T00:00:00+01:60", "2026-02-30T00:00:00Z"])
def test_invalid_rfc3339_timestamp_is_rejected(timestamp):
    source = legacy_v1()
    target = migrate(source)
    target["admissions"][0]["admitted_at"] = timestamp
    with pytest.raises(AdmissionError, match="invalid_v2_snapshot"):
        validate_snapshot_version(target)


def test_rfc3339_leap_second_is_accepted():
    source = legacy_v1()
    target = migrate(source)
    target["admissions"][0]["admitted_at"] = "2026-12-31T23:59:60Z"
    validate_snapshot_version(target)


@pytest.mark.parametrize("bad", [None, "one", 1.5, True, [], {}])
def test_malformed_minimum_generation_fails_closed(bad):
    source = legacy_v1()
    with pytest.raises(AdmissionError):
        migrate_v1_to_v2(
            source, manifest(source), trusted_source_digest=snapshot_digest(source),
            trusted_authorities=[AUTHORITY], minimum_target_generation=bad,
        )
