# project_guardian/tests/test_memory_review_approved_promotion_operator_approved_staging.py

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = (
    SCRIPT_DIR / "run_memory_review_approved_promotion_operator_approved_staging_smoke.py"
)
APPROVAL_TOKEN_PHRASE = "APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY"
EDITED_TEXT = (
    "Edited approved memory: kitchen countertop measurement is 42 inches and "
    "the revised tile color is blue."
)


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


def test_operator_approved_staging_smoke_json_cli_passes(smoke_payload):
    payload = smoke_payload

    assert payload["verdict"] == "PASS"
    assert payload["staging_path"]
    assert payload["operator_approved_staging_manifest_path"]
    assert payload["operator_approved_staging_manifest_valid_json"] is True
    assert payload["staging_readme_path"]
    assert payload["staging_readme_created"] is True
    assert payload["staging_readme_sha256"]
    assert payload["promotion_manifest_hash_present"] is True
    assert payload["operator_handoff_hash_present"] is True
    assert payload["approval_gate_hash_present"] is True
    assert payload["approval_token_phrase"] == APPROVAL_TOKEN_PHRASE
    assert payload["approval_gate_verdict"] == "PASS"
    assert payload["operator_approval_valid"] is True
    assert payload["tamper_evidence_verdict"] == "PASS"
    assert payload["all_tamper_cases_detected"] is True
    assert payload["promotion_item_count"] == 2
    assert payload["approved_candidate_included"] is True
    assert payload["edited_candidate_included"] is True
    assert payload["rejected_candidate_excluded"] is True
    assert payload["excluded_rejected_count"] == 1
    assert payload["ready_for_operator_approved_staging"] is True
    assert payload["ready_for_live_memory_write"] is False
    assert payload["requires_explicit_operator_approval"] is True
    assert payload["future_live_write_allowed"] is False
    assert payload["live_write_blocked_reason"]
    assert payload["staging_paths_inside_workspace"] is True
    assert payload["operator_required"] is True
    assert payload["dry_run"] is True
    assert payload["local_only"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_operator_approved_staging_json_contract_fields_present(smoke_payload):
    required_fields = {
        "verdict",
        "workspace",
        "staging_path",
        "operator_approved_staging_manifest_path",
        "operator_approved_staging_manifest_valid_json",
        "staging_readme_path",
        "staging_readme_created",
        "promotion_manifest_hash_present",
        "operator_handoff_hash_present",
        "approval_gate_hash_present",
        "approval_gate_verdict",
        "operator_approval_valid",
        "tamper_evidence_verdict",
        "all_tamper_cases_detected",
        "promotion_item_count",
        "approved_candidate_included",
        "edited_candidate_included",
        "rejected_candidate_excluded",
        "excluded_rejected_count",
        "ready_for_operator_approved_staging",
        "ready_for_live_memory_write",
        "requires_explicit_operator_approval",
        "future_live_write_allowed",
        "staging_paths_inside_workspace",
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


def test_operator_approved_staging_preserved_workspace_artifacts(tmp_path):
    base_dir = tmp_path / "operator-approved-staging"
    payload = _run_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    workspace = base_dir.resolve()
    assert Path(payload["workspace"]) == workspace

    staging_dir = Path(payload["staging_path"])
    manifest_path = Path(payload["operator_approved_staging_manifest_path"])
    readme_path = Path(payload["staging_readme_path"])
    handoff_path = Path(payload["operator_handoff_path"])
    gate_path = Path(payload["operator_approval_gate_path"])

    for path in (staging_dir, manifest_path, readme_path, handoff_path, gate_path):
        assert path.exists()
        path.resolve().relative_to(workspace)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    readme = readme_path.read_text(encoding="utf-8")
    staged_items = {item["decision_type"]: item for item in manifest["staged_items"]}

    assert staging_dir.name == "approved_promotion_operator_approved_staging"
    assert manifest_path.name == "operator_approved_staging_manifest.json"
    assert readme_path.name == "STAGING_README.md"
    assert manifest["verdict"] == "PASS"
    assert manifest["operator_approved_staging_manifest_valid_json"] is True
    assert payload["staging_readme_sha256"] == hashlib.sha256(
        readme_path.read_bytes()
    ).hexdigest()
    assert manifest["staging_readme_sha256"] == payload["staging_readme_sha256"]
    assert "approved" in staged_items
    assert "edited" in staged_items
    assert "rejected" not in staged_items
    assert staged_items["edited"]["promoted_text"] == EDITED_TEXT
    assert manifest["promotion_item_count"] == 2
    assert manifest["excluded_rejected_count"] == 1
    assert manifest["promotion_manifest_sha256"]
    assert manifest["operator_handoff_sha256"] == hashlib.sha256(
        handoff_path.read_bytes()
    ).hexdigest()
    assert manifest["operator_approval_gate_sha256"] == hashlib.sha256(
        gate_path.read_bytes()
    ).hexdigest()
    assert manifest["approval_token_phrase"] == APPROVAL_TOKEN_PHRASE
    assert APPROVAL_TOKEN_PHRASE in readme
    assert manifest["tamper_evidence_verdict"] == "PASS"
    assert manifest["approval_gate_verdict"] == "PASS"
    assert manifest["operator_approval_valid"] is True
    assert manifest["ready_for_operator_approved_staging"] is True
    assert manifest["ready_for_live_memory_write"] is False
    assert manifest["future_live_write_allowed"] is False
    assert manifest["requires_explicit_operator_approval"] is True
    assert manifest["live_write_blocked_reason"]
    assert manifest["staging_paths_inside_workspace"] is True
    _assert_safety_flags_false(manifest)


def test_invalid_approval_does_not_create_pass_staging(tmp_path):
    sys.path.insert(0, str(SCRIPT_DIR))
    from run_memory_review_approved_promotion_operator_approval_gate_smoke import (
        run_memory_review_approved_promotion_operator_approval_gate_smoke,
    )
    from run_memory_review_approved_promotion_operator_approved_staging_smoke import (
        _assemble_operator_approved_staging,
    )

    workspace = tmp_path / "invalid-approval-staging"
    gate_report = run_memory_review_approved_promotion_operator_approval_gate_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    assert gate_report.verdict == "PASS"
    Path(gate_report.approval_artifact_path).write_text("{}\n", encoding="utf-8")

    report = _assemble_operator_approved_staging(workspace, gate_report)
    assert report.verdict == "FAIL"
    assert report.operator_approval_valid is False
    assert report.ready_for_operator_approved_staging is False

    manifest_path = (
        workspace
        / "approved_promotion_operator_approved_staging"
        / "operator_approved_staging_manifest.json"
    )
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["verdict"] != "PASS"


def test_operator_approved_staging_script_has_no_network_ui_or_route_behavior():
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


def test_operator_approved_staging_script_refuses_repository_root_workspace():
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
