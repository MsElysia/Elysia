# project_guardian/tests/test_memory_review_decision_idempotency.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_decision_idempotency_smoke.py"


def _run_idempotency_script(*args: str) -> dict:
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


def test_idempotency_smoke_json_cli_passes():
    payload = _run_idempotency_script()

    assert payload["verdict"] == "PASS"
    assert payload["source_type"] == "transcription"
    assert payload["candidates_created"] >= 3

    assert payload["first_approved_count"] == payload["second_approved_count"]
    assert payload["first_rejected_count"] == payload["second_rejected_count"]
    assert payload["first_edited_count"] == payload["second_edited_count"]
    assert payload["second_approved_count"] >= 2
    assert payload["second_rejected_count"] >= 1
    assert payload["second_edited_count"] >= 1

    assert payload["approved_counts_stable"] is True
    assert payload["rejected_counts_stable"] is True
    assert payload["edited_counts_stable"] is True
    assert payload["approved_ids_stable"] is True
    assert payload["rejected_ids_stable"] is True
    assert payload["store_record_count_stable"] is True
    assert payload["no_duplicate_approved_records"] is True
    assert payload["no_duplicate_store_records"] is True
    assert payload["rejected_still_excluded"] is True
    assert payload["edited_text_still_present"] is True
    assert payload["search_ready"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_idempotency_preserved_workspace_has_no_duplicate_records(tmp_path):
    base_dir = tmp_path / "idempotency"
    payload = _run_idempotency_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    assert Path(payload["workspace"]) == base_dir.resolve()
    _assert_safety_flags_false(payload)

    artifact_paths = payload["artifact_paths"]
    for path_text in artifact_paths.values():
        path = Path(path_text)
        assert path.is_file()
        path.relative_to(base_dir.resolve())

    approved_export_lines = [
        json.loads(line)
        for line in Path(artifact_paths["approved_export"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    store_lines = [
        json.loads(line)
        for line in Path(artifact_paths["memory_store"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    approved_candidate_ids = [record["candidate_id"] for record in approved_export_lines]
    store_candidate_ids = [record["candidate_id"] for record in store_lines]
    store_memory_ids = [record["memory_id"] for record in store_lines]

    assert len(approved_candidate_ids) == len(set(approved_candidate_ids))
    assert len(store_candidate_ids) == len(set(store_candidate_ids))
    assert len(store_memory_ids) == len(set(store_memory_ids))

    rejected_id = payload["rejected_ids"][0]
    edited_id = payload["edited_ids"][0]
    approved_export_text = Path(artifact_paths["approved_export"]).read_text(encoding="utf-8")
    store_text = Path(artifact_paths["memory_store"]).read_text(encoding="utf-8")

    assert rejected_id not in approved_export_text
    assert rejected_id not in store_text
    assert "rejected-only" not in approved_export_text
    assert "rejected-only" not in store_text
    assert edited_id in approved_export_text
    assert edited_id in store_text
    assert "Edited approved memory" in approved_export_text
    assert "Edited approved memory" in store_text


def test_idempotency_json_contract_fields_are_present():
    payload = _run_idempotency_script()

    required_fields = {
        "verdict",
        "workspace",
        "candidates_created",
        "first_approved_count",
        "second_approved_count",
        "first_rejected_count",
        "second_rejected_count",
        "first_edited_count",
        "second_edited_count",
        "approved_counts_stable",
        "rejected_counts_stable",
        "edited_counts_stable",
        "approved_ids_stable",
        "rejected_ids_stable",
        "store_record_count_stable",
        "no_duplicate_approved_records",
        "no_duplicate_store_records",
        "rejected_still_excluded",
        "edited_text_still_present",
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


def test_idempotency_script_does_not_add_network_ui_or_route_behavior():
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


def test_idempotency_script_refuses_repository_root_workspace():
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
