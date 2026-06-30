# project_guardian/tests/test_memory_import_review_handoff.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_import_review_handoff_smoke.py"
EXPECTED_SOURCE_TYPES = {"transcription", "chatgpt_export", "email_export"}


def _run_handoff_script(*args: str) -> dict:
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
    for item in payload["per_source"]:
        assert item["model_called"] is False
        assert item["embeddings_used"] is False
        assert item["live_memory_written"] is False
        assert item["live_vector_db_written"] is False
        assert item["autonomy_enabled"] is False


def test_handoff_smoke_json_cli_passes_for_all_source_types():
    payload = _run_handoff_script()

    assert payload["verdict"] == "PASS"
    assert payload["source_type"] == "all"
    assert set(payload["source_types"]) == EXPECTED_SOURCE_TYPES
    assert len(payload["per_source"]) == 3
    assert payload["candidates_created"] >= 4
    assert payload["review_items_available"] is True
    assert payload["approval_path_available"] is True
    assert payload["search_ready"] is True
    assert payload["workspace_preserved"] is False
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_handoff_smoke_preserved_workspace_contains_review_artifacts(tmp_path):
    base_dir = tmp_path / "handoff"
    payload = _run_handoff_script("--source-type", "transcription", "--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["source_types"] == ["transcription"]
    assert payload["workspace_preserved"] is True
    assert Path(payload["workspace"]) == base_dir.resolve()
    assert payload["candidates_created"] >= 1
    assert payload["review_items_available"] is True
    assert payload["approval_path_available"] is True
    assert payload["search_ready"] is True
    _assert_safety_flags_false(payload)

    source_report = payload["per_source"][0]
    artifact_paths = source_report["artifact_paths"]
    for path_text in artifact_paths.values():
        path = Path(path_text)
        assert path.is_file()
        path.relative_to(base_dir.resolve())
    assert source_report["review_item_count"] >= 1
    assert source_report["approved_export_available"] is True
    assert source_report["memory_store_available"] is True
    assert source_report["context_bundle_available"] is True


def test_handoff_report_has_required_json_contract_fields():
    payload = _run_handoff_script("--source-type", "email_export")

    required_fields = {
        "verdict",
        "workspace",
        "source_type",
        "candidates_created",
        "review_items_available",
        "approval_path_available",
        "search_ready",
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "autonomy_enabled",
        "errors",
    }
    assert required_fields.issubset(payload)
    assert payload["verdict"] == "PASS"
    assert payload["source_type"] == "email_export"
    assert payload["candidates_created"] >= 1
    assert payload["review_items_available"] is True
    assert payload["approval_path_available"] is True
    assert payload["search_ready"] is True
    _assert_safety_flags_false(payload)


def test_handoff_script_does_not_add_network_ui_or_route_behavior():
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


def test_handoff_script_refuses_repository_root_workspace():
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
