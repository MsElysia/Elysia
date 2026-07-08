# project_guardian/tests/test_memory_review_approved_promotion_operator_handoff.py

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "run_memory_review_approved_promotion_operator_handoff_smoke.py"
)
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


def test_operator_handoff_smoke_json_cli_passes(smoke_payload):
    payload = smoke_payload

    assert payload["verdict"] == "PASS"
    assert payload["handoff_path"]
    assert payload["operator_handoff_path"]
    assert payload["operator_handoff_valid_json"] is True
    assert payload["operator_checklist_path"]
    assert payload["operator_checklist_created"] is True
    assert payload["operator_checklist_sha256"]
    assert payload["promotion_bundle_path"]
    assert payload["promotion_manifest_path"]
    assert payload["promotion_manifest_hash_present"] is True
    assert payload["tamper_evidence_verdict"] == "PASS"
    assert payload["all_tamper_cases_detected"] is True
    assert payload["promotion_item_count"] == 2
    assert payload["approved_candidate_included"] is True
    assert payload["edited_candidate_included"] is True
    assert payload["edited_promoted_text_preserved"] is True
    assert payload["rejected_candidate_excluded"] is True
    assert payload["excluded_rejected_count"] == 1
    assert payload["ready_for_operator_review"] is True
    assert payload["ready_for_live_memory_write"] is False
    assert payload["requires_explicit_operator_approval"] is True
    assert payload["future_live_write_allowed"] is False
    assert payload["live_write_blocked_reason"]
    assert payload["handoff_paths_inside_workspace"] is True
    assert payload["operator_required"] is True
    assert payload["dry_run"] is True
    assert payload["local_only"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_operator_handoff_json_contract_fields_present(smoke_payload):
    required_fields = {
        "verdict",
        "workspace",
        "handoff_path",
        "operator_handoff_path",
        "operator_handoff_valid_json",
        "operator_checklist_path",
        "operator_checklist_created",
        "promotion_bundle_path",
        "promotion_manifest_path",
        "promotion_manifest_hash_present",
        "tamper_evidence_verdict",
        "all_tamper_cases_detected",
        "promotion_item_count",
        "approved_candidate_included",
        "edited_candidate_included",
        "rejected_candidate_excluded",
        "excluded_rejected_count",
        "ready_for_operator_review",
        "ready_for_live_memory_write",
        "requires_explicit_operator_approval",
        "future_live_write_allowed",
        "handoff_paths_inside_workspace",
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


def test_operator_handoff_preserved_workspace_artifacts(tmp_path):
    base_dir = tmp_path / "operator-handoff"
    payload = _run_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    workspace = base_dir.resolve()
    assert Path(payload["workspace"]) == workspace

    handoff_dir = Path(payload["handoff_path"])
    operator_handoff_path = Path(payload["operator_handoff_path"])
    checklist_path = Path(payload["operator_checklist_path"])
    promotion_manifest_path = Path(payload["promotion_manifest_path"])
    promotion_bundle_path = Path(payload["promotion_bundle_path"])

    for path in (
        handoff_dir,
        operator_handoff_path,
        checklist_path,
        promotion_manifest_path,
        promotion_bundle_path,
    ):
        assert path.exists()
        path.resolve().relative_to(workspace)

    handoff = json.loads(operator_handoff_path.read_text(encoding="utf-8"))
    manifest = json.loads(promotion_manifest_path.read_text(encoding="utf-8"))

    assert handoff["verdict"] == "PASS"
    assert handoff["promotion_item_count"] == 2
    assert handoff["excluded_rejected_count"] == 1
    assert handoff["promotion_manifest_sha256"] == manifest["promotion_manifest_sha256"]
    assert handoff["tamper_evidence_verdict"] == "PASS"
    assert handoff["all_tamper_cases_detected"] is True
    assert handoff["ready_for_operator_review"] is True
    assert handoff["ready_for_live_memory_write"] is False
    assert handoff["requires_explicit_operator_approval"] is True
    assert handoff["future_live_write_allowed"] is False
    assert handoff["live_write_blocked_reason"]
    assert handoff["operator_checklist_sha256"] == hashlib.sha256(
        checklist_path.read_bytes()
    ).hexdigest()

    items = handoff["promotion_items"]
    assert len(items) == 2
    assert any(item["decision_type"] == "approved" for item in items)
    edited_items = [item for item in items if item["decision_type"] == "edited"]
    assert len(edited_items) == 1
    assert edited_items[0]["promoted_text"] == EDITED_TEXT
    assert edited_items[0]["ready_for_operator_review"] is True
    assert edited_items[0]["ready_for_live_memory_write"] is False
    assert edited_items[0]["requires_explicit_operator_approval"] is True
    assert all(item["decision_type"] != "rejected" for item in items)

    manifest_edited = [
        item for item in manifest["promotion_items"] if item.get("text_was_edited")
    ]
    assert len(manifest_edited) == 1
    assert "Edit branch fixture" in manifest_edited[0]["original_text"]
    assert manifest_edited[0]["promoted_text"] == EDITED_TEXT
    _assert_safety_flags_false(handoff)


def test_operator_handoff_script_has_no_network_ui_or_route_behavior():
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


def test_operator_handoff_script_refuses_repository_root_workspace():
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
