"""Fresh repair-edge attacks for exact candidate 518f9f8551998a18527c817ecea819afa4d5132d."""
from copy import deepcopy

import pytest

from elysia_collective_seed.autopilot.contracts.admission import (
    AdmissionError,
    evaluate_admitted,
    migrate_v1_to_v2,
    validate_snapshot_version,
)
from elysia_collective_seed.autopilot.contracts.checkpoint_reference import snapshot_digest
from test_round1_breakers import (
    AUTHORITY,
    AUTHORITY_REF,
    admission,
    legacy_v1,
    manifest,
    migrate,
)


_DEFAULT_AUTHORITIES = object()

def call_migration(source, plan, *, authorities=_DEFAULT_AUTHORITIES, pin=None, minimum=1):
    return migrate_v1_to_v2(
        source,
        plan,
        trusted_source_digest=snapshot_digest(source) if pin is None else pin,
        trusted_authorities=[AUTHORITY] if authorities is _DEFAULT_AUTHORITIES else authorities,
        minimum_target_generation=minimum,
    )


@pytest.mark.parametrize("authorities", [None, {}, "authority", 1, True, [None], ["authority"]])
def test_malformed_trusted_authorities_normalize_to_admission_error(authorities):
    source = legacy_v1()
    with pytest.raises(AdmissionError):
        call_migration(source, manifest(source), authorities=authorities)


def test_unhashable_trusted_authority_identity_normalizes_to_admission_error():
    source = legacy_v1()
    authority = deepcopy(AUTHORITY)
    authority["authority_id"] = ["unhashable"]
    with pytest.raises(AdmissionError):
        call_migration(source, manifest(source), authorities=[authority])


@pytest.mark.parametrize("field", ["authority_id", "authority_generation"])
def test_unhashable_manifest_authority_ref_normalizes_to_admission_error(field):
    source = legacy_v1()
    plan = manifest(source)
    plan["migration_authority"][field] = ["unhashable"]
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


@pytest.mark.parametrize("field", ["authority_id", "authority_generation"])
def test_missing_manifest_authority_ref_field_fails_closed(field):
    source = legacy_v1()
    plan = manifest(source)
    plan["migration_authority"].pop(field)
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


def test_manifest_authority_ref_with_extra_field_fails_schema_closed():
    source = legacy_v1()
    plan = manifest(source)
    plan["migration_authority"]["worker_claim"] = "trusted"
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("from_schema_version", True),
        ("from_schema_version", 1.0),
        ("to_schema_version", True),
        ("to_schema_version", 2.0),
        ("from_schema_version", "1"),
        ("to_schema_version", "2"),
    ],
)
def test_manifest_versions_are_exact_python_integers(field, value):
    source = legacy_v1()
    plan = manifest(source)
    plan[field] = value
    with pytest.raises(AdmissionError, match="explicit_v1_to_v2_manifest_required"):
        call_migration(source, plan)


@pytest.mark.parametrize("version", [True, 1.0, "1", None, 0, 2])
def test_source_version_is_exact_integer_one(version):
    source = legacy_v1()
    source["schema_version"] = version
    with pytest.raises(AdmissionError, match="source_must_be_v1"):
        call_migration(source, manifest(legacy_v1()), pin="0" * 64)


@pytest.mark.parametrize("version", [True, 2.0, "2", None, 1, 3])
def test_target_version_is_exact_integer_two(version):
    target = migrate(legacy_v1())
    target["schema_version"] = version
    with pytest.raises(AdmissionError, match="unsupported_schema_version"):
        validate_snapshot_version(target)


def test_empty_legacy_entities_fail_closed_before_probe_indexing():
    source = legacy_v1()
    source["entities"] = []
    plan = manifest(legacy_v1())
    plan["admissions"] = []
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


def test_unhashable_legacy_entity_identity_normalizes_to_admission_error():
    source = legacy_v1()
    source["entities"][0]["entity_id"] = ["unhashable"]
    plan = manifest(legacy_v1())
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


def test_unhashable_manifest_admission_identity_normalizes_to_admission_error():
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][0]["entity_id"] = ["unhashable"]
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ("source", "lineage_refs"),
        ("decision", "repository_lineage_refs"),
    ],
)
def test_noniterable_lineage_normalizes_to_admission_error(container, field):
    source = legacy_v1()
    plan = manifest(source)
    if container == "source":
        source["entities"][1][field] = None
        plan = manifest(legacy_v1())
    else:
        plan["admissions"][1][field] = None
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


def test_non_json_legacy_content_normalizes_to_admission_error():
    source = legacy_v1()
    source["source_refs"] = [object()]
    with pytest.raises(AdmissionError):
        migrate_v1_to_v2(
            source,
            manifest(legacy_v1()),
            trusted_source_digest="0" * 64,
            trusted_authorities=[AUTHORITY],
        )


def test_non_json_manifest_content_normalizes_to_admission_error():
    source = legacy_v1()
    plan = manifest(source)
    plan["unexpected"] = object()
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


@pytest.mark.parametrize("minimum", [None, "8", 8.0, True, [], {}])
def test_invalid_minimum_generation_normalizes_to_admission_error(minimum):
    source = legacy_v1()
    with pytest.raises(AdmissionError):
        call_migration(source, manifest(source), minimum=minimum)


def test_duplicate_manifest_admissions_fail_closed():
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"].append(deepcopy(plan["admissions"][0]))
    with pytest.raises(AdmissionError):
        call_migration(source, plan)


def test_cycle_in_migration_target_fails_semantic_probe():
    source = legacy_v1()
    source["entities"][0]["parent_refs"] = ["child"]
    source["entities"][1]["parent_refs"] = ["root"]
    plan = manifest(source)
    for record in plan["admissions"]:
        record["ancestry_kind"] = "derived"
        record.pop("root_admission_evidence", None)
    with pytest.raises(AdmissionError, match="ancestry_cycle|invalid_v2_semantics"):
        call_migration(source, plan)


def test_semantic_probe_checks_disconnected_records_even_when_first_is_no_match():
    source = legacy_v1()
    source["entities"][0]["objective_refs"] = ["unrelated"]
    source["entities"][0]["lineage_refs"] = ["branch:unrelated"]
    source["entities"][0]["governance_gate_refs"] = []
    source["entities"][1]["parent_refs"] = ["absent"]
    plan = manifest(source)
    plan["admissions"][0]["action_classes"] = ["static_read"]
    with pytest.raises(AdmissionError, match="missing_parent|invalid_v2_semantics"):
        call_migration(source, plan)


def test_semantic_probe_accepts_both_blocked_and_no_match_as_non_authorizing_states():
    gated_source = legacy_v1()
    gated = migrate(gated_source)
    assert evaluate_admitted(
        gated, "root", "semantic_code_write", trusted_current_digest=snapshot_digest(gated)
    ).disposition == "BLOCKED_PENDING_HUMAN_RELEASE"

    unrelated_source = legacy_v1()
    unrelated_source["gates"] = []
    for entity in unrelated_source["entities"]:
        entity["governance_gate_refs"] = []
    plan = manifest(unrelated_source)
    plan["admissions"][0]["action_classes"] = ["static_read"]
    unrelated = call_migration(unrelated_source, plan)
    assert evaluate_admitted(
        unrelated, "root", "static_read", trusted_current_digest=snapshot_digest(unrelated)
    ).disposition == "NO_MATCHING_BLOCK_NOT_AUTHORIZATION"


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_authority", "duplicate_gate", "duplicate_admission", "missing_parent", "cycle", "missing_gate", "unknown_authority"],
)
def test_direct_v2_semantic_corruption_blocks(mutation):
    target = migrate(legacy_v1())
    if mutation == "duplicate_authority":
        target["admission_authorities"].append(deepcopy(target["admission_authorities"][0]))
    elif mutation == "duplicate_gate":
        target["gates"].append(deepcopy(target["gates"][0]))
    elif mutation == "duplicate_admission":
        target["admissions"].append(deepcopy(target["admissions"][0]))
    elif mutation == "missing_parent":
        target["admissions"][1]["parent_refs"] = ["absent"]
    elif mutation == "cycle":
        target["admissions"][0]["ancestry_kind"] = "derived"
        target["admissions"][0]["parent_refs"] = ["child"]
    elif mutation == "missing_gate":
        target["admissions"][1]["governance_gate_refs"] = ["absent"]
    else:
        target["admissions"][1]["admitted_by"] = {
            "authority_id": "worker", "authority_generation": 1
        }
    result = evaluate_admitted(
        target,
        "root",
        "semantic_code_write",
        trusted_current_digest=snapshot_digest(target),
    )
    assert result.disposition == "BLOCKED_INVALID_STATE"


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-12T00:00:00Z",
        "2026-09-12T00:00:00+00:00",
        "2026-09-12T00:00:00-04:00",
        "2024-02-29T23:59:59.123456Z",
    ],
)
def test_valid_rfc3339_timestamps_are_accepted(timestamp):
    target = migrate(legacy_v1())
    target["admissions"][0]["admitted_at"] = timestamp
    target["migration_provenance"]["migrated_at"] = timestamp
    validate_snapshot_version(target)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-12T00:00:00",
        "2026-09-12 00:00:00Z",
        "2026-09-12T00:00:00+01:60",
        "2026-09-12T00:00:00+24:00",
        "2023-02-29T00:00:00Z",
        "not-a-date-time",
    ],
)
def test_invalid_or_timezone_free_rfc3339_timestamps_are_rejected(timestamp):
    target = migrate(legacy_v1())
    target["admissions"][0]["admitted_at"] = timestamp
    with pytest.raises(AdmissionError, match="invalid_v2_snapshot"):
        validate_snapshot_version(target)


def test_rfc3339_leap_second_is_accepted():
    target = migrate(legacy_v1())
    target["admissions"][0]["admitted_at"] = "1990-12-31T23:59:60Z"
    validate_snapshot_version(target)



