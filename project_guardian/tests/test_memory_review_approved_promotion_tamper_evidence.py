# project_guardian/tests/test_memory_review_approved_promotion_tamper_evidence.py

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
    REPO_ROOT / "scripts" / "run_memory_review_approved_promotion_tamper_evidence_smoke.py"
)


def _load_smoke_module():
    module_name = "run_memory_review_approved_promotion_tamper_evidence_smoke"
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


def _valid_item(**overrides: Any) -> Dict[str, Any]:
    original_text = "Approve branch fixture: kitchen cabinet measurements are ready."
    promoted_text = overrides.pop("promoted_text", original_text)
    item = {
        "candidate_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "decision_id": "0123456789abcdef0123456789abcdef",
        "decision_type": "approved",
        "source_type": "transcription",
        "original_text": original_text,
        "promoted_text": promoted_text,
        "text_was_edited": False,
        "source_queue_path": "review_queue.jsonl",
        "review_decision_log_path": "review_decisions.jsonl",
        "candidate_sha256": SMOKE._sha256_text(original_text),
        "promoted_text_sha256": SMOKE._sha256_text(promoted_text),
        "ready_for_future_promotion": True,
        "live_memory_written": False,
        "live_vector_db_written": False,
        "operator_required": True,
    }
    item.update(overrides)
    return item


def _valid_manifest(**overrides: Any) -> Dict[str, Any]:
    item = _valid_item()
    manifest = {
        "verdict": "PASS",
        "workspace": "temp-workspace",
        "bundle_path": "temp-workspace/approved_promotion_bundle",
        "approved_candidate_count": 1,
        "edited_candidate_count": 0,
        "rejected_candidate_count": 1,
        "promotion_item_count": 1,
        "excluded_rejected_count": 1,
        "promotion_items": [item],
        "source_queue_path": "review_queue.jsonl",
        "review_decisions_log_path": "review_decisions.jsonl",
        "review_decisions_log_sha256": "f" * 64,
        "candidate_source_hashes": {
            item["candidate_id"]: item["candidate_sha256"],
        },
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
    return SMOKE._attach_manifest_hash(manifest)


def _write_manifest(path: Path, manifest: Dict[str, Any], *, refresh_hash: bool = True) -> Path:
    payload = SMOKE._attach_manifest_hash(manifest) if refresh_hash else manifest
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def test_approved_promotion_tamper_smoke_json_cli_passes(smoke_payload):
    payload = smoke_payload

    assert payload["verdict"] == "PASS"
    assert payload["clean_manifest_verdict"] == "PASS"
    assert payload["clean_manifest_still_passes"] is True
    assert payload["tampered_cases_run"] == 9

    assert payload["malformed_json_detected"] is True
    assert payload["missing_required_manifest_field_detected"] is True
    assert payload["missing_required_promotion_item_field_detected"] is True
    assert payload["promoted_text_hash_mismatch_detected"] is True
    assert payload["candidate_hash_mismatch_detected"] is True
    assert payload["rejected_candidate_included_detected"] is True
    assert payload["promotion_item_count_mismatch_detected"] is True
    assert payload["unsafe_metadata_detected"] is True
    assert payload["manifest_hash_mismatch_detected"] is True
    assert payload["specific_errors_present"] is True
    assert payload["tamper_paths_inside_workspace"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_approved_promotion_tamper_json_contract_fields_present(smoke_payload):
    payload = smoke_payload
    required_fields = {
        "verdict",
        "workspace",
        "clean_manifest_path",
        "clean_manifest_verdict",
        "clean_manifest_still_passes",
        "tampered_cases_run",
        "malformed_json_detected",
        "missing_required_manifest_field_detected",
        "missing_required_promotion_item_field_detected",
        "promoted_text_hash_mismatch_detected",
        "candidate_hash_mismatch_detected",
        "rejected_candidate_included_detected",
        "promotion_item_count_mismatch_detected",
        "unsafe_metadata_detected",
        "manifest_hash_mismatch_detected",
        "manifest_hash_validation_present",
        "specific_errors_present",
        "tamper_paths_inside_workspace",
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
        "errors",
        "cases",
        "artifact_paths",
    }
    assert required_fields.issubset(payload)
    _assert_safety_flags_false(payload)


def test_approved_promotion_tamper_each_case_returns_fail_with_specific_token(smoke_payload):
    cases = {case["name"]: case for case in smoke_payload["cases"]}
    for name in (
        "malformed_json",
        "missing_required_manifest_field",
        "missing_required_promotion_item_field",
        "promoted_text_hash_mismatch",
        "candidate_hash_mismatch",
        "rejected_candidate_included",
        "promotion_item_count_mismatch",
        "unsafe_metadata",
        "manifest_hash_mismatch",
    ):
        assert cases[name]["verdict"] == "FAIL"
        assert cases[name]["token_found"] is True
        assert any(cases[name]["expected_token"] in err for err in cases[name]["errors"])


def test_checker_clean_promotion_manifest_passes(tmp_path):
    manifest_path = _write_manifest(tmp_path / "clean.json", _valid_manifest())
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "PASS"
    assert errors == []


def test_checker_detects_malformed_json(tmp_path):
    manifest_path = tmp_path / "malformed.json"
    manifest_path.write_text("{ not valid json\n", encoding="utf-8", newline="\n")
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("malformed_json" in error for error in errors)


def test_checker_detects_missing_required_manifest_field(tmp_path):
    manifest = _valid_manifest()
    manifest.pop("workspace")
    manifest_path = _write_manifest(tmp_path / "missing_manifest_field.json", manifest)
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("missing_required_manifest_field" in error for error in errors)


def test_checker_detects_missing_required_promotion_item_field(tmp_path):
    manifest = _valid_manifest()
    manifest["promotion_items"][0].pop("promoted_text")
    manifest_path = _write_manifest(tmp_path / "missing_item_field.json", manifest)
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("missing_required_promotion_item_field" in error for error in errors)


def test_checker_detects_promoted_text_hash_mismatch(tmp_path):
    manifest = _valid_manifest()
    manifest["promotion_items"][0]["promoted_text_sha256"] = "0" * 64
    manifest_path = _write_manifest(tmp_path / "promoted_hash.json", manifest)
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("promoted_text_hash_mismatch" in error for error in errors)


def test_checker_detects_candidate_hash_mismatch(tmp_path):
    manifest = _valid_manifest()
    manifest["promotion_items"][0]["candidate_sha256"] = "0" * 64
    manifest_path = _write_manifest(tmp_path / "candidate_hash.json", manifest)
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("candidate_hash_mismatch" in error for error in errors)


def test_checker_detects_rejected_candidate_included(tmp_path):
    manifest = _valid_manifest()
    rejected_item = _valid_item(
        candidate_id="bbbbbbbbbbbbbbbbbbbbbbbb",
        decision_id="rejecteddecision0123456789ab",
        decision_type="rejected",
    )
    manifest["promotion_items"].append(rejected_item)
    manifest["promotion_item_count"] = 2
    manifest["candidate_source_hashes"][rejected_item["candidate_id"]] = rejected_item[
        "candidate_sha256"
    ]
    manifest_path = _write_manifest(tmp_path / "rejected.json", manifest)
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("rejected_candidate_included" in error for error in errors)


def test_checker_detects_promotion_item_count_mismatch(tmp_path):
    manifest = _valid_manifest(promotion_item_count=2)
    manifest_path = _write_manifest(tmp_path / "count_mismatch.json", manifest)
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("promotion_item_count_mismatch" in error for error in errors)


def test_checker_detects_unsafe_metadata(tmp_path):
    manifest = _valid_manifest(live_memory_written=True)
    manifest_path = _write_manifest(tmp_path / "unsafe.json", manifest)
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("unsafe_metadata" in error for error in errors)


def test_checker_detects_manifest_hash_mismatch(tmp_path):
    manifest = _valid_manifest()
    manifest["promotion_manifest_sha256"] = "0" * 64
    manifest_path = _write_manifest(
        tmp_path / "manifest_hash.json",
        manifest,
        refresh_hash=False,
    )
    verdict, errors = SMOKE.audit_promotion_manifest(manifest_path)
    assert verdict == "FAIL"
    assert any("manifest_hash_mismatch" in error for error in errors)


def test_approved_promotion_tamper_script_has_no_network_ui_or_route_behavior():
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


def test_approved_promotion_tamper_script_refuses_repository_root_workspace():
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
