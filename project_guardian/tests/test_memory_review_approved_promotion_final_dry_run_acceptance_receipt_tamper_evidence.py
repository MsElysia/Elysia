# project_guardian/tests/test_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence.py

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke.py"
)
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


def _load_smoke_module():
    module_name = (
        "run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke"
    )
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
        check=False,
        capture_output=True,
        text=True,
    )
    start = result.stdout.find("{")
    if start < 0:
        raise AssertionError(
            "tamper evidence smoke did not emit JSON\n"
            f"returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    payload = json.loads(result.stdout[start:])
    if result.returncode != 0 and payload.get("verdict") != "FAIL":
        raise AssertionError(
            "tamper evidence smoke failed without FAIL verdict\n"
            f"returncode={result.returncode}\nstderr={result.stderr}"
        )
    return payload


@pytest.fixture(scope="module")
def smoke_payload() -> dict:
    base_dir = Path(tempfile.mkdtemp(prefix="elysia_fdrarte_"))
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


def _write_source_file(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return SMOKE._sha256_file(path)


def _valid_receipt(tmp_path: Path) -> Dict[str, Any]:
    workspace = tmp_path / "ws"
    packet_path = (
        workspace / "approved_promotion_final_readiness_packet" / "final_readiness_packet.json"
    )
    packet_tamper_path = (
        workspace
        / "approved_promotion_final_readiness_packet_tamper_evidence"
        / "final_readiness_packet_tamper_evidence.json"
    )
    gate_path = (
        workspace
        / "approved_promotion_final_readiness_operator_acceptance_gate"
        / "operator_acceptance_gate.json"
    )
    gate_tamper_path = (
        workspace
        / "approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence"
        / "operator_acceptance_gate_tamper_evidence.json"
    )
    receipt_dir = workspace / "approved_promotion_final_dry_run_acceptance_receipt"
    receipt_json = receipt_dir / "final_dry_run_acceptance_receipt.json"
    receipt_readme = receipt_dir / "FINAL_DRY_RUN_ACCEPTANCE_RECEIPT.md"
    packet_hash = _write_source_file(packet_path, '{"verdict":"PASS"}')
    packet_tamper_hash = _write_source_file(packet_tamper_path, '{"verdict":"PASS"}')
    gate_hash = _write_source_file(gate_path, '{"verdict":"PASS"}')
    gate_tamper_hash = _write_source_file(gate_tamper_path, '{"verdict":"PASS"}')
    readme_hash = _write_source_file(receipt_readme, "receipt")
    return {
        "verdict": "PASS",
        "workspace": str(workspace),
        "receipt_path": str(receipt_dir),
        "receipt_json_path": str(receipt_json),
        "receipt_json_valid": True,
        "receipt_readme_path": str(receipt_readme),
        "receipt_readme_sha256": readme_hash,
        "operator_acceptance_phrase": SMOKE.ACCEPTANCE_PHRASE,
        "operator_acceptance_phrase_valid": True,
        "accepted_checkpoint_tag": SMOKE.ACCEPTED_CHECKPOINT_TAG,
        "accepted_checkpoint_hash": SMOKE.ACCEPTED_CHECKPOINT_HASH,
        "accepted_checkpoint_message": "feat(local): add approved promotion final acceptance gate tamper evidence",
        "source_final_readiness_packet_sha256": packet_hash,
        "source_final_readiness_packet_tamper_evidence_sha256": packet_tamper_hash,
        "source_operator_acceptance_gate_sha256": gate_hash,
        "source_operator_acceptance_gate_tamper_evidence_sha256": gate_tamper_hash,
        "final_readiness_packet_verdict": "PASS",
        "final_readiness_packet_tamper_evidence_verdict": "PASS",
        "operator_acceptance_gate_verdict": "PASS",
        "operator_acceptance_gate_tamper_evidence_verdict": "PASS",
        "accepted_for_final_dry_run_readiness": True,
        "accepted_for_live_memory_write": False,
        "accepted_for_vector_db_write": False,
        "ready_for_future_live_write_design": False,
        "requires_separate_live_write_campaign": True,
        "requires_separate_operator_approval_for_live_write": True,
        "live_memory_write_allowed": False,
        "vector_db_write_allowed": False,
        "live_write_blocked_reason": "blocked live",
        "vector_db_write_blocked_reason": "blocked vector",
        "operator_next_steps": list(SMOKE.OPERATOR_NEXT_STEPS),
        "dry_run": True,
        "local_only": True,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "live_vector_db_written": False,
        "account_api_network_accessed": False,
        "autonomy_enabled": False,
        "errors": [],
        "artifact_paths": {
            "packet_json": str(packet_path),
            "packet_tamper_json": str(packet_tamper_path),
            "gate_json": str(gate_path),
            "gate_tamper_json": str(gate_tamper_path),
        },
    }


def _write_receipt(tmp_path: Path, report: Dict[str, Any]) -> Path:
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _cases(payload: dict) -> Dict[str, dict]:
    return {case["case_name"]: case for case in payload["tamper_cases"]}


def test_clean_receipt_validates_pass(smoke_payload):
    assert smoke_payload["clean_receipt_verdict"] == "PASS"
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []
    _assert_safety_flags_false(smoke_payload)


def test_malformed_json_fails(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ this is not valid json\n", encoding="utf-8")
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(path)
    assert verdict == "FAIL"
    assert any("malformed_json" in error for error in errors)


def test_missing_required_receipt_field_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report.pop("workspace")
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("missing_required_receipt_field" in error for error in errors)


def test_operator_phrase_change_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["operator_acceptance_phrase"] = "WRONG_PHRASE"
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("operator_acceptance_phrase_changed" in error for error in errors)


def test_operator_phrase_invalid_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["operator_acceptance_phrase_valid"] = False
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("operator_acceptance_phrase_valid_false" in error for error in errors)


def test_checkpoint_tag_change_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["accepted_checkpoint_tag"] = "wrong_tag"
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("accepted_checkpoint_tag_changed" in error for error in errors)


def test_checkpoint_hash_change_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["accepted_checkpoint_hash"] = "0" * 40
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("accepted_checkpoint_hash_changed" in error for error in errors)


@pytest.mark.parametrize(
    "field_name,token",
    [
        ("source_final_readiness_packet_sha256", "source_final_readiness_packet_hash_mismatch"),
        (
            "source_final_readiness_packet_tamper_evidence_sha256",
            "source_final_readiness_packet_tamper_hash_mismatch",
        ),
        ("source_operator_acceptance_gate_sha256", "source_operator_acceptance_gate_hash_mismatch"),
        (
            "source_operator_acceptance_gate_tamper_evidence_sha256",
            "source_operator_acceptance_gate_tamper_hash_mismatch",
        ),
    ],
)
def test_source_hash_mismatches_fail(tmp_path, field_name, token):
    report = _valid_receipt(tmp_path)
    report[field_name] = "0" * 64
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any(token in error for error in errors)


@pytest.mark.parametrize(
    "field_name,token",
    [
        ("final_readiness_packet_verdict", "final_readiness_packet_verdict_not_pass"),
        (
            "final_readiness_packet_tamper_evidence_verdict",
            "final_readiness_tamper_evidence_verdict_not_pass",
        ),
        ("operator_acceptance_gate_verdict", "operator_acceptance_gate_verdict_not_pass"),
        (
            "operator_acceptance_gate_tamper_evidence_verdict",
            "operator_acceptance_gate_tamper_evidence_verdict_not_pass",
        ),
    ],
)
def test_upstream_verdict_changed_from_pass_fails(tmp_path, field_name, token):
    report = _valid_receipt(tmp_path)
    report[field_name] = "FAIL"
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any(token in error for error in errors)


@pytest.mark.parametrize(
    "field_name,value,token",
    [
        ("accepted_for_final_dry_run_readiness", False, "accepted_for_final_dry_run_readiness_false"),
        ("accepted_for_live_memory_write", True, "accepted_for_live_memory_write_true"),
        ("accepted_for_vector_db_write", True, "accepted_for_vector_db_write_true"),
        ("ready_for_future_live_write_design", True, "ready_for_future_live_write_design_true"),
        (
            "requires_separate_live_write_campaign",
            False,
            "requires_separate_live_write_campaign_false",
        ),
        (
            "requires_separate_operator_approval_for_live_write",
            False,
            "requires_separate_operator_approval_for_live_write_false",
        ),
        ("live_memory_write_allowed", True, "live_memory_write_allowed_true"),
        ("vector_db_write_allowed", True, "vector_db_write_allowed_true"),
        ("dry_run", False, "dry_run_false"),
        ("local_only", False, "local_only_false"),
    ],
)
def test_authorization_and_mode_flag_tampers_fail(tmp_path, field_name, value, token):
    report = _valid_receipt(tmp_path)
    report[field_name] = value
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any(token in error for error in errors)


def test_missing_live_write_blocked_reason_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["live_write_blocked_reason"] = ""
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("live_write_blocked_reason_missing" in error for error in errors)


def test_missing_vector_db_blocked_reason_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["vector_db_write_blocked_reason"] = ""
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("vector_db_write_blocked_reason_missing" in error for error in errors)


def test_missing_operator_next_steps_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["operator_next_steps"] = []
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    assert any("operator_next_steps_missing" in error for error in errors)


def test_unsafe_metadata_fails(tmp_path):
    report = _valid_receipt(tmp_path)
    report["model_called"] = True
    report["embeddings_used"] = True
    report["live_memory_written"] = True
    report["live_vector_db_written"] = True
    report["account_api_network_accessed"] = True
    report["autonomy_enabled"] = True
    verdict, errors = SMOKE.audit_final_dry_run_acceptance_receipt(_write_receipt(tmp_path, report))
    assert verdict == "FAIL"
    joined = " ".join(errors)
    for token in (
        "model_called_true",
        "embeddings_used_true",
        "live_memory_written_true",
        "live_vector_db_written_true",
        "account_api_network_accessed_true",
        "autonomy_enabled_true",
    ):
        assert token in joined


def test_all_tamper_cases_are_detected(smoke_payload):
    cases = _cases(smoke_payload)
    assert list(cases) == list(SMOKE.REQUIRED_TAMPER_CASES)
    assert smoke_payload["tamper_case_count"] == len(SMOKE.REQUIRED_TAMPER_CASES)
    assert smoke_payload["all_tamper_cases_detected"] is True
    for name, case in cases.items():
        assert case["expected_verdict"] == "FAIL"
        assert case["actual_verdict"] == "FAIL"
        assert case["detected"] is True
        assert case["detected_error_type"]
        assert name in case["detected_error_type"] or any(
            name in detail for detail in case["details"]
        )


def test_json_report_contains_pass_contract(smoke_payload):
    required_fields = {
        "verdict",
        "workspace",
        "clean_receipt_verdict",
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
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["clean_receipt_verdict"] == "PASS"
    assert smoke_payload["operator_required"] is True
    assert smoke_payload["dry_run"] is True
    assert smoke_payload["local_only"] is True
    _assert_safety_flags_false(smoke_payload)


def test_json_report_includes_all_tamper_case_names(smoke_payload):
    names = [case["case_name"] for case in smoke_payload["tamper_cases"]]
    assert names == list(SMOKE.REQUIRED_TAMPER_CASES)
    for name in SMOKE.REQUIRED_TAMPER_CASES:
        assert name in smoke_payload["detected_error_types"] or any(
            case["detected"] and case["case_name"] == name
            for case in smoke_payload["tamper_cases"]
        )


def test_json_report_confirms_safety_flags_false(smoke_payload):
    assert smoke_payload["model_called"] is False
    assert smoke_payload["embeddings_used"] is False
    assert smoke_payload["live_memory_written"] is False
    assert smoke_payload["live_vector_db_written"] is False
    assert smoke_payload["account_api_network_accessed"] is False
    assert smoke_payload["autonomy_enabled"] is False


def test_no_live_runtime_memory_or_vector_db_path_is_written(smoke_payload):
    workspace = Path(smoke_payload["workspace"])
    assert workspace.is_dir()
    assert "forbidden_live_writes" not in smoke_payload
    assert not (workspace / "forbidden_live_writes").exists()
    assert list(workspace.rglob("runtime_memory.jsonl")) == []
    assert list(workspace.rglob("vector_db.index")) == []
    dumped = json.dumps(smoke_payload)
    assert "forbidden_live_writes" not in dumped


def test_script_has_no_network_ui_or_route_behavior():
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    for token in FORBIDDEN_SCRIPT_TOKENS:
        assert token not in script
    assert "POST" not in script


def test_script_refuses_repository_root_workspace():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", "--base-dir", str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    start = result.stdout.find("{")
    payload = json.loads(result.stdout[start:])
    assert payload["verdict"] == "FAIL"
    assert "repository root" in payload["errors"][0]
