# project_guardian/tests/test_memory_review_approved_promotion_live_write_design_authorization_gate.py

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
    / "run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke.py"
)
DESIGN_AUTHORIZATION_PHRASE = "AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY"
REQUIRED_AUTHORIZATION_CASES = (
    "missing_design_authorization_artifact",
    "invalid_design_authorization_phrase",
    "mismatched_receipt_hash",
    "mismatched_receipt_tamper_hash",
    "receipt_not_pass",
    "receipt_tamper_not_pass",
    "authorization_claims_live_write_implementation",
    "authorization_claims_live_memory_write",
    "authorization_claims_vector_db_write",
    "valid_design_proposal_authorization_only",
)
INVALID_AUTHORIZATION_CASES = REQUIRED_AUTHORIZATION_CASES[:-1]
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
REQUIRED_SMOKE_FIELDS = {
    "verdict",
    "workspace",
    "authorization_case_count",
    "authorization_cases",
    "all_invalid_authorization_cases_failed_closed",
    "valid_design_authorization_passed_design_only",
    "authorized_for_live_write_design_proposal",
    "authorized_for_live_write_implementation",
    "authorized_for_live_memory_write",
    "authorized_for_vector_db_write",
    "live_memory_write_allowed",
    "vector_db_write_allowed",
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
REQUIRED_GATE_FIELDS = REQUIRED_SMOKE_FIELDS | {
    "gate_path",
    "gate_report_path",
    "gate_report_valid_json",
    "design_authorization_phrase",
    "design_authorization_phrase_valid",
    "design_authorization_artifact_present",
    "design_authorization_artifact_sha256",
    "source_final_dry_run_acceptance_receipt_sha256",
    "source_final_dry_run_acceptance_receipt_tamper_evidence_sha256",
    "final_dry_run_acceptance_receipt_verdict",
    "final_dry_run_acceptance_receipt_tamper_evidence_verdict",
    "accepted_for_final_dry_run_readiness",
    "ready_for_future_live_write_design",
    "requires_separate_live_write_design_campaign",
    "requires_separate_live_write_implementation_campaign",
    "requires_separate_operator_approval_for_live_write",
    "design_authorization_cases",
}


def _parse_json_payload(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[start:])


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = _parse_json_payload(result.stdout)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AssertionError(
            "design authorization gate smoke did not emit JSON\n"
            f"returncode={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        ) from exc
    if result.returncode != 0 and payload.get("verdict") != "FAIL":
        raise AssertionError(
            "design authorization gate smoke failed without FAIL verdict\n"
            f"returncode={result.returncode}\n"
            f"stderr={result.stderr}\n"
            f"payload={payload}"
        )
    return payload


@pytest.fixture(scope="module")
def smoke_payload() -> dict:
    base_dir = Path(tempfile.mkdtemp(prefix="elysia_lwdag_"))
    try:
        payload = _run_script("--base-dir", str(base_dir), "--keep-temp")
        yield payload
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def _assert_writes_unauthorized(payload: dict) -> None:
    assert payload["authorized_for_live_write_implementation"] is False
    assert payload["authorized_for_live_memory_write"] is False
    assert payload["authorized_for_vector_db_write"] is False
    assert payload["live_memory_write_allowed"] is False
    assert payload["vector_db_write_allowed"] is False


def _cases(payload: dict) -> dict:
    return {case["case_name"]: case for case in payload["authorization_cases"]}


def test_gate_script_emits_verdict_pass(smoke_payload):
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []


def test_gate_json_exists_and_is_valid(smoke_payload):
    path = Path(smoke_payload["gate_report_path"])
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["verdict"] == "PASS"
    assert smoke_payload["gate_report_valid_json"] is True
    assert REQUIRED_GATE_FIELDS.issubset(loaded)


def test_gate_readme_exists(smoke_payload):
    path = Path(smoke_payload["gate_readme_path"])
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert DESIGN_AUTHORIZATION_PHRASE in text
    assert "live-write design authorization gate exists" in text.lower() or (
        "Live-Write Design Authorization Gate" in text
    )


def test_design_phrase_is_recorded_exactly(smoke_payload):
    assert smoke_payload["design_authorization_phrase"] == DESIGN_AUTHORIZATION_PHRASE
    artifact = Path(smoke_payload["artifact_paths"]["valid_design_authorization_artifact"])
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["design_authorization_phrase"] == DESIGN_AUTHORIZATION_PHRASE


def test_design_phrase_validates_true_only_for_valid_case(smoke_payload):
    cases = _cases(smoke_payload)
    for name in INVALID_AUTHORIZATION_CASES:
        assert cases[name]["details"]["design_authorization_phrase_valid"] is False
    assert cases["valid_design_proposal_authorization_only"]["details"][
        "design_authorization_phrase_valid"
    ] is True
    assert smoke_payload["design_authorization_phrase_valid"] is True


def test_source_final_dry_run_receipt_hash_present(smoke_payload):
    digest = smoke_payload["source_final_dry_run_acceptance_receipt_sha256"]
    assert isinstance(digest, str) and len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
    receipt_path = Path(smoke_payload["source_final_dry_run_acceptance_receipt_path"])
    assert receipt_path.is_file()


def test_source_final_dry_run_receipt_tamper_hash_present(smoke_payload):
    digest = smoke_payload["source_final_dry_run_acceptance_receipt_tamper_evidence_sha256"]
    assert isinstance(digest, str) and len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
    tamper_path = Path(
        smoke_payload["source_final_dry_run_acceptance_receipt_tamper_evidence_path"]
    )
    assert tamper_path.is_file()


def test_receipt_verdict_pass(smoke_payload):
    assert smoke_payload["final_dry_run_acceptance_receipt_verdict"] == "PASS"
    assert smoke_payload["accepted_for_final_dry_run_readiness"] is True


def test_receipt_tamper_evidence_verdict_pass(smoke_payload):
    assert smoke_payload["final_dry_run_acceptance_receipt_tamper_evidence_verdict"] == "PASS"


def test_missing_design_authorization_artifact_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["missing_design_authorization_artifact"]
    assert case["expected_verdict"] == "FAIL"
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_write_design_proposal"] is False
    assert any(
        "missing_design_authorization_artifact" in error
        for error in case["details"]["errors"]
    )


def test_invalid_design_phrase_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["invalid_design_authorization_phrase"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any(
        "invalid_design_authorization_phrase" in error for error in case["details"]["errors"]
    )


def test_mismatched_receipt_hash_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["mismatched_receipt_hash"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("mismatched_receipt_hash" in error for error in case["details"]["errors"])


def test_mismatched_receipt_tamper_hash_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["mismatched_receipt_tamper_hash"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any(
        "mismatched_receipt_tamper_hash" in error for error in case["details"]["errors"]
    )


def test_receipt_not_pass_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["receipt_not_pass"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("receipt_not_pass" in error for error in case["details"]["errors"])


def test_receipt_tamper_not_pass_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["receipt_tamper_not_pass"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert any("receipt_tamper_not_pass" in error for error in case["details"]["errors"])


def test_authorization_claiming_live_write_implementation_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["authorization_claims_live_write_implementation"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_write_implementation"] is False
    assert any(
        "authorization_claims_live_write_implementation" in error
        for error in case["details"]["errors"]
    )


def test_authorization_claiming_live_memory_write_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["authorization_claims_live_memory_write"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_memory_write"] is False
    assert any(
        "authorization_claims_live_memory_write" in error
        for error in case["details"]["errors"]
    )


def test_authorization_claiming_vector_db_write_fails_closed(smoke_payload):
    case = _cases(smoke_payload)["authorization_claims_vector_db_write"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["details"]["authorized_for_vector_db_write"] is False
    assert any(
        "authorization_claims_vector_db_write" in error for error in case["details"]["errors"]
    )


def test_valid_design_authorization_passes_design_proposal_only(smoke_payload):
    case = _cases(smoke_payload)["valid_design_proposal_authorization_only"]
    assert case["expected_verdict"] == "PASS"
    assert case["actual_verdict"] == "PASS"
    assert case["detected"] is True
    assert case["details"]["authorized_for_live_write_design_proposal"] is True
    assert case["details"]["authorized_for_live_write_implementation"] is False
    assert case["details"]["authorized_for_live_memory_write"] is False
    assert case["details"]["authorized_for_vector_db_write"] is False
    assert case["details"]["live_memory_write_allowed"] is False
    assert case["details"]["vector_db_write_allowed"] is False
    assert case["details"]["errors"] == []
    assert smoke_payload["valid_design_authorization_passed_design_only"] is True
    assert smoke_payload["authorized_for_live_write_design_proposal"] is True


def test_valid_design_authorization_does_not_authorize_implementation(smoke_payload):
    case = _cases(smoke_payload)["valid_design_proposal_authorization_only"]
    assert case["details"]["authorized_for_live_write_implementation"] is False
    assert smoke_payload["authorized_for_live_write_implementation"] is False


def test_valid_design_authorization_does_not_allow_live_memory_write(smoke_payload):
    case = _cases(smoke_payload)["valid_design_proposal_authorization_only"]
    assert case["details"]["authorized_for_live_memory_write"] is False
    assert case["details"]["live_memory_write_allowed"] is False
    assert smoke_payload["live_memory_write_allowed"] is False


def test_valid_design_authorization_does_not_allow_vector_db_write(smoke_payload):
    case = _cases(smoke_payload)["valid_design_proposal_authorization_only"]
    assert case["details"]["authorized_for_vector_db_write"] is False
    assert case["details"]["vector_db_write_allowed"] is False
    assert smoke_payload["vector_db_write_allowed"] is False


def test_authorized_for_live_write_implementation_false_for_every_case(smoke_payload):
    for case in smoke_payload["authorization_cases"]:
        assert case["details"]["authorized_for_live_write_implementation"] is False
    assert smoke_payload["authorized_for_live_write_implementation"] is False


def test_authorized_for_live_memory_write_false_for_every_case(smoke_payload):
    for case in smoke_payload["authorization_cases"]:
        assert case["details"]["authorized_for_live_memory_write"] is False
    assert smoke_payload["authorized_for_live_memory_write"] is False


def test_authorized_for_vector_db_write_false_for_every_case(smoke_payload):
    for case in smoke_payload["authorization_cases"]:
        assert case["details"]["authorized_for_vector_db_write"] is False
    assert smoke_payload["authorized_for_vector_db_write"] is False


def test_live_memory_write_allowed_false_for_every_case(smoke_payload):
    for case in smoke_payload["authorization_cases"]:
        assert case["details"]["live_memory_write_allowed"] is False
    assert smoke_payload["live_memory_write_allowed"] is False


def test_vector_db_write_allowed_false_for_every_case(smoke_payload):
    for case in smoke_payload["authorization_cases"]:
        assert case["details"]["vector_db_write_allowed"] is False
    assert smoke_payload["vector_db_write_allowed"] is False


def test_invalid_cases_keep_design_and_write_authorization_false(smoke_payload):
    cases = _cases(smoke_payload)
    for name in INVALID_AUTHORIZATION_CASES:
        details = cases[name]["details"]
        assert details["authorized_for_live_write_design_proposal"] is False
        assert details["authorized_for_live_write_implementation"] is False
        assert details["authorized_for_live_memory_write"] is False
        assert details["authorized_for_vector_db_write"] is False
        assert details["live_memory_write_allowed"] is False
        assert details["vector_db_write_allowed"] is False


def test_requires_separate_campaigns_and_operator_approval(smoke_payload):
    assert smoke_payload["requires_separate_live_write_design_campaign"] is True
    assert smoke_payload["requires_separate_live_write_implementation_campaign"] is True
    assert smoke_payload["requires_separate_operator_approval_for_live_write"] is True
    assert smoke_payload["ready_for_future_live_write_design"] is True
    assert smoke_payload["operator_required"] is True
    assert smoke_payload["dry_run"] is True
    assert smoke_payload["local_only"] is True


def test_json_report_contains_required_pass_contract(smoke_payload):
    assert REQUIRED_SMOKE_FIELDS.issubset(smoke_payload)
    assert REQUIRED_GATE_FIELDS.issubset(smoke_payload)
    assert smoke_payload["verdict"] == "PASS"
    names = [case["case_name"] for case in smoke_payload["authorization_cases"]]
    assert names == list(REQUIRED_AUTHORIZATION_CASES)
    assert smoke_payload["authorization_case_count"] == len(REQUIRED_AUTHORIZATION_CASES)
    assert smoke_payload["all_invalid_authorization_cases_failed_closed"] is True
    assert smoke_payload["valid_design_authorization_passed_design_only"] is True
    _assert_safety_flags_false(smoke_payload)
    _assert_writes_unauthorized(smoke_payload)


def test_no_network_account_api_or_live_paths_written(smoke_payload):
    _assert_safety_flags_false(smoke_payload)
    assert smoke_payload["live_memory_written"] is False
    assert smoke_payload["live_vector_db_written"] is False
    assert "forbidden_live_writes" not in smoke_payload
    report = json.loads(Path(smoke_payload["gate_report_path"]).read_text(encoding="utf-8"))
    assert "forbidden_live_writes" not in report


def test_preserved_workspace_artifacts(smoke_payload):
    workspace = Path(smoke_payload["workspace"]).resolve()
    gate_dir = Path(smoke_payload["gate_path"])
    gate_json_path = Path(smoke_payload["gate_report_path"])
    readme_path = Path(smoke_payload["gate_readme_path"])
    receipt_path = Path(smoke_payload["source_final_dry_run_acceptance_receipt_path"])
    tamper_path = Path(
        smoke_payload["source_final_dry_run_acceptance_receipt_tamper_evidence_path"]
    )
    valid_artifact = Path(smoke_payload["artifact_paths"]["valid_design_authorization_artifact"])
    for path in (gate_dir, gate_json_path, readme_path, receipt_path, tamper_path, valid_artifact):
        assert path.exists()
        path.resolve().relative_to(workspace)

    authorization = json.loads(valid_artifact.read_text(encoding="utf-8"))
    assert authorization["design_authorization_phrase"] == DESIGN_AUTHORIZATION_PHRASE
    assert authorization["authorized_for_live_write_design_proposal"] is True
    assert authorization["authorized_for_live_write_implementation"] is False
    assert authorization["authorized_for_live_memory_write"] is False
    assert authorization["authorized_for_vector_db_write"] is False
    assert authorization["live_memory_write_allowed"] is False
    assert authorization["vector_db_write_allowed"] is False
    assert authorization["dry_run"] is True
    assert authorization["local_only"] is True
    assert (
        authorization["source_final_dry_run_acceptance_receipt_sha256"]
        == smoke_payload["source_final_dry_run_acceptance_receipt_sha256"]
    )
    assert (
        authorization["source_final_dry_run_acceptance_receipt_tamper_evidence_sha256"]
        == smoke_payload["source_final_dry_run_acceptance_receipt_tamper_evidence_sha256"]
    )
    assert authorization["final_dry_run_acceptance_receipt_verdict"] == "PASS"
    assert authorization["final_dry_run_acceptance_receipt_tamper_evidence_verdict"] == "PASS"


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
    payload = _parse_json_payload(result.stdout)
    assert payload["verdict"] == "FAIL"
    assert "repository root" in payload["errors"][0]
