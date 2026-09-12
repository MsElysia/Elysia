# project_guardian/tests/test_memory_review_approved_promotion_final_readiness_operator_acceptance_gate.py

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke.py"
)
ACCEPTANCE_PHRASE = "ACCEPT_FINAL_DRY_RUN_READINESS_PACKET_ONLY"
REQUIRED_ACCEPTANCE_CASES = (
    "missing_acceptance_artifact",
    "invalid_acceptance_phrase",
    "mismatched_packet_hash",
    "mismatched_tamper_evidence_hash",
    "tamper_evidence_not_pass",
    "acceptance_claims_live_memory_write",
    "acceptance_claims_vector_db_write",
    "valid_final_dry_run_acceptance",
)
INVALID_ACCEPTANCE_CASES = REQUIRED_ACCEPTANCE_CASES[:-1]
FORBIDDEN_SCRIPT_TOKENS = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "requests.",
    "urllib.",
    "socket.",
    "http://",
    "https://",
    "@app.",
    "FastAPI",
    "Flask",
    "route(",
)
REQUIRED_REPORT_FIELDS = {
    "verdict",
    "workspace",
    "gate_path",
    "gate_report_path",
    "gate_report_valid_json",
    "acceptance_phrase",
    "acceptance_phrase_valid",
    "acceptance_artifact_present",
    "acceptance_artifact_sha256",
    "source_final_readiness_packet_path",
    "source_final_readiness_packet_sha256",
    "source_final_readiness_tamper_evidence_path",
    "source_final_readiness_tamper_evidence_sha256",
    "packet_tamper_evidence_verdict",
    "clean_packet_verdict",
    "operator_acceptance_valid",
    "accepted_for_final_dry_run_readiness",
    "accepted_for_live_memory_write",
    "accepted_for_vector_db_write",
    "ready_for_future_live_write_design",
    "requires_separate_live_write_campaign",
    "live_memory_write_allowed",
    "vector_db_write_allowed",
    "live_write_blocked_reason",
    "vector_db_write_blocked_reason",
    "acceptance_cases",
    "acceptance_case_count",
    "all_invalid_acceptance_cases_failed_closed",
    "valid_acceptance_passed_dry_run_only",
    "operator_required",
    "dry_run",
    "local_only",
    "model_called",
    "embeddings_used",
    "live_memory_written",
    "live_vector_db_written",
    "account_api_network_accessed",
    "autonomy_enabled",
    "errors",
}


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    payload_text = result.stdout
    start = payload_text.find("{")
    if start < 0:
        raise AssertionError(
            "acceptance gate smoke did not emit JSON\n"
            f"returncode={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )
    payload = json.loads(payload_text[start:])
    if result.returncode != 0 and payload.get("verdict") != "FAIL":
        raise AssertionError(
            "acceptance gate smoke failed without FAIL verdict\n"
            f"returncode={result.returncode}\n"
            f"stderr={result.stderr}\n"
            f"payload={payload}"
        )
    return payload


@pytest.fixture(scope="module")
def smoke_payload() -> dict:
    return _run_script()


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def _assert_live_writes_blocked(payload: dict) -> None:
    assert payload["accepted_for_live_memory_write"] is False
    assert payload["accepted_for_vector_db_write"] is False
    assert payload["ready_for_future_live_write_design"] is False
    assert payload["requires_separate_live_write_campaign"] is True
    assert payload["live_memory_write_allowed"] is False
    assert payload["vector_db_write_allowed"] is False


def test_clean_packet_and_tamper_evidence_validate_pass(smoke_payload):
    assert smoke_payload["clean_packet_verdict"] == "PASS"
    assert smoke_payload["packet_tamper_evidence_verdict"] == "PASS"
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []


def test_missing_acceptance_artifact_fails_closed(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["missing_acceptance_artifact"]
    assert case["expected_verdict"] == "FAIL"
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["operator_acceptance_valid"] is False
    assert case["details"]["accepted_for_final_dry_run_readiness"] is False
    assert any("missing_acceptance_artifact" in error for error in case["details"]["errors"])


def test_invalid_acceptance_phrase_fails_closed(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["invalid_acceptance_phrase"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("invalid_acceptance_phrase" in error for error in case["details"]["errors"])


def test_mismatched_packet_hash_fails_closed(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["mismatched_packet_hash"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("mismatched_packet_hash" in error for error in case["details"]["errors"])


def test_mismatched_tamper_evidence_hash_fails_closed(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["mismatched_tamper_evidence_hash"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any(
        "mismatched_tamper_evidence_hash" in error for error in case["details"]["errors"]
    )


def test_tamper_evidence_not_pass_fails_closed(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["tamper_evidence_not_pass"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("tamper_evidence_not_pass" in error for error in case["details"]["errors"])


def test_acceptance_claiming_live_memory_write_fails_closed(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["acceptance_claims_live_memory_write"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["accepted_for_live_memory_write"] is False
    assert any(
        "acceptance_claims_live_memory_write" in error
        for error in case["details"]["errors"]
    )


def test_acceptance_claiming_vector_db_write_fails_closed(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["acceptance_claims_vector_db_write"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["accepted_for_vector_db_write"] is False
    assert any(
        "acceptance_claims_vector_db_write" in error
        for error in case["details"]["errors"]
    )


def test_valid_acceptance_passes_dry_run_only(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    case = cases["valid_final_dry_run_acceptance"]
    assert case["expected_verdict"] == "PASS"
    assert case["actual_verdict"] == "PASS"
    assert case["detected"] is True
    assert case["details"]["operator_acceptance_valid"] is True
    assert case["details"]["accepted_for_final_dry_run_readiness"] is True
    assert case["details"]["accepted_for_live_memory_write"] is False
    assert case["details"]["accepted_for_vector_db_write"] is False
    assert case["details"]["live_memory_write_allowed"] is False
    assert case["details"]["vector_db_write_allowed"] is False
    assert case["details"]["errors"] == []
    assert smoke_payload["valid_acceptance_passed_dry_run_only"] is True


def test_accepted_for_final_dry_run_readiness_true_only_for_valid_case(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["acceptance_cases"]}
    for name in INVALID_ACCEPTANCE_CASES:
        assert cases[name]["details"]["accepted_for_final_dry_run_readiness"] is False
        assert cases[name]["details"]["operator_acceptance_valid"] is False
    assert cases["valid_final_dry_run_acceptance"]["details"][
        "accepted_for_final_dry_run_readiness"
    ] is True


def test_live_and_vector_writes_false_for_every_case(smoke_payload):
    for case in smoke_payload["acceptance_cases"]:
        assert case["details"]["accepted_for_live_memory_write"] is False
        assert case["details"]["accepted_for_vector_db_write"] is False
        assert case["details"]["live_memory_write_allowed"] is False
        assert case["details"]["vector_db_write_allowed"] is False
    _assert_live_writes_blocked(smoke_payload)


def test_requires_separate_live_write_campaign_and_blocked_reasons(smoke_payload):
    assert smoke_payload["requires_separate_live_write_campaign"] is True
    assert smoke_payload["live_write_blocked_reason"]
    assert smoke_payload["vector_db_write_blocked_reason"]
    assert smoke_payload["acceptance_phrase"] == ACCEPTANCE_PHRASE
    assert smoke_payload["acceptance_phrase_valid"] is True
    packet_hash = smoke_payload["source_final_readiness_packet_sha256"]
    tamper_hash = smoke_payload["source_final_readiness_tamper_evidence_sha256"]
    assert isinstance(packet_hash, str) and len(packet_hash) == 64
    assert isinstance(tamper_hash, str) and len(tamper_hash) == 64
    assert all(char in "0123456789abcdef" for char in packet_hash)
    assert all(char in "0123456789abcdef" for char in tamper_hash)


def test_json_report_contains_required_pass_contract(smoke_payload):
    assert REQUIRED_REPORT_FIELDS.issubset(smoke_payload)
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["gate_report_valid_json"] is True
    names = [case["case_name"] for case in smoke_payload["acceptance_cases"]]
    assert names == list(REQUIRED_ACCEPTANCE_CASES)
    assert smoke_payload["acceptance_case_count"] == len(REQUIRED_ACCEPTANCE_CASES)
    assert smoke_payload["all_invalid_acceptance_cases_failed_closed"] is True
    assert smoke_payload["valid_acceptance_passed_dry_run_only"] is True
    assert smoke_payload["operator_required"] is True
    assert smoke_payload["dry_run"] is True
    assert smoke_payload["local_only"] is True
    _assert_safety_flags_false(smoke_payload)
    _assert_live_writes_blocked(smoke_payload)


def test_acceptance_gate_preserved_workspace_artifacts():
    base_dir = Path(tempfile.mkdtemp(prefix="elysia_fr_ag_"))
    try:
        payload = _run_script("--base-dir", str(base_dir))
        assert payload["verdict"] == "PASS", payload.get("errors")
        assert payload["workspace_preserved"] is True
        workspace = base_dir.resolve()
        assert Path(payload["workspace"]) == workspace
        _assert_preserved_workspace_contents(payload, workspace)
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def _assert_preserved_workspace_contents(payload: dict, workspace: Path) -> None:

    gate_dir = Path(payload["gate_path"])
    gate_json_path = Path(payload["gate_report_path"])
    packet_path = Path(payload["source_final_readiness_packet_path"])
    tamper_path = Path(payload["source_final_readiness_tamper_evidence_path"])
    readme_path = Path(payload["gate_readme_path"])
    valid_artifact = Path(payload["artifact_paths"]["valid_acceptance_artifact"])

    for path in (gate_dir, gate_json_path, packet_path, tamper_path, readme_path, valid_artifact):
        assert path.exists()
        path.resolve().relative_to(workspace)

    report = json.loads(gate_json_path.read_text(encoding="utf-8"))
    acceptance = json.loads(valid_artifact.read_text(encoding="utf-8"))
    readme = readme_path.read_text(encoding="utf-8")

    assert report["verdict"] == "PASS"
    assert report["gate_report_valid_json"] is True
    assert acceptance["acceptance_phrase"] == ACCEPTANCE_PHRASE
    assert acceptance["accepted_for_final_dry_run_readiness"] is True
    assert acceptance["accepted_for_live_memory_write"] is False
    assert acceptance["accepted_for_vector_db_write"] is False
    assert ACCEPTANCE_PHRASE in readme
    assert "forbidden_live_writes" not in report
    _assert_safety_flags_false(report)
    _assert_live_writes_blocked(report)


def test_script_has_no_network_ui_or_route_behavior():
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    for token in FORBIDDEN_SCRIPT_TOKENS:
        assert token not in script


def test_script_refuses_repository_root_workspace():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", "--base-dir", str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "FAIL"
    assert "repository root" in payload["errors"][0]
