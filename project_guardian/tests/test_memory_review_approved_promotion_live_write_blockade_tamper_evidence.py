# project_guardian/tests/test_memory_review_approved_promotion_live_write_blockade_tamper_evidence.py

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke.py"
)
REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_report_field",
    "source_staging_manifest_hash_mismatch",
    "clean_staging_invalid",
    "staging_tamper_evidence_failed",
    "live_memory_write_allowed",
    "live_memory_write_not_denied",
    "live_memory_write_attempted",
    "live_memory_write_performed",
    "live_memory_write_path_created",
    "vector_db_write_allowed",
    "vector_db_write_not_denied",
    "vector_db_write_attempted",
    "vector_db_write_performed",
    "vector_db_write_path_created",
    "runtime_memory_files_created_nonzero",
    "vector_db_files_created_nonzero",
    "ready_for_live_memory_write_true",
    "future_live_write_allowed_true",
    "future_milestone_not_required",
    "missing_denial_reason",
    "unsafe_metadata",
)
DENIAL_REASON = (
    "Live memory write is blocked because this campaign only proves dry-run "
    "staging safety. A separate explicit future milestone is required before "
    "any live memory or vector DB write path may exist."
)


def _load_smoke_module():
    module_name = "run_memory_review_approved_promotion_live_write_blockade_tamper_evidence_smoke"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke_module()


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


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


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _valid_report(tmp_path: Path, **overrides: Any) -> Dict[str, Any]:
    staging_path = tmp_path / "operator_approved_staging_manifest.json"
    _write_json(staging_path, {"verdict": "PASS", "kind": "staging"})
    report = {
        "verdict": "PASS",
        "workspace": str(tmp_path),
        "blockade_path": str(tmp_path / "approved_promotion_live_write_blockade"),
        "live_write_blockade_report_path": str(tmp_path / "live_write_blockade_report.json"),
        "live_write_blockade_report_valid_json": True,
        "source_staging_manifest_path": str(staging_path),
        "source_staging_manifest_sha256": SMOKE._sha256_file(staging_path),
        "source_staging_tamper_evidence_verdict": "PASS",
        "clean_staging_valid": True,
        "operator_approval_valid": True,
        "approval_gate_verdict": "PASS",
        "tamper_evidence_verdict": "PASS",
        "ready_for_operator_approved_staging": True,
        "ready_for_live_memory_write": False,
        "future_live_write_allowed": False,
        "live_memory_write_requested": True,
        "live_memory_write_allowed": False,
        "live_memory_write_denied": True,
        "live_memory_write_denial_reason": DENIAL_REASON,
        "live_memory_write_attempted": False,
        "live_memory_write_performed": False,
        "live_memory_write_path": str(tmp_path / "forbidden_live_writes" / "runtime_memory.jsonl"),
        "live_memory_write_path_created": False,
        "vector_db_write_requested": True,
        "vector_db_write_allowed": False,
        "vector_db_write_denied": True,
        "vector_db_write_denial_reason": DENIAL_REASON,
        "vector_db_write_attempted": False,
        "vector_db_write_performed": False,
        "vector_db_write_path": str(tmp_path / "forbidden_live_writes" / "vector_db.index"),
        "vector_db_write_path_created": False,
        "runtime_memory_files_created": 0,
        "vector_db_files_created": 0,
        "promotion_item_count": 2,
        "approved_candidate_count": 1,
        "edited_candidate_count": 1,
        "excluded_rejected_count": 1,
        "operator_required": True,
        "requires_future_live_write_milestone": True,
        "dry_run": True,
        "local_only": True,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "live_vector_db_written": False,
        "account_api_network_accessed": False,
        "autonomy_enabled": False,
        "errors": [],
    }
    report.update(overrides)
    return report


def _cases_by_name(payload: dict) -> Dict[str, dict]:
    return {case["case_name"]: case for case in payload["tamper_cases"]}


def test_clean_live_write_blockade_report_validates_pass(smoke_payload):
    assert smoke_payload["clean_blockade_verdict"] == "PASS"
    assert smoke_payload["clean_blockade_still_passes"] is True


def test_malformed_json_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["malformed_json"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "malformed_json"


def test_missing_required_report_field_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["missing_required_report_field"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "missing_required_report_field"


def test_source_staging_manifest_hash_mismatch_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["source_staging_manifest_hash_mismatch"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "source_staging_manifest_hash_mismatch"


def test_clean_staging_invalid_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["clean_staging_invalid"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "clean_staging_invalid"


def test_staging_tamper_evidence_failed_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["staging_tamper_evidence_failed"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "staging_tamper_evidence_failed"


def test_live_memory_write_allowed_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["live_memory_write_allowed"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "live_memory_write_allowed"


def test_live_memory_write_not_denied_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["live_memory_write_not_denied"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "live_memory_write_not_denied"


def test_live_memory_write_attempted_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["live_memory_write_attempted"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "live_memory_write_attempted"


def test_live_memory_write_performed_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["live_memory_write_performed"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "live_memory_write_performed"


def test_live_memory_write_path_created_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["live_memory_write_path_created"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "live_memory_write_path_created"


def test_vector_db_write_allowed_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["vector_db_write_allowed"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "vector_db_write_allowed"


def test_vector_db_write_not_denied_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["vector_db_write_not_denied"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "vector_db_write_not_denied"


def test_vector_db_write_attempted_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["vector_db_write_attempted"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "vector_db_write_attempted"


def test_vector_db_write_performed_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["vector_db_write_performed"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "vector_db_write_performed"


def test_vector_db_write_path_created_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["vector_db_write_path_created"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "vector_db_write_path_created"


def test_runtime_memory_files_created_nonzero_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["runtime_memory_files_created_nonzero"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "runtime_memory_files_created_nonzero"


def test_vector_db_files_created_nonzero_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["vector_db_files_created_nonzero"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "vector_db_files_created_nonzero"


def test_ready_for_live_memory_write_true_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["ready_for_live_memory_write_true"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "ready_for_live_memory_write_true"


def test_future_live_write_allowed_true_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["future_live_write_allowed_true"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "future_live_write_allowed_true"


def test_future_milestone_not_required_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["future_milestone_not_required"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "future_milestone_not_required"


def test_missing_denial_reason_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["missing_denial_reason"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "missing_denial_reason"


def test_unsafe_metadata_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["unsafe_metadata"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "unsafe_metadata"


def test_every_tamper_case_is_detected(smoke_payload):
    cases = _cases_by_name(smoke_payload)
    assert set(cases) == set(REQUIRED_TAMPER_CASES)
    assert smoke_payload["all_tamper_cases_detected"] is True
    for name in REQUIRED_TAMPER_CASES:
        assert cases[name]["detected"] is True
        assert cases[name]["actual_verdict"] == "FAIL"


def test_json_report_contains_verdict_pass(smoke_payload):
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []


def test_json_report_includes_tamper_case_names(smoke_payload):
    names = [case["case_name"] for case in smoke_payload["tamper_cases"]]
    assert names == list(REQUIRED_TAMPER_CASES)
    assert smoke_payload["tamper_case_count"] == len(REQUIRED_TAMPER_CASES)


def test_json_report_confirms_all_tamper_cases_detected(smoke_payload):
    assert smoke_payload["all_tamper_cases_detected"] is True
    assert set(smoke_payload["detected_error_types"]) == set(REQUIRED_TAMPER_CASES)


def test_json_report_confirms_model_called_false(smoke_payload):
    assert smoke_payload["model_called"] is False


def test_json_report_confirms_embeddings_used_false(smoke_payload):
    assert smoke_payload["embeddings_used"] is False


def test_json_report_confirms_live_memory_written_false(smoke_payload):
    assert smoke_payload["live_memory_written"] is False


def test_json_report_confirms_live_vector_db_written_false(smoke_payload):
    assert smoke_payload["live_vector_db_written"] is False


def test_json_report_confirms_account_api_network_accessed_false(smoke_payload):
    assert smoke_payload["account_api_network_accessed"] is False


def test_json_report_confirms_autonomy_enabled_false(smoke_payload):
    assert smoke_payload["autonomy_enabled"] is False


def test_json_report_required_fields_present(smoke_payload):
    required_fields = {
        "verdict",
        "workspace",
        "clean_blockade_verdict",
        "tamper_case_count",
        "tamper_cases",
        "all_tamper_cases_detected",
        "detected_error_types",
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
    assert required_fields.issubset(smoke_payload)
    assert smoke_payload["operator_required"] is True
    assert smoke_payload["dry_run"] is True
    assert smoke_payload["local_only"] is True
    _assert_safety_flags_false(smoke_payload)
    for case in smoke_payload["tamper_cases"]:
        assert {
            "case_name",
            "expected_verdict",
            "actual_verdict",
            "detected",
            "detected_error_type",
            "details",
        }.issubset(case)


def test_checker_clean_blockade_report_passes(tmp_path):
    report_path = _write_json(tmp_path / "clean.json", _valid_report(tmp_path))
    verdict, errors = SMOKE.audit_live_write_blockade_report(report_path)
    assert verdict == "PASS"
    assert errors == []


def test_checker_detects_malformed_json(tmp_path):
    report_path = tmp_path / "malformed.json"
    report_path.write_text("{ not valid json\n", encoding="utf-8", newline="\n")
    verdict, errors = SMOKE.audit_live_write_blockade_report(report_path)
    assert verdict == "FAIL"
    assert any("malformed_json" in error for error in errors)


def test_checker_detects_missing_required_report_field(tmp_path):
    report = _valid_report(tmp_path)
    report.pop("workspace")
    report_path = _write_json(tmp_path / "missing_field.json", report)
    verdict, errors = SMOKE.audit_live_write_blockade_report(report_path)
    assert verdict == "FAIL"
    assert any("missing_required_report_field" in error for error in errors)


def test_checker_detects_source_staging_manifest_hash_mismatch(tmp_path):
    report = _valid_report(tmp_path, source_staging_manifest_sha256="0" * 64)
    report_path = _write_json(tmp_path / "hash_mismatch.json", report)
    verdict, errors = SMOKE.audit_live_write_blockade_report(report_path)
    assert verdict == "FAIL"
    assert any("source_staging_manifest_hash_mismatch" in error for error in errors)


def test_checker_detects_unsafe_metadata(tmp_path):
    report = _valid_report(tmp_path, dry_run=False, autonomy_enabled=True)
    report_path = _write_json(tmp_path / "unsafe.json", report)
    verdict, errors = SMOKE.audit_live_write_blockade_report(report_path)
    assert verdict == "FAIL"
    assert any("unsafe_metadata" in error for error in errors)


def test_live_write_blockade_tamper_script_has_no_network_ui_or_route_behavior():
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    forbidden_tokens = (
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
    for token in forbidden_tokens:
        assert token not in script


def test_live_write_blockade_tamper_script_refuses_repository_root_workspace():
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
