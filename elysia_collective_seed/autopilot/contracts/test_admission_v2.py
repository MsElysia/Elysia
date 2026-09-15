"""V2 admission/migration falsification; no production service or trust anchor."""
from copy import deepcopy

import pytest

from .admission import AdmissionError, evaluate_admitted, migrate_v1_to_v2, validate_snapshot_version
from .checkpoint_reference import VALIDATOR, snapshot_digest


AUTHORITY = {
    "authority_id": "migration-control-plane",
    "authority_kind": "trusted_migration_control_plane",
    "authority_generation": 4,
    "source_refs": ["fixture:authority-registry"],
}
AUTHORITY_REF = {"authority_id": "migration-control-plane", "authority_generation": 4}
OLD_BLOCKS = ["claim", "repo_write", "semantic_write", "integration", "merge", "deploy", "external_write"]


def legacy_v1():
    return {
        "schema_version": 1, "revision": 7, "source_refs": ["fixture:v1"],
        "gates": [{
            "gate_id": "gate:23", "generation": 3,
            "kind": "human_governance_required", "state": "active",
            "scope": {"objective_refs": ["issue:23"], "lineage_refs": ["governance:23"]},
            "inherit_to_children": True, "blocked_actions": OLD_BLOCKS[:],
            "reason": "human decision required", "source_refs": ["issue:29"], "release": None,
        }],
        "entities": [
            {"entity_id": "root", "parent_refs": [], "objective_refs": ["issue:23"],
             "lineage_refs": ["branch:restack"], "governance_gate_refs": ["gate:23"]},
            {"entity_id": "child", "parent_refs": ["root"], "objective_refs": ["task:renamed"],
             "lineage_refs": ["commit:child"], "governance_gate_refs": []},
        ],
    }


def decision(source, *, kind, entity_kind, action="semantic_code_write", root_evidence=None):
    result = {
        "entity_id": source["entity_id"], "entity_kind": entity_kind,
        "ancestry_kind": kind, "parent_refs": deepcopy(source["parent_refs"]),
        "repository_lineage_refs": deepcopy(source["lineage_refs"]),
        "governance_lineage_refs": ["governance:23"],
        "objective_refs": deepcopy(source["objective_refs"]), "action_classes": [action],
        "admission_generation": 8, "admitted_by": deepcopy(AUTHORITY_REF),
        "admission_source": ["fixture:migration-manifest"],
        "admission_evidence": ["fixture:repository-proof"],
        "admitted_at": "2026-09-12T00:00:00Z",
        "governance_gate_refs": deepcopy(source["governance_gate_refs"]),
    }
    if root_evidence is not None:
        result["root_admission_evidence"] = root_evidence
    return result


def manifest(source=None):
    source = source or legacy_v1()
    return {
        "from_schema_version": 1, "to_schema_version": 2,
        "target_snapshot_generation": 8,
        "migration_authority": deepcopy(AUTHORITY_REF),
        "migrated_at": "2026-09-12T00:00:00Z", "evidence_refs": ["fixture:migration-review"],
        "admissions": [
            decision(source["entities"][0], kind="root", entity_kind="objective",
                     root_evidence=["fixture:explicit-root-admission"]),
            decision(source["entities"][1], kind="derived", entity_kind="commit"),
        ],
    }


def migrate(source=None, plan=None, **kwargs):
    source = source or legacy_v1()
    return migrate_v1_to_v2(
        source, plan or manifest(source), trusted_source_digest=snapshot_digest(source),
        trusted_authorities=[AUTHORITY], **kwargs,
    )


def test_v1_is_rejected_by_v2_and_requires_explicit_migration():
    source = legacy_v1()
    assert not VALIDATOR.is_valid(source)
    with pytest.raises(AdmissionError, match="unsupported_schema_version"):
        validate_snapshot_version(source)
    target = migrate(source)
    assert target["schema_version"] == 2
    assert target["migration_provenance"]["source_snapshot_digest"] == snapshot_digest(source)


def test_migration_is_deterministic_and_preserves_gate_scope_and_release_denial():
    source = legacy_v1()
    first = migrate(source)
    second = migrate(deepcopy(source), deepcopy(manifest(source)))
    assert first == second
    assert first["gates"][0]["gate_id"] == "gate:23"
    assert first["gates"][0]["generation"] == 3
    assert first["gates"][0]["scope"] == source["gates"][0]["scope"]
    result = evaluate_admitted(first, "child", "semantic_code_write",
        trusted_current_digest=snapshot_digest(first))
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.release_validation == "UNAVAILABLE"


@pytest.mark.parametrize("version", [0, 1, 3, 999, "2", None])
def test_unknown_downgrade_and_forward_versions_fail_closed(version):
    target = migrate()
    target["schema_version"] = version
    with pytest.raises(AdmissionError, match="unsupported_schema_version"):
        validate_snapshot_version(target)


def test_generation_rollback_and_stale_digest_fail():
    source = legacy_v1()
    plan = manifest(source)
    plan["target_snapshot_generation"] = source["revision"]
    with pytest.raises(AdmissionError, match="target_generation_not_monotonic"):
        migrate(source, plan)
    target = migrate(source)
    with pytest.raises(AdmissionError, match="snapshot_generation_rollback"):
        validate_snapshot_version(target, minimum_generation=9)
    with pytest.raises(AdmissionError, match="stale_or_untrusted_source_digest"):
        migrate_v1_to_v2(source, manifest(source), trusted_source_digest="0" * 64,
                         trusted_authorities=[AUTHORITY])


def test_empty_parents_do_not_automatically_mean_root():
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][0].pop("root_admission_evidence")
    with pytest.raises(AdmissionError, match="root_requires_explicit_migration_evidence"):
        migrate(source, plan)
    plan = manifest(source)
    plan["admissions"][0]["ancestry_kind"] = "derived"
    with pytest.raises(AdmissionError, match="empty_parents_are_ambiguous"):
        migrate(source, plan)


def test_worker_authority_and_unknown_authority_fail():
    source = legacy_v1()
    plan = manifest(source)
    plan["migration_authority"] = {"authority_id": "worker", "authority_generation": 1}
    with pytest.raises(AdmissionError, match="unknown_migration_authority"):
        migrate(source, plan)
    target = migrate(source)
    target["admissions"][0]["admitted_by"] = {"authority_id": "worker", "authority_generation": 1}
    result = evaluate_admitted(target, "root", "semantic_code_write",
        trusted_current_digest=snapshot_digest(target))
    assert result.disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize("field", ["objective_refs", "parent_refs"])
def test_migration_cannot_rewrite_objective_ancestry_or_gate_refs(field):
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][1][field] = []
    with pytest.raises(AdmissionError):
        migrate(source, plan)


def test_migration_cannot_drop_gate_refs():
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][0]["governance_gate_refs"] = []
    with pytest.raises(AdmissionError, match="cannot_drop_gate_refs"):
        migrate(source, plan)


def test_migration_cannot_drop_repository_or_governance_lineage():
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][1]["repository_lineage_refs"] = ["branch:friendly"]
    with pytest.raises(AdmissionError, match="cannot_drop_repository_lineage"):
        migrate(source, plan)
    plan = manifest(source)
    plan["admissions"][1]["governance_lineage_refs"] = []
    with pytest.raises(AdmissionError, match="invalid_v2_snapshot"):
        migrate(source, plan)


def test_conflicting_or_incomplete_admission_records_fail():
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"].append(deepcopy(plan["admissions"][0]))
    with pytest.raises(AdmissionError, match="exactly_once"):
        migrate(source, plan)
    plan = manifest(source)
    plan["admissions"].pop()
    with pytest.raises(AdmissionError, match="exactly_once"):
        migrate(source, plan)


def test_worker_proposal_cannot_downgrade_objective_or_action():
    target = migrate()
    result = evaluate_admitted(
        target, "child", "semantic_code_write",
        trusted_current_digest=snapshot_digest(target),
        worker_proposal={"objective_refs": ["unrelated"], "action": "docs_only", "ancestry_kind": "root"},
    )
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    downgraded = evaluate_admitted(target, "child", "docs_only",
        trusted_current_digest=snapshot_digest(target), worker_proposal={"action": "docs_only"})
    assert downgraded.disposition == "BLOCKED_INVALID_STATE"
    assert downgraded.reason == "action_not_admitted"


def test_ambiguous_action_and_unknown_entity_fail_closed():
    target = migrate()
    for entity, action in (("child", "unknown"), ("missing", "semantic_code_write")):
        result = evaluate_admitted(target, entity, action,
            trusted_current_digest=snapshot_digest(target))
        assert result.disposition == "BLOCKED_INVALID_STATE"


def test_released_v1_gate_stays_effective_after_migration():
    source = legacy_v1()
    gate = source["gates"][0]
    gate["state"] = "released"
    gate["release"] = {
        "gate_id": "gate:23", "generation": 3, "scope": deepcopy(gate["scope"]),
        "actions": OLD_BLOCKS[:], "asserted_human": "owner", "transport": "app",
        "application": "connector", "evidence_refs": ["fixture:unverified"],
    }
    target = migrate(source)
    result = evaluate_admitted(target, "child", "semantic_code_write",
        trusted_current_digest=snapshot_digest(target))
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.release_validation == "UNAVAILABLE"


def test_unrelated_admitted_root_is_no_match_not_authorization():
    source = legacy_v1()
    source["entities"] = [source["entities"][0]]
    source["entities"][0]["objective_refs"] = ["issue:999"]
    source["entities"][0]["lineage_refs"] = ["branch:unrelated"]
    source["entities"][0]["governance_gate_refs"] = []
    plan = manifest(legacy_v1())
    plan["admissions"] = [decision(source["entities"][0], kind="root", entity_kind="task",
        action="static_read", root_evidence=["fixture:trusted-new-root"])]
    target = migrate(source, plan)
    result = evaluate_admitted(target, "root", "static_read",
        trusted_current_digest=snapshot_digest(target))
    assert result.disposition == "NO_MATCHING_BLOCK_NOT_AUTHORIZATION"
    assert result.external_write_enforcement == "NOT_ENFORCED"
