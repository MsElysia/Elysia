# project_guardian/tests/test_memory_review_approved_promotion_operator_approval_gate.py

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "run_memory_review_approved_promotion_operator_approval_gate_smoke.py"
)
APPROVAL_TOKEN_PHRASE = "APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY"


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


def test_operator_approval_gate_smoke_json_cli_passes(smoke_payload):
    payload = smoke_payload

    assert payload["verdict"] == "PASS"
    assert payload["approval_gate_path"]
    assert payload["operator_approval_gate_path"]
    assert payload["operator_approval_gate_valid_json"] is True
    assert payload["handoff_path"]
    assert payload["operator_handoff_path"]
    assert payload["operator_handoff_sha256"]
    assert payload["approval_artifact_path"]
    assert payload["approval_case_count"] == 5
    assert payload["missing_approval_fails_closed"] is True
    assert payload["invalid_token_fails_closed"] is True
    assert payload["mismatched_handoff_hash_fails_closed"] is True
    assert payload["stale_approval_fails_closed"] is True
    assert payload["valid_approval_passes_dry_run_staging"] is True
    assert payload["ready_for_operator_approved_staging"] is True
    assert payload["ready_for_live_memory_write"] is False
    assert payload["requires_explicit_operator_approval"] is True
    assert payload["future_live_write_allowed"] is False
    assert payload["live_write_blocked_reason"]
    assert payload["approval_scope"] == "dry_run_memory_promotion_staging_only"
    assert payload["approval_token_phrase_documented"] is True
    assert payload["approval_paths_inside_workspace"] is True
    assert payload["default_state_blocked"] is True
    assert payload["operator_required"] is True
    assert payload["dry_run"] is True
    assert payload["local_only"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_operator_approval_gate_json_contract_fields_present(smoke_payload):
    required_fields = {
        "verdict",
        "workspace",
        "approval_gate_path",
        "operator_approval_gate_path",
        "operator_approval_gate_valid_json",
        "handoff_path",
        "operator_handoff_path",
        "operator_handoff_sha256",
        "approval_artifact_path",
        "approval_case_count",
        "approval_cases",
        "missing_approval_fails_closed",
        "invalid_token_fails_closed",
        "mismatched_handoff_hash_fails_closed",
        "valid_approval_passes_dry_run_staging",
        "ready_for_operator_approved_staging",
        "ready_for_live_memory_write",
        "requires_explicit_operator_approval",
        "future_live_write_allowed",
        "live_write_blocked_reason",
        "approval_scope",
        "approval_token_phrase_documented",
        "approval_paths_inside_workspace",
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
    _assert_safety_flags_false(smoke_payload)


def test_operator_approval_gate_cases_fail_closed_and_valid_passes(smoke_payload):
    cases = {case["case_name"]: case for case in smoke_payload["approval_cases"]}
    expected_names = {
        "missing_approval",
        "invalid_approval_token",
        "mismatched_handoff_hash",
        "stale_handoff_id",
        "valid_explicit_dry_run_approval",
    }
    assert set(cases) == expected_names

    for name in (
        "missing_approval",
        "invalid_approval_token",
        "mismatched_handoff_hash",
        "stale_handoff_id",
    ):
        assert cases[name]["expected_verdict"] == "FAIL"
        assert cases[name]["actual_verdict"] == "FAIL"
        assert cases[name]["detected"] is True
        assert cases[name]["details"]["ready_for_operator_approved_staging"] is False
        assert cases[name]["details"]["ready_for_live_memory_write"] is False
        assert cases[name]["details"]["future_live_write_allowed"] is False
        assert cases[name]["details"]["errors"]

    valid = cases["valid_explicit_dry_run_approval"]
    assert valid["expected_verdict"] == "PASS"
    assert valid["actual_verdict"] == "PASS"
    assert valid["detected"] is True
    assert valid["details"]["ready_for_operator_approved_staging"] is True
    assert valid["details"]["ready_for_live_memory_write"] is False
    assert valid["details"]["future_live_write_allowed"] is False
    assert valid["details"]["errors"] == []


def test_operator_approval_gate_preserved_workspace_artifacts(tmp_path):
    base_dir = tmp_path / "operator-approval-gate"
    payload = _run_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    workspace = base_dir.resolve()
    assert Path(payload["workspace"]) == workspace

    approval_gate_dir = Path(payload["approval_gate_path"])
    gate_json_path = Path(payload["operator_approval_gate_path"])
    readme_path = Path(payload["approval_gate_readme_path"])
    handoff_path = Path(payload["operator_handoff_path"])
    approval_artifact_path = Path(payload["approval_artifact_path"])

    for path in (
        approval_gate_dir,
        gate_json_path,
        readme_path,
        handoff_path,
        approval_artifact_path,
    ):
        assert path.exists()
        path.resolve().relative_to(workspace)

    report = json.loads(gate_json_path.read_text(encoding="utf-8"))
    approval = json.loads(approval_artifact_path.read_text(encoding="utf-8"))
    readme = readme_path.read_text(encoding="utf-8")

    assert report["verdict"] == "PASS"
    assert report["operator_approval_gate_valid_json"] is True
    assert report["operator_handoff_sha256"] == hashlib.sha256(
        handoff_path.read_bytes()
    ).hexdigest()
    assert approval["operator_approval_token"] == APPROVAL_TOKEN_PHRASE
    assert approval["handoff_sha256"] == report["operator_handoff_sha256"]
    assert approval["approved_for_dry_run_staging"] is True
    assert approval["approved_for_live_memory_write"] is False
    assert approval["dry_run"] is True
    assert approval["local_only"] is True
    assert APPROVAL_TOKEN_PHRASE in readme
    assert report["ready_for_operator_approved_staging"] is True
    assert report["ready_for_live_memory_write"] is False
    assert report["future_live_write_allowed"] is False
    assert report["approval_paths_inside_workspace"] is True
    _assert_safety_flags_false(report)


def test_operator_approval_gate_script_has_no_network_ui_or_route_behavior():
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


def test_operator_approval_gate_script_refuses_repository_root_workspace():
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
