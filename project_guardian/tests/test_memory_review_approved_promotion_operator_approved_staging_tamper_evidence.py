# project_guardian/tests/test_memory_review_approved_promotion_operator_approved_staging_tamper_evidence.py

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
    / "run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke.py"
)
APPROVAL_TOKEN_PHRASE = "APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY"
REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_manifest_field",
    "missing_required_staged_item_field",
    "promoted_text_hash_mismatch",
    "promotion_manifest_hash_mismatch",
    "operator_handoff_hash_mismatch",
    "approval_gate_hash_mismatch",
    "rejected_candidate_included",
    "staging_item_count_mismatch",
    "unsafe_metadata",
    "live_write_unblocked",
)


def _load_smoke_module():
    module_name = "run_memory_review_approved_promotion_operator_approved_staging_tamper_evidence_smoke"
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


def _valid_item(handoff_hash: str, gate_hash: str, **overrides: Any) -> Dict[str, Any]:
    promoted_text = overrides.pop(
        "promoted_text",
        "Approve branch fixture: kitchen cabinet measurements are ready.",
    )
    item = {
        "candidate_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "decision_id": "0123456789abcdef0123456789abcdef",
        "decision_type": "approved",
        "source_type": "transcription",
        "promoted_text": promoted_text,
        "promoted_text_sha256": SMOKE._sha256_text(promoted_text),
        "candidate_sha256": SMOKE._sha256_text(promoted_text),
        "source_handoff_sha256": handoff_hash,
        "source_approval_gate_sha256": gate_hash,
        "ready_for_operator_approved_staging": True,
        "ready_for_live_memory_write": False,
        "requires_explicit_operator_approval": True,
        "live_memory_written": False,
        "live_vector_db_written": False,
    }
    item.update(overrides)
    return item


def _valid_manifest(tmp_path: Path, **overrides: Any) -> Dict[str, Any]:
    promotion_path = tmp_path / "promotion_manifest.json"
    handoff_path = tmp_path / "operator_handoff.json"
    gate_path = tmp_path / "operator_approval_gate.json"
    _write_json(promotion_path, {"verdict": "PASS", "kind": "promotion"})
    _write_json(handoff_path, {"verdict": "PASS", "kind": "handoff"})
    _write_json(gate_path, {"verdict": "PASS", "kind": "approval_gate"})
    promotion_hash = SMOKE._promotion_manifest_content_hash(promotion_path)
    handoff_hash = SMOKE._sha256_file(handoff_path)
    gate_hash = SMOKE._sha256_file(gate_path)
    approved = _valid_item(handoff_hash, gate_hash)
    edited_text = (
        "Edited approved memory: kitchen countertop measurement is 42 inches "
        "and the revised tile color is blue."
    )
    edited = _valid_item(
        handoff_hash,
        gate_hash,
        candidate_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        decision_id="fedcba9876543210fedcba9876543210",
        decision_type="edited",
        promoted_text=edited_text,
    )
    manifest = {
        "verdict": "PASS",
        "workspace": str(tmp_path),
        "staging_path": str(tmp_path / "approved_promotion_operator_approved_staging"),
        "operator_approved_staging_manifest_path": str(tmp_path / "operator_approved_staging_manifest.json"),
        "operator_approved_staging_manifest_valid_json": True,
        "promotion_bundle_path": str(tmp_path / "approved_promotion_bundle"),
        "promotion_manifest_path": str(promotion_path),
        "promotion_manifest_sha256": promotion_hash,
        "operator_handoff_path": str(handoff_path),
        "operator_handoff_sha256": handoff_hash,
        "operator_approval_gate_path": str(gate_path),
        "operator_approval_gate_sha256": gate_hash,
        "approval_token_phrase": APPROVAL_TOKEN_PHRASE,
        "approval_gate_verdict": "PASS",
        "ready_for_operator_approved_staging": True,
        "ready_for_live_memory_write": False,
        "future_live_write_allowed": False,
        "requires_explicit_operator_approval": True,
        "operator_approval_valid": True,
        "tamper_evidence_verdict": "PASS",
        "all_tamper_cases_detected": True,
        "promotion_item_count": 2,
        "approved_candidate_count": 1,
        "edited_candidate_count": 1,
        "excluded_rejected_count": 1,
        "staged_items": [approved, edited],
        "staging_readme_path": str(tmp_path / "STAGING_README.md"),
        "staging_readme_sha256": "c" * 64,
        "live_write_blocked_reason": "Live memory writing remains blocked.",
        "staging_paths_inside_workspace": True,
        "operator_required": True,
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
    manifest.update(overrides)
    return manifest


def _cases_by_name(payload: dict) -> Dict[str, dict]:
    return {case["case_name"]: case for case in payload["tamper_cases"]}


def test_clean_operator_approved_staging_package_validates_pass(smoke_payload):
    assert smoke_payload["clean_staging_verdict"] == "PASS"
    assert smoke_payload["clean_staging_still_passes"] is True


def test_malformed_json_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["malformed_json"]
    assert case["expected_verdict"] == "FAIL"
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "malformed_json"


def test_missing_required_manifest_field_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["missing_required_manifest_field"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "missing_required_manifest_field"


def test_missing_required_staged_item_field_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["missing_required_staged_item_field"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "missing_required_staged_item_field"


def test_promoted_text_hash_mismatch_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["promoted_text_hash_mismatch"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "promoted_text_hash_mismatch"


def test_promotion_manifest_hash_mismatch_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["promotion_manifest_hash_mismatch"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "promotion_manifest_hash_mismatch"


def test_operator_handoff_hash_mismatch_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["operator_handoff_hash_mismatch"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "operator_handoff_hash_mismatch"


def test_approval_gate_hash_mismatch_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["approval_gate_hash_mismatch"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "approval_gate_hash_mismatch"


def test_rejected_candidate_included_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["rejected_candidate_included"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "rejected_candidate_included"


def test_staging_item_count_mismatch_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["staging_item_count_mismatch"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "staging_item_count_mismatch"


def test_unsafe_metadata_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["unsafe_metadata"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "unsafe_metadata"


def test_live_write_unblocked_validates_fail(smoke_payload):
    case = _cases_by_name(smoke_payload)["live_write_unblocked"]
    assert case["actual_verdict"] == "FAIL"
    assert case["detected"] is True
    assert case["detected_error_type"] == "live_write_unblocked"


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
        "clean_staging_verdict",
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


def test_checker_clean_staging_manifest_passes(tmp_path):
    manifest_path = _write_json(tmp_path / "clean.json", _valid_manifest(tmp_path))
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "PASS"
    assert errors == []


def test_checker_detects_malformed_json(tmp_path):
    manifest_path = tmp_path / "malformed.json"
    manifest_path.write_text("{ not valid json\n", encoding="utf-8", newline="\n")
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("malformed_json" in error for error in errors)


def test_checker_detects_missing_required_manifest_field(tmp_path):
    manifest = _valid_manifest(tmp_path)
    manifest.pop("workspace")
    manifest_path = _write_json(tmp_path / "missing_manifest_field.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("missing_required_manifest_field" in error for error in errors)


def test_checker_detects_missing_required_staged_item_field(tmp_path):
    manifest = _valid_manifest(tmp_path)
    manifest["staged_items"][0].pop("promoted_text")
    manifest_path = _write_json(tmp_path / "missing_item_field.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("missing_required_staged_item_field" in error for error in errors)


def test_checker_detects_promoted_text_hash_mismatch(tmp_path):
    manifest = _valid_manifest(tmp_path)
    manifest["staged_items"][0]["promoted_text_sha256"] = "0" * 64
    manifest_path = _write_json(tmp_path / "promoted_hash.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("promoted_text_hash_mismatch" in error for error in errors)


def test_checker_detects_promotion_manifest_hash_mismatch(tmp_path):
    manifest = _valid_manifest(tmp_path)
    manifest["promotion_manifest_sha256"] = "0" * 64
    manifest_path = _write_json(tmp_path / "promotion_hash.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("promotion_manifest_hash_mismatch" in error for error in errors)


def test_checker_detects_operator_handoff_hash_mismatch(tmp_path):
    manifest = _valid_manifest(tmp_path)
    manifest["operator_handoff_sha256"] = "0" * 64
    manifest_path = _write_json(tmp_path / "handoff_hash.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("operator_handoff_hash_mismatch" in error for error in errors)


def test_checker_detects_approval_gate_hash_mismatch(tmp_path):
    manifest = _valid_manifest(tmp_path)
    manifest["operator_approval_gate_sha256"] = "0" * 64
    manifest_path = _write_json(tmp_path / "gate_hash.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("approval_gate_hash_mismatch" in error for error in errors)


def test_checker_detects_rejected_candidate_included(tmp_path):
    manifest = _valid_manifest(tmp_path)
    rejected = dict(manifest["staged_items"][0])
    rejected["candidate_id"] = "cccccccccccccccccccccccc"
    rejected["decision_type"] = "rejected"
    manifest["staged_items"].append(rejected)
    manifest["promotion_item_count"] = 3
    manifest_path = _write_json(tmp_path / "rejected.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("rejected_candidate_included" in error for error in errors)


def test_checker_detects_staging_item_count_mismatch(tmp_path):
    manifest = _valid_manifest(tmp_path, promotion_item_count=3)
    manifest_path = _write_json(tmp_path / "count_mismatch.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("staging_item_count_mismatch" in error for error in errors)


def test_checker_detects_unsafe_metadata(tmp_path):
    manifest = _valid_manifest(tmp_path, dry_run=False, live_memory_written=True)
    manifest_path = _write_json(tmp_path / "unsafe.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("unsafe_metadata" in error for error in errors)


def test_checker_detects_live_write_unblocked(tmp_path):
    manifest = _valid_manifest(
        tmp_path,
        ready_for_live_memory_write=True,
        future_live_write_allowed=True,
    )
    manifest_path = _write_json(tmp_path / "live_write.json", manifest)
    verdict, errors = SMOKE.audit_operator_approved_staging_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("live_write_unblocked" in error for error in errors)


def test_staging_tamper_script_has_no_network_ui_or_route_behavior():
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


def test_staging_tamper_script_refuses_repository_root_workspace():
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
