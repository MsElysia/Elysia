"""Final repair-specific Vega probes for exact candidate 7b076548751e72879d0632c1ec687e087e43a7b8."""
from copy import deepcopy
import json
import subprocess

import pytest
from jsonschema import Draft202012Validator

from elysia_collective_seed.autopilot.contracts.admission import (
    AUTHORITY_VALIDATOR,
    V1_SCHEMA,
    V1_VALIDATOR,
    AdmissionError,
    migrate_v1_to_v2,
    validate_snapshot_version,
)
from elysia_collective_seed.autopilot.contracts.checkpoint_reference import SCHEMA, snapshot_digest
from test_round1_breakers import AUTHORITY, legacy_v1, manifest, migrate


def invoke(source, plan, **overrides):
    arguments = {
        "trusted_source_digest": snapshot_digest(source),
        "trusted_authorities": [AUTHORITY],
        "minimum_target_generation": 1,
    }
    arguments.update(overrides)
    return migrate_v1_to_v2(source, plan, **arguments)


def test_preserved_v1_schema_is_byte_exact_original_pr32_blob():
    historical = subprocess.run(
        [
            "git", "show",
            "0843d9cad29a632a42946a5daf4abe4d0b93bdb0:elysia_collective_seed/autopilot/contracts/checkpoint_snapshot.schema.json",
        ],
        check=True,
        capture_output=True,
    ).stdout
    current = subprocess.run(
        ["git", "show", "HEAD:elysia_collective_seed/autopilot/contracts/checkpoint_snapshot.v1.schema.json"],
        check=True,
        capture_output=True,
    ).stdout
    assert current == historical
    assert V1_SCHEMA == json.loads(historical.decode("utf-8"))
    Draft202012Validator.check_schema(V1_SCHEMA)
    Draft202012Validator.check_schema(SCHEMA)


def test_preserved_v1_validator_accepts_only_exact_reference_fixture():
    source = legacy_v1()
    assert V1_VALIDATOR.is_valid(source)
    for mutation in (
        lambda value: value["entities"][0].update(extra="ignored"),
        lambda value: value["entities"][0].pop("lineage_refs"),
        lambda value: value["gates"][0].update(blocked_actions=["read"]),
    ):
        malformed = deepcopy(source)
        mutation(malformed)
        assert not V1_VALIDATOR.is_valid(malformed)
        with pytest.raises(AdmissionError, match="invalid_v1_snapshot"):
            invoke(malformed, manifest(source), trusted_source_digest=snapshot_digest(malformed))


@pytest.mark.parametrize("evidence", [["dup:proof", "dup:proof"], [" leading"], ["trailing "], ["\nproof"], ["proof\n"]])
def test_root_evidence_rejects_duplicates_and_boundary_whitespace(evidence):
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][0]["root_admission_evidence"] = evidence
    with pytest.raises(AdmissionError, match="root_requires_explicit_migration_evidence"):
        invoke(source, plan)


def test_multiple_distinct_root_evidence_refs_are_accepted_and_manifest_bound():
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][0]["root_admission_evidence"] = ["review:1", "git:proof:2"]
    target = invoke(source, plan)
    assert target["admissions"][0]["ancestry_kind"] == "root"
    assert len(target["migration_provenance"]["migration_manifest_digest"]) == 64


def test_every_authority_is_validated_before_selection():
    source = legacy_v1()
    plan = manifest(source)
    valid_other = {
        "authority_id": "other",
        "authority_kind": "trusted_repository_control_plane",
        "authority_generation": 2,
        "source_refs": ["authority:other"],
    }
    assert AUTHORITY_VALIDATOR.is_valid(valid_other)
    invoke(source, plan, trusted_authorities=(valid_other, AUTHORITY))
    for field, value in (
        ("authority_kind", "worker"),
        ("authority_generation", True),
        ("source_refs", []),
        ("authority_id", " "),
    ):
        bad = deepcopy(valid_other)
        bad[field] = value
        assert not AUTHORITY_VALIDATOR.is_valid(bad)
        with pytest.raises(AdmissionError, match="invalid_trusted_authority_registry"):
            invoke(source, plan, trusted_authorities=(AUTHORITY, bad))


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-01-01T00:00:00+23:59",
        "2026-01-01T00:00:00-23:59",
        "1990-12-31T23:59:60Z",
        "2026-01-01T00:00:00.000001Z",
    ],
)
def test_rfc3339_valid_boundaries(timestamp):
    target = migrate(legacy_v1())
    target["admissions"][0]["admitted_at"] = timestamp
    validate_snapshot_version(target)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-01-01T00:00:00+24:00",
        "2026-01-01T00:00:00+00:60",
        "2026-01-01T24:00:00Z",
        "2026-01-01T00:60:00Z",
        "2026-01-01T00:00:61Z",
        "٢٠٢٦-01-01T00:00:00Z",
    ],
)
def test_rfc3339_invalid_boundaries(timestamp):
    target = migrate(legacy_v1())
    target["admissions"][0]["admitted_at"] = timestamp
    with pytest.raises(AdmissionError, match="invalid_v2_snapshot"):
        validate_snapshot_version(target)


def test_malformed_json_like_matrix_only_raises_admission_error():
    source = legacy_v1()
    cases = []

    bad = deepcopy(source)
    bad["entities"] = [None]
    cases.append((bad, manifest(source), {"trusted_source_digest": snapshot_digest(bad)}))

    bad = deepcopy(source)
    bad["source_refs"] = [False]
    cases.append((bad, manifest(source), {"trusted_source_digest": snapshot_digest(bad)}))

    bad_plan = manifest(source)
    bad_plan["migration_authority"]["authority_id"] = []
    cases.append((source, bad_plan, {}))

    bad_plan = manifest(source)
    bad_plan["admissions"] = [None]
    cases.append((source, bad_plan, {}))

    for bad_source, bad_manifest, changes in cases:
        kwargs = {
            "trusted_source_digest": snapshot_digest(source),
            "trusted_authorities": [AUTHORITY],
            "minimum_target_generation": 1,
        }
        kwargs.update(changes)
        with pytest.raises(AdmissionError):
            migrate_v1_to_v2(bad_source, bad_manifest, **kwargs)

@pytest.mark.parametrize(
    "action",
    [
        "semantic_code_write",
        "repo_write",
        "integration",
        "merge",
        "deploy",
        "external_write",
        "permission_change",
        "private_data_access",
    ],
)
def test_migrated_gate_blocks_every_consequential_v2_action(action):
    source = legacy_v1()
    plan = manifest(source)
    plan["admissions"][1]["action_classes"] = [action]
    target = invoke(source, plan)
    from elysia_collective_seed.autopilot.contracts.admission import evaluate_admitted
    result = evaluate_admitted(
        target,
        "child",
        action,
        trusted_current_digest=snapshot_digest(target),
        worker_proposal={"action": "docs_only", "ancestry_kind": "root"},
    )
    assert result.disposition == "BLOCKED_PENDING_HUMAN_RELEASE"
    assert result.release_validation == "UNAVAILABLE"
    assert result.external_write_enforcement == "NOT_ENFORCED"
