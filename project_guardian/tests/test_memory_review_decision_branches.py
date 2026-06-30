# project_guardian/tests/test_memory_review_decision_branches.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_decision_branches_smoke.py"


def _run_decision_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def test_decision_branch_smoke_json_cli_passes():
    payload = _run_decision_script()

    assert payload["verdict"] == "PASS"
    assert payload["source_type"] == "transcription"
    assert payload["candidates_created"] >= 3
    assert payload["approved_count"] >= 2
    assert payload["rejected_count"] >= 1
    assert payload["edited_count"] >= 1
    assert len(payload["approved_ids"]) >= 2
    assert len(payload["rejected_ids"]) == 1
    assert len(payload["edited_ids"]) == 1
    assert payload["rejected_excluded_from_search"] is True
    assert payload["edited_text_present"] is True
    assert payload["search_ready"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_decision_branch_preserved_workspace_contains_expected_artifacts(tmp_path):
    base_dir = tmp_path / "decision-branches"
    payload = _run_decision_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    assert Path(payload["workspace"]) == base_dir.resolve()
    _assert_safety_flags_false(payload)

    artifact_paths = payload["artifact_paths"]
    for path_text in artifact_paths.values():
        path = Path(path_text)
        assert path.is_file()
        path.relative_to(base_dir.resolve())

    approved_export = Path(artifact_paths["approved_export"]).read_text(encoding="utf-8")
    memory_store = Path(artifact_paths["memory_store"]).read_text(encoding="utf-8")
    rejected_id = payload["rejected_ids"][0]
    edited_id = payload["edited_ids"][0]

    assert rejected_id not in approved_export
    assert rejected_id not in memory_store
    assert edited_id in approved_export
    assert edited_id in memory_store
    assert "Edited approved memory" in approved_export
    assert "Edited approved memory" in memory_store
    assert "rejected-only" not in approved_export
    assert "rejected-only" not in memory_store


def test_decision_branch_json_contract_fields_are_present():
    payload = _run_decision_script()

    required_fields = {
        "verdict",
        "workspace",
        "candidates_created",
        "approved_count",
        "rejected_count",
        "edited_count",
        "approved_ids",
        "rejected_ids",
        "edited_ids",
        "rejected_excluded_from_search",
        "edited_text_present",
        "search_ready",
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
        "errors",
    }
    assert required_fields.issubset(payload)
    assert payload["verdict"] == "PASS"
    _assert_safety_flags_false(payload)


def test_decision_branch_script_does_not_add_network_ui_or_route_behavior():
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


def test_decision_branch_script_refuses_repository_root_workspace():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--json",
            "--base-dir",
            str(REPO_ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "FAIL"
    assert "repository root" in payload["errors"][0]
