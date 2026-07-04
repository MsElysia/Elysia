# project_guardian/tests/test_memory_review_recovery_audit_trail.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_recovery_audit_trail_smoke.py"

EXPECTED_RECOVERY_EVENTS = {
    "corruption_detected",
    "quarantine_created",
    "corrupt_log_preserved",
    "manifest_written",
    "known_good_resolution_used",
    "recovery_completed",
}

REQUIRED_RECOVERY_AUDIT_FIELDS = {
    "recovery_event_id",
    "event_type",
    "event_at",
    "source_log_path",
    "quarantine_log_path",
    "quarantine_manifest_path",
    "detected_error_types",
    "operator_required",
    "dry_run",
    "local_only",
    "silently_repaired",
    "live_memory_written",
    "model_called",
    "embeddings_used",
    "live_vector_db_written",
    "account_api_network_accessed",
    "autonomy_enabled",
}


def _run_script(*args: str) -> dict:
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


def test_recovery_audit_smoke_json_cli_passes():
    payload = _run_script()

    assert payload["verdict"] == "PASS"
    assert payload["recovery_audit_log_exists"] is True
    assert payload["recovery_audit_line_count"] == 6
    assert payload["recovery_audit_valid_jsonl"] is True
    assert payload["recovery_audit_required_fields_present"] is True
    assert payload["recovery_events_present"] is True
    assert payload["recovery_events_chronological"] is True

    assert payload["corruption_detected"] is True
    assert payload["quarantine_created"] is True
    assert payload["quarantine_manifest_created"] is True
    assert payload["quarantine_log_preserved"] is True
    assert payload["known_good_resolution_used"] is True
    assert payload["latest_decisions_match_known_good"] is True
    assert payload["corrupt_log_not_trusted"] is True
    assert payload["rejected_still_excluded"] is True
    assert payload["edited_text_still_present"] is True

    assert payload["operator_required"] is True
    assert payload["dry_run"] is True
    assert payload["local_only"] is True
    assert payload["silently_repaired"] is False
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_recovery_audit_json_contract_fields_present():
    payload = _run_script()
    required_fields = {
        "verdict",
        "workspace",
        "recovery_audit_log_path",
        "recovery_audit_log_exists",
        "recovery_audit_line_count",
        "recovery_audit_valid_jsonl",
        "recovery_audit_required_fields_present",
        "recovery_events_present",
        "recovery_events_chronological",
        "corruption_detected",
        "quarantine_created",
        "quarantine_manifest_created",
        "quarantine_log_preserved",
        "known_good_resolution_used",
        "latest_decisions_match_known_good",
        "corrupt_log_not_trusted",
        "rejected_still_excluded",
        "edited_text_still_present",
        "operator_required",
        "dry_run",
        "local_only",
        "silently_repaired",
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


def test_recovery_audit_preserved_workspace_log_is_well_formed(tmp_path):
    base_dir = tmp_path / "recovery-audit-trail"
    payload = _run_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    assert Path(payload["workspace"]) == base_dir.resolve()
    _assert_safety_flags_false(payload)

    artifacts = payload["artifact_paths"]
    recovery_audit = Path(artifacts["recovery_audit_log"])
    quarantine_log = Path(artifacts["quarantine_log"])
    quarantine_manifest = Path(artifacts["quarantine_manifest"])
    known_good = Path(artifacts["known_good_log"])
    restored = Path(artifacts["restored_log"])

    for path in (recovery_audit, quarantine_log, quarantine_manifest, known_good, restored):
        assert path.is_file()
        path.relative_to(base_dir.resolve())

    audit_lines = [
        line for line in recovery_audit.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(audit_lines) == 6

    entries = [json.loads(line) for line in audit_lines]
    event_types = set()
    timestamps = []
    for entry in entries:
        assert REQUIRED_RECOVERY_AUDIT_FIELDS.issubset(entry)
        assert entry["operator_required"] is True
        assert entry["dry_run"] is True
        assert entry["local_only"] is True
        assert entry["silently_repaired"] is False
        assert entry["live_memory_written"] is False
        assert entry["model_called"] is False
        assert entry["embeddings_used"] is False
        assert entry["live_vector_db_written"] is False
        assert entry["account_api_network_accessed"] is False
        assert entry["autonomy_enabled"] is False
        event_types.add(entry["event_type"])
        timestamps.append(str(entry["event_at"]))

    assert EXPECTED_RECOVERY_EVENTS.issubset(event_types)
    assert timestamps == sorted(timestamps)

    # Corrupt log preserved and not repaired.
    corrupt_lines = [
        line for line in quarantine_log.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    malformed = 0
    for line in corrupt_lines:
        try:
            json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
    assert malformed >= 1

    manifest = json.loads(quarantine_manifest.read_text(encoding="utf-8"))
    assert manifest["original_log_path"]
    assert manifest["quarantine_log_path"]
    assert manifest["detected_error_types"]
    assert manifest["dry_run"] is True
    assert manifest["local_only"] is True
    assert manifest["silently_repaired"] is False
    assert manifest["live_memory_written"] is False
    assert manifest["operator_required"] is True

    # Restored from known-good only.
    assert restored.read_text(encoding="utf-8") == known_good.read_text(encoding="utf-8")

    approved_export = Path(artifacts["approved_export"]).read_text(encoding="utf-8")
    assert "rejected-only" not in approved_export

    edited_text = Path(artifacts["edited_text"]).read_text(encoding="utf-8")
    assert "Edited approved memory" in edited_text


def test_recovery_audit_script_has_no_network_ui_or_route_behavior():
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


def test_recovery_audit_script_refuses_repository_root_workspace():
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
