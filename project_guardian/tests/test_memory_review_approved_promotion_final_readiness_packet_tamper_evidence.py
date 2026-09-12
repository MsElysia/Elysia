# project_guardian/tests/test_memory_review_approved_promotion_final_readiness_packet_tamper_evidence.py

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
    / "run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke.py"
)
REQUIRED_TAMPER_CASES = (
    "malformed_json",
    "missing_required_packet_field",
    "packet_readme_hash_mismatch",
    "source_bundle_hash_mismatch",
    "source_promotion_manifest_hash_mismatch",
    "source_operator_handoff_hash_mismatch",
    "source_approval_gate_hash_mismatch",
    "source_staging_manifest_hash_mismatch",
    "source_staging_tamper_evidence_hash_mismatch",
    "source_live_write_blockade_hash_mismatch",
    "source_live_write_blockade_tamper_evidence_hash_mismatch",
    "approval_token_phrase_missing",
    "approved_item_removed",
    "edited_item_removed",
    "edited_promoted_text_changed",
    "rejected_item_included",
    "promotion_item_count_mismatch",
    "excluded_rejected_count_mismatch",
    "safety_chain_missing_stage",
    "safety_chain_stage_failed",
    "ready_for_operator_review_false",
    "ready_for_operator_approved_staging_false",
    "ready_for_live_memory_write_true",
    "future_live_write_allowed_true",
    "requires_explicit_operator_approval_false",
    "requires_future_live_write_milestone_false",
    "live_write_blocked_reason_missing",
    "vector_db_write_blocked_reason_missing",
    "operator_next_steps_missing_future_milestone",
    "unsafe_metadata",
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
        "run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke"
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


def _write_source_file(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return SMOKE._sha256_file(path)


def _valid_packet(tmp_path: Path) -> Dict[str, Any]:
    workspace = tmp_path / "ws"
    readme = workspace / "approved_promotion_final_readiness_packet" / "FINAL_READINESS_README.md"
    bundle_readme = workspace / "approved_promotion_bundle" / "README.md"
    promotion_manifest = workspace / "approved_promotion_bundle" / "promotion_manifest.json"
    handoff = workspace / "approved_promotion_operator_handoff" / "operator_handoff.json"
    gate = (
        workspace
        / "approved_promotion_operator_approval_gate"
        / "operator_approval_gate.json"
    )
    staging = (
        workspace
        / "approved_promotion_operator_approved_staging"
        / "operator_approved_staging_manifest.json"
    )
    staging_receipt = workspace / "ap_ste_receipt" / "staging_tamper_evidence_receipt.json"
    blockade = (
        workspace
        / "approved_promotion_live_write_blockade"
        / "live_write_blockade_report.json"
    )
    blockade_tamper = (
        workspace / "ap_lwbte_receipt" / "live_write_blockade_tamper_evidence_report.json"
    )
    hashes = {
        "packet_readme_sha256": _write_source_file(readme, "readme"),
        "source_bundle_sha256": _write_source_file(bundle_readme, "bundle"),
        "source_promotion_manifest_sha256": _write_source_file(promotion_manifest, "{}"),
        "source_operator_handoff_sha256": _write_source_file(handoff, "{}"),
        "source_approval_gate_sha256": _write_source_file(gate, "{}"),
        "source_staging_manifest_sha256": _write_source_file(staging, "{}"),
        "source_staging_tamper_evidence_sha256": _write_source_file(staging_receipt, "{}"),
        "source_live_write_blockade_sha256": _write_source_file(blockade, "{}"),
        "source_live_write_blockade_tamper_evidence_sha256": _write_source_file(
            blockade_tamper, "{}"
        ),
    }
    packet = {
        "verdict": "PASS",
        "workspace": str(workspace),
        "packet_path": str(readme.parent),
        "packet_json_path": str(readme.parent / "final_readiness_packet.json"),
        "packet_readme_path": str(readme),
        "source_bundle_path": str(bundle_readme.parent),
        "approval_token_phrase": SMOKE.APPROVAL_TOKEN_PHRASE,
        "promotion_item_count": 2,
        "approved_candidate_count": 1,
        "edited_candidate_count": 1,
        "excluded_rejected_count": 1,
        "ready_for_operator_review": True,
        "ready_for_operator_approved_staging": True,
        "ready_for_live_memory_write": False,
        "future_live_write_allowed": False,
        "requires_explicit_operator_approval": True,
        "requires_future_live_write_milestone": True,
        "live_write_blocked_reason": "blocked live",
        "vector_db_write_blocked_reason": "blocked vector",
        "approved_items": [
            {
                "candidate_id": "approved-1",
                "decision_type": "approved",
                "promoted_text": "Approve branch fixture",
            },
            {
                "candidate_id": "edited-1",
                "decision_type": "edited",
                "promoted_text": "Edited approved memory: kitchen countertop",
            },
        ],
        "safety_chain": {stage: "PASS" for stage in SMOKE.REQUIRED_SAFETY_CHAIN_STAGES},
        "operator_next_steps": [
            "A separate explicit future milestone is required before any live write path can be designed or implemented."
        ],
        "dry_run": True,
        "local_only": True,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "live_vector_db_written": False,
        "account_api_network_accessed": False,
        "autonomy_enabled": False,
        "errors": [],
        **hashes,
    }
    path = readme.parent / "final_readiness_packet.json"
    path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    return packet


def _write_packet(tmp_path: Path, packet: Dict[str, Any]) -> Path:
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    return path


def test_clean_final_readiness_packet_validates_pass(smoke_payload):
    assert smoke_payload["clean_packet_verdict"] == "PASS"
    assert smoke_payload["verdict"] == "PASS"


def test_malformed_json_fails(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ this is not valid json\n", encoding="utf-8")
    verdict, errors = SMOKE.audit_final_readiness_packet(path)
    assert verdict == "FAIL"
    assert any("malformed_json" in error for error in errors)


def test_missing_required_packet_field_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet.pop("workspace")
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("missing_required_packet_field" in error for error in errors)


def test_packet_readme_hash_mismatch_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["packet_readme_sha256"] = "0" * 64
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("packet_readme_hash_mismatch" in error for error in errors)


@pytest.mark.parametrize(
    "field_name,token",
    [
        ("source_bundle_sha256", "source_bundle_hash_mismatch"),
        ("source_promotion_manifest_sha256", "source_promotion_manifest_hash_mismatch"),
        ("source_operator_handoff_sha256", "source_operator_handoff_hash_mismatch"),
        ("source_approval_gate_sha256", "source_approval_gate_hash_mismatch"),
        ("source_staging_manifest_sha256", "source_staging_manifest_hash_mismatch"),
        (
            "source_staging_tamper_evidence_sha256",
            "source_staging_tamper_evidence_hash_mismatch",
        ),
        ("source_live_write_blockade_sha256", "source_live_write_blockade_hash_mismatch"),
        (
            "source_live_write_blockade_tamper_evidence_sha256",
            "source_live_write_blockade_tamper_evidence_hash_mismatch",
        ),
    ],
)
def test_source_hash_mismatch_fails(tmp_path, field_name, token):
    packet = _valid_packet(tmp_path)
    packet[field_name] = "0" * 64
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any(token in error for error in errors)


def test_approval_token_phrase_missing_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["approval_token_phrase"] = ""
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("approval_token_phrase_missing" in error for error in errors)


def test_approved_item_removed_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["approved_items"] = [
        item for item in packet["approved_items"] if item["decision_type"] != "approved"
    ]
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("approved_item_removed" in error for error in errors)


def test_edited_item_removed_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["approved_items"] = [
        item for item in packet["approved_items"] if item["decision_type"] != "edited"
    ]
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("edited_item_removed" in error for error in errors)


def test_edited_promoted_text_changed_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["approved_items"][1]["promoted_text"] = "Silently altered"
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("edited_promoted_text_changed" in error for error in errors)


def test_rejected_item_included_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["approved_items"].append(
        {"candidate_id": "rejected-1", "decision_type": "rejected", "promoted_text": "no"}
    )
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("rejected_item_included" in error for error in errors)


def test_count_mismatches_fail(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["promotion_item_count"] = 3
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("promotion_item_count_mismatch" in error for error in errors)
    packet = _valid_packet(tmp_path / "b")
    packet["excluded_rejected_count"] = 0
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path / "b", packet))
    assert verdict == "FAIL"
    assert any("excluded_rejected_count_mismatch" in error for error in errors)


def test_safety_chain_missing_and_failed_stages_fail(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["safety_chain"].pop("live_write_blockade")
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("safety_chain_missing_stage" in error for error in errors)
    packet = _valid_packet(tmp_path / "b")
    packet["safety_chain"]["live_write_blockade"] = "FAIL"
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path / "b", packet))
    assert verdict == "FAIL"
    assert any("safety_chain_stage_failed" in error for error in errors)


def test_live_write_flags_and_missing_reasons_fail(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["ready_for_live_memory_write"] = True
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert any("ready_for_live_memory_write_true" in error for error in errors)
    packet = _valid_packet(tmp_path / "b")
    packet["future_live_write_allowed"] = True
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path / "b", packet))
    assert any("future_live_write_allowed_true" in error for error in errors)
    packet = _valid_packet(tmp_path / "c")
    packet["requires_explicit_operator_approval"] = False
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path / "c", packet))
    assert any("requires_explicit_operator_approval_false" in error for error in errors)
    packet = _valid_packet(tmp_path / "d")
    packet["requires_future_live_write_milestone"] = False
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path / "d", packet))
    assert any("requires_future_live_write_milestone_false" in error for error in errors)
    packet = _valid_packet(tmp_path / "e")
    packet["live_write_blocked_reason"] = ""
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path / "e", packet))
    assert any("live_write_blocked_reason_missing" in error for error in errors)
    packet = _valid_packet(tmp_path / "f")
    packet["vector_db_write_blocked_reason"] = ""
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path / "f", packet))
    assert any("vector_db_write_blocked_reason_missing" in error for error in errors)


def test_missing_future_milestone_next_step_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["operator_next_steps"] = ["This packet is final dry-run readiness only."]
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("operator_next_steps_missing_future_milestone" in error for error in errors)


def test_unsafe_metadata_fails(tmp_path):
    packet = _valid_packet(tmp_path)
    packet["dry_run"] = False
    packet["model_called"] = True
    packet["autonomy_enabled"] = True
    verdict, errors = SMOKE.audit_final_readiness_packet(_write_packet(tmp_path, packet))
    assert verdict == "FAIL"
    assert any("unsafe_metadata" in error for error in errors)


def test_all_tamper_cases_detected_and_named(smoke_payload):
    names = [case["case_name"] for case in smoke_payload["tamper_cases"]]
    assert names == list(REQUIRED_TAMPER_CASES)
    assert smoke_payload["all_tamper_cases_detected"] is True
    assert all(case["detected"] is True for case in smoke_payload["tamper_cases"])
    assert all(case["actual_verdict"] == "FAIL" for case in smoke_payload["tamper_cases"])


def test_json_report_safety_and_verdict(smoke_payload):
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []
    _assert_safety_flags_false(smoke_payload)
    assert smoke_payload["dry_run"] is True
    assert smoke_payload["local_only"] is True


def test_script_has_no_network_or_ui_tokens():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for token in FORBIDDEN_SCRIPT_TOKENS:
        assert token not in source


def test_script_refuses_repository_root_as_base_dir():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", "--base-dir", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "FAIL"
    assert any("repository root" in error for error in payload["errors"])
