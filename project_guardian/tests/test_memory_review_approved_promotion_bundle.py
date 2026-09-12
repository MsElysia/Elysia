# project_guardian/tests/test_memory_review_approved_promotion_bundle.py

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_approved_promotion_bundle_smoke.py"
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


def _sha256_text(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def test_approved_promotion_bundle_smoke_json_cli_passes():
    payload = _run_script()

    assert payload["verdict"] == "PASS"
    assert payload["bundle_path"]
    assert payload["promotion_manifest_path"]
    assert payload["promotion_manifest_valid_json"] is True
    assert payload["approved_candidate_included"] is True
    assert payload["edited_candidate_included"] is True
    assert payload["edited_text_preserved"] is True
    assert payload["original_text_preserved_for_edit"] is True
    assert payload["rejected_candidate_excluded"] is True
    assert payload["promotion_item_count"] == 2
    assert payload["excluded_rejected_count"] == 1
    assert payload["promotion_items_have_review_links"] is True
    assert payload["promotion_items_have_hashes"] is True
    assert payload["bundle_paths_inside_workspace"] is True
    assert payload["manifest_hash_present"] is True
    assert payload["operator_required"] is True
    assert payload["dry_run"] is True
    assert payload["local_only"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_approved_promotion_bundle_json_contract_fields_present():
    payload = _run_script()
    required_fields = {
        "verdict",
        "workspace",
        "bundle_path",
        "promotion_manifest_path",
        "promotion_manifest_valid_json",
        "approved_candidate_included",
        "edited_candidate_included",
        "edited_text_preserved",
        "original_text_preserved_for_edit",
        "rejected_candidate_excluded",
        "promotion_item_count",
        "excluded_rejected_count",
        "promotion_items_have_review_links",
        "promotion_items_have_hashes",
        "bundle_paths_inside_workspace",
        "manifest_hash_present",
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
    assert required_fields.issubset(payload)
    _assert_safety_flags_false(payload)


def test_approved_promotion_bundle_preserved_workspace_artifacts(tmp_path):
    base_dir = tmp_path / "approved-promotion-bundle"
    payload = _run_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    workspace = base_dir.resolve()
    assert Path(payload["workspace"]) == workspace
    _assert_safety_flags_false(payload)

    artifacts = payload["artifact_paths"]
    bundle_dir = Path(artifacts["bundle_dir"])
    manifest_path = Path(artifacts["promotion_manifest"])
    readme_path = Path(artifacts["promotion_readme"])
    review_queue = Path(artifacts["review_queue"])
    review_decisions = Path(artifacts["review_decisions"])

    for path in (bundle_dir, manifest_path, readme_path, review_queue, review_decisions):
        assert path.exists()
        path.relative_to(workspace)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["promotion_item_count"] == 2
    assert manifest["excluded_rejected_count"] == 1
    assert manifest["approved_candidate_count"] == 1
    assert manifest["edited_candidate_count"] == 1
    assert manifest["rejected_candidate_count"] == 1
    assert manifest["promotion_manifest_sha256"]
    assert manifest["review_decisions_log_sha256"] == hashlib.sha256(
        review_decisions.read_bytes()
    ).hexdigest()
    assert manifest["dry_run"] is True
    assert manifest["local_only"] is True
    assert manifest["live_memory_written"] is False
    assert manifest["live_vector_db_written"] is False

    items = manifest["promotion_items"]
    assert len(items) == 2
    edited_items = [item for item in items if item["text_was_edited"]]
    approved_items = [item for item in items if not item["text_was_edited"]]
    assert len(edited_items) == 1
    assert len(approved_items) == 1
    assert edited_items[0]["promoted_text"] == EDITED_TEXT
    assert "Edit branch fixture" in edited_items[0]["original_text"]
    assert edited_items[0]["promoted_text"] != edited_items[0]["original_text"]
    assert edited_items[0]["decision_id"]
    assert edited_items[0]["review_decision_log_path"] == str(review_decisions.resolve())
    assert edited_items[0]["promoted_text_sha256"] == _sha256_text(edited_items[0]["promoted_text"])

    rejected_ids = {
        item.get("candidate_id")
        for item in items
    }
    decisions = [
        json.loads(line)
        for line in review_decisions.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rejected_candidate_ids = {
        item["candidate_id"]
        for item in decisions
        if item.get("new_status") == "rejected"
    }
    assert rejected_candidate_ids
    assert rejected_candidate_ids.isdisjoint(rejected_ids)


def test_approved_promotion_bundle_script_has_no_network_ui_or_route_behavior():
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


def test_approved_promotion_bundle_script_refuses_repository_root_workspace():
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
