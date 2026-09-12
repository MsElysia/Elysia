# project_guardian/tests/test_memory_review_decision_audit_trail.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_decision_audit_trail_smoke.py"

REQUIRED_DECISION_FIELDS = {
    "decision_id",
    "candidate_id",
    "previous_status",
    "new_status",
    "decided_at",
    "operator_required",
    "live_memory_written",
    "source_queue_path",
}


def _run_audit_script(*args: str) -> dict:
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


def test_audit_trail_smoke_json_cli_passes():
    payload = _run_audit_script()

    assert payload["verdict"] == "PASS"
    assert payload["source_type"] == "transcription"
    assert payload["candidates_created"] >= 3

    assert payload["decision_log_exists"] is True
    assert payload["decision_log_line_count"] >= 6
    assert payload["decision_entries_valid_json"] is True
    assert payload["required_fields_present"] is True
    assert payload["candidate_ids_present"] is True
    assert payload["previous_status_present"] is True
    assert payload["new_status_present"] is True

    assert payload["approve_transition_present"] is True
    assert payload["reject_transition_present"] is True
    assert payload["edit_transition_present"] is True

    assert payload["timestamps_present"] is True
    assert payload["timestamps_chronological"] is True

    assert payload["latest_decisions_resolved"] is True
    assert payload["latest_approved_count"] == 1
    assert payload["latest_rejected_count"] == 1
    assert payload["latest_edited_count"] == 1

    assert payload["rejected_still_excluded"] is True
    assert payload["edited_text_still_present"] is True
    assert payload["operator_required"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_audit_trail_preserved_workspace_log_is_well_formed(tmp_path):
    base_dir = tmp_path / "audit-trail"
    payload = _run_audit_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    assert Path(payload["workspace"]) == base_dir.resolve()
    _assert_safety_flags_false(payload)

    artifact_paths = payload["artifact_paths"]
    for path_text in artifact_paths.values():
        path = Path(path_text)
        assert path.is_file()
        path.relative_to(base_dir.resolve())

    decision_lines = [
        line
        for line in Path(artifact_paths["review_decisions"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(decision_lines) >= 6

    entries = [json.loads(line) for line in decision_lines]
    statuses = set()
    timestamps = []
    for entry in entries:
        assert REQUIRED_DECISION_FIELDS.issubset(entry)
        assert str(entry["candidate_id"]).strip()
        assert str(entry["previous_status"]).strip()
        assert str(entry["new_status"]).strip()
        assert entry["operator_required"] is True
        assert entry["live_memory_written"] is False
        statuses.add(entry["new_status"])
        timestamps.append(str(entry["decided_at"]))

    assert {"approved", "rejected", "edited"}.issubset(statuses)
    assert timestamps == sorted(timestamps)

    # Rejected content must never reach approved export or the local store.
    approved_export = Path(artifact_paths["approved_export"]).read_text(encoding="utf-8")
    memory_store = Path(artifact_paths["memory_store"]).read_text(encoding="utf-8")
    assert "rejected-only" not in approved_export
    assert "rejected-only" not in memory_store

    # Edited text is preserved in the edited artifact referenced by the log.
    edited_text = Path(artifact_paths["edited_text"]).read_text(encoding="utf-8")
    assert "Edited approved memory" in edited_text


def test_audit_trail_json_contract_fields_are_present():
    payload = _run_audit_script()

    required_fields = {
        "verdict",
        "workspace",
        "candidates_created",
        "decision_log_path",
        "decision_log_exists",
        "decision_log_line_count",
        "decision_entries_valid_json",
        "required_fields_present",
        "candidate_ids_present",
        "previous_status_present",
        "new_status_present",
        "approve_transition_present",
        "reject_transition_present",
        "edit_transition_present",
        "timestamps_present",
        "timestamps_chronological",
        "latest_decisions_resolved",
        "latest_approved_count",
        "latest_rejected_count",
        "latest_edited_count",
        "operator_required",
        "live_memory_written",
        "model_called",
        "embeddings_used",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
        "errors",
    }
    assert required_fields.issubset(payload)
    assert payload["verdict"] == "PASS"
    _assert_safety_flags_false(payload)


def test_audit_trail_script_does_not_add_network_ui_or_route_behavior():
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


def test_audit_trail_script_refuses_repository_root_workspace():
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
