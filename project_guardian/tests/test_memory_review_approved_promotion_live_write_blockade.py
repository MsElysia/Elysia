# project_guardian/tests/test_memory_review_approved_promotion_live_write_blockade.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "run_memory_review_approved_promotion_live_write_blockade_smoke.py"
)
FUTURE_MILESTONE_MARKERS = ("separate", "milestone")


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def smoke_payload(tmp_path_factory) -> dict:
    base_dir = tmp_path_factory.mktemp("lwb")
    return _run_script("--base-dir", str(base_dir), "--keep-temp")


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def _source_staging_manifest(smoke_payload: dict) -> dict:
    path = Path(smoke_payload["source_staging_manifest_path"])
    return json.loads(path.read_text(encoding="utf-8"))


def test_clean_operator_approved_staging_package_validates_pass(smoke_payload):
    assert smoke_payload["clean_staging_valid"] is True
    assert smoke_payload["verdict"] == "PASS"


def test_staging_tamper_evidence_validates_pass(smoke_payload):
    assert smoke_payload["source_staging_tamper_evidence_verdict"] == "PASS"
    assert smoke_payload["tamper_evidence_verdict"] == "PASS"


def test_live_memory_write_request_is_denied(smoke_payload):
    assert smoke_payload["live_memory_write_requested"] is True
    assert smoke_payload["live_memory_write_allowed"] is False
    assert smoke_payload["live_memory_write_denied"] is True


def test_vector_db_write_request_is_denied(smoke_payload):
    assert smoke_payload["vector_db_write_requested"] is True
    assert smoke_payload["vector_db_write_allowed"] is False
    assert smoke_payload["vector_db_write_denied"] is True


def test_live_memory_write_is_not_attempted(smoke_payload):
    assert smoke_payload["live_memory_write_attempted"] is False


def test_vector_db_write_is_not_attempted(smoke_payload):
    assert smoke_payload["vector_db_write_attempted"] is False


def test_live_memory_write_is_not_performed(smoke_payload):
    assert smoke_payload["live_memory_write_performed"] is False


def test_vector_db_write_is_not_performed(smoke_payload):
    assert smoke_payload["vector_db_write_performed"] is False


def test_live_memory_write_path_is_not_created(smoke_payload):
    assert smoke_payload["live_memory_write_path_created"] is False
    assert not Path(smoke_payload["live_memory_write_path"]).exists()


def test_vector_db_write_path_is_not_created(smoke_payload):
    assert smoke_payload["vector_db_write_path_created"] is False
    assert not Path(smoke_payload["vector_db_write_path"]).exists()


def test_runtime_memory_files_created_count_is_zero(smoke_payload):
    assert smoke_payload["runtime_memory_files_created"] == 0


def test_vector_db_files_created_count_is_zero(smoke_payload):
    assert smoke_payload["vector_db_files_created"] == 0


def test_denial_reason_is_present(smoke_payload):
    assert smoke_payload["live_memory_write_denial_reason"]
    assert smoke_payload["vector_db_write_denial_reason"]


def test_denial_reason_says_future_separate_milestone_is_required(smoke_payload):
    reason = smoke_payload["live_memory_write_denial_reason"].lower()
    assert "separate" in reason
    assert "milestone" in reason
    vector_reason = smoke_payload["vector_db_write_denial_reason"].lower()
    assert "separate" in vector_reason
    assert "milestone" in vector_reason
    assert smoke_payload["requires_future_live_write_milestone"] is True


def test_ready_for_operator_approved_staging_true(smoke_payload):
    assert smoke_payload["ready_for_operator_approved_staging"] is True


def test_ready_for_live_memory_write_false(smoke_payload):
    assert smoke_payload["ready_for_live_memory_write"] is False


def test_future_live_write_allowed_false(smoke_payload):
    assert smoke_payload["future_live_write_allowed"] is False


def test_requires_future_live_write_milestone_true(smoke_payload):
    assert smoke_payload["requires_future_live_write_milestone"] is True


def test_approved_candidate_remains_included_in_source_staging(smoke_payload):
    staging = _source_staging_manifest(smoke_payload)
    staged_items = staging.get("staged_items") or []
    assert any(item.get("decision_type") == "approved" for item in staged_items)


def test_edited_candidate_remains_included_in_source_staging(smoke_payload):
    staging = _source_staging_manifest(smoke_payload)
    staged_items = staging.get("staged_items") or []
    assert any(item.get("decision_type") == "edited" for item in staged_items)


def test_rejected_candidate_remains_excluded_in_source_staging(smoke_payload):
    staging = _source_staging_manifest(smoke_payload)
    staged_items = staging.get("staged_items") or []
    assert all(item.get("decision_type") != "rejected" for item in staged_items)


def test_promotion_item_count_remains_2(smoke_payload):
    assert smoke_payload["promotion_item_count"] == 2
    staging = _source_staging_manifest(smoke_payload)
    assert staging.get("promotion_item_count") == 2


def test_excluded_rejected_count_remains_1(smoke_payload):
    assert smoke_payload["excluded_rejected_count"] == 1
    staging = _source_staging_manifest(smoke_payload)
    assert staging.get("excluded_rejected_count") == 1


def test_json_report_contains_verdict_pass(smoke_payload):
    assert smoke_payload["verdict"] == "PASS"
    assert smoke_payload["errors"] == []
    assert smoke_payload["live_write_blockade_report_valid_json"] is True
    report_path = Path(smoke_payload["live_write_blockade_report_path"])
    on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert on_disk["verdict"] == "PASS"


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
        "blockade_path",
        "live_write_blockade_report_path",
        "live_write_blockade_report_valid_json",
        "source_staging_manifest_path",
        "source_staging_manifest_sha256",
        "source_staging_tamper_evidence_verdict",
        "clean_staging_valid",
        "operator_approval_valid",
        "approval_gate_verdict",
        "tamper_evidence_verdict",
        "ready_for_operator_approved_staging",
        "ready_for_live_memory_write",
        "future_live_write_allowed",
        "live_memory_write_requested",
        "live_memory_write_allowed",
        "live_memory_write_denied",
        "live_memory_write_denial_reason",
        "live_memory_write_attempted",
        "live_memory_write_performed",
        "live_memory_write_path",
        "live_memory_write_path_created",
        "vector_db_write_requested",
        "vector_db_write_allowed",
        "vector_db_write_denied",
        "vector_db_write_denial_reason",
        "vector_db_write_attempted",
        "vector_db_write_performed",
        "vector_db_write_path",
        "vector_db_write_path_created",
        "runtime_memory_files_created",
        "vector_db_files_created",
        "promotion_item_count",
        "approved_candidate_count",
        "edited_candidate_count",
        "excluded_rejected_count",
        "operator_required",
        "requires_future_live_write_milestone",
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
    assert smoke_payload["approval_gate_verdict"] == "PASS"
    assert smoke_payload["operator_approval_valid"] is True
    _assert_safety_flags_false(smoke_payload)
    assert FUTURE_MILESTONE_MARKERS


def test_live_write_blockade_script_has_no_network_ui_or_route_behavior():
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


def test_live_write_blockade_script_refuses_repository_root_workspace():
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
