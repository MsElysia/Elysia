"""Fresh independent attacks added for exact candidate caf735ba44c0d992d7562f3f99cbbb39404c11bc."""
from copy import deepcopy

import pytest

from elysia_collective_seed.autopilot.contracts.admission import AdmissionError, migrate_v1_to_v2, validate_snapshot_version
from elysia_collective_seed.autopilot.contracts.checkpoint_reference import snapshot_digest
from test_round1_breakers import AUTHORITY, legacy_v1, manifest, migrate


def migrate_exact(source, plan=None, authorities=None):
    return migrate_v1_to_v2(
        source,
        manifest(source) if plan is None else plan,
        trusted_source_digest=snapshot_digest(source),
        trusted_authorities=[AUTHORITY] if authorities is None else authorities,
    )


@pytest.mark.parametrize("evidence", [[False], [0], [{}], [""], [" "], ["\t"]])
def test_root_admission_evidence_requires_nonempty_reference_strings(evidence):
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][0]["root_admission_evidence"] = evidence
    with pytest.raises(AdmissionError):
        migrate_exact(source, plan)


def test_exact_v1_rejects_unknown_entity_fields_instead_of_ignoring_them():
    source = legacy_v1()
    source["entities"][0]["worker_claim"] = "new-trusted-root"
    with pytest.raises(AdmissionError):
        migrate_exact(source)


@pytest.mark.parametrize("lineage", [None, [], [""], [" "], [False], "branch:restack"])
def test_exact_v1_rejects_missing_or_malformed_entity_lineage(lineage):
    source = legacy_v1()
    if lineage is None:
        source["entities"][0].pop("lineage_refs")
    else:
        source["entities"][0]["lineage_refs"] = lineage
    # Use a pristine decision so missing/empty source lineage cannot weaken the
    # preservation comparison and be silently replaced by manifest content.
    plan = manifest(legacy_v1())
    with pytest.raises(AdmissionError):
        migrate_exact(source, plan)


@pytest.mark.parametrize(
    "blocked_actions",
    [
        ["read"],
        ["claim", "repo_write", "integration", "merge", "deploy", "external_write"],
        [],
    ],
)
def test_exact_v1_rejects_incomplete_legacy_gate_action_set(blocked_actions):
    source = legacy_v1()
    source["gates"][0]["blocked_actions"] = blocked_actions
    with pytest.raises(AdmissionError):
        migrate_exact(source)


@pytest.mark.parametrize(
    "extra_authority",
    [
        {},
        {"authority_id": "unused", "authority_generation": 1},
        {
            "authority_id": "unused",
            "authority_generation": 1,
            "authority_kind": "worker_self_assertion",
            "source_refs": ["worker:claim"],
        },
        {
            "authority_id": "unused",
            "authority_generation": 1,
            "authority_kind": "trusted_migration_control_plane",
            "source_refs": [],
        },
        {
            "authority_id": "unused",
            "authority_generation": True,
            "authority_kind": "trusted_migration_control_plane",
            "source_refs": ["fixture:unused"],
        },
        {
            "authority_id": "unused",
            "authority_generation": 1,
            "authority_kind": "trusted_migration_control_plane",
            "source_refs": ["fixture:unused"],
            "worker_claim": "trusted",
        },
    ],
)
def test_all_trusted_authority_records_are_validated_even_when_unselected(extra_authority):
    source = legacy_v1()
    with pytest.raises(AdmissionError, match="authority|malformed"):
        migrate_exact(source, authorities=[AUTHORITY, extra_authority])


def test_valid_unselected_trusted_authority_does_not_change_selected_authority():
    source = legacy_v1()
    other = {
        "authority_id": "other-migration-plane",
        "authority_generation": 2,
        "authority_kind": "trusted_migration_control_plane",
        "source_refs": ["fixture:other-authority"],
    }
    target = migrate_exact(source, authorities=[other, AUTHORITY])
    assert target["admission_authorities"] == [AUTHORITY]


@pytest.mark.parametrize(
    "timestamp",
    [
        "٢٠٢٦-09-12T00:00:00Z",
        "2026-٠٩-12T00:00:00Z",
        "2026-09-12T٠٠:00:00Z",
        "2026-09-12T00:00:00+٠١:00",
    ],
)
def test_rfc3339_rejects_non_ascii_digits(timestamp):
    target = migrate(legacy_v1())
    target["admissions"][0]["admitted_at"] = timestamp
    with pytest.raises(AdmissionError, match="invalid_v2_snapshot"):
        validate_snapshot_version(target)


def test_malformed_root_evidence_cannot_satisfy_new_root_precondition():
    source = legacy_v1()
    source["entities"] = [source["entities"][0]]
    source["entities"][0]["objective_refs"] = ["worker:new-objective"]
    source["entities"][0]["lineage_refs"] = ["worker:new-branch"]
    source["entities"][0]["governance_gate_refs"] = []
    plan = manifest(legacy_v1())
    root = deepcopy(plan["admissions"][0])
    root["objective_refs"] = ["worker:new-objective"]
    root["repository_lineage_refs"] = ["worker:new-branch"]
    root["governance_lineage_refs"] = ["worker:new-governance-lineage"]
    root["governance_gate_refs"] = []
    root["root_admission_evidence"] = [False]
    root["action_classes"] = ["semantic_code_write"]
    plan["admissions"] = [root]
    with pytest.raises(AdmissionError):
        migrate_exact(source, plan)



