# project_guardian/tests/test_memory_review_decision_tamper_recovery.py

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_decision_tamper_recovery_smoke.py"


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


def test_recovery_smoke_json_cli_passes():
    payload = _run_script()

    assert payload["verdict"] == "PASS"
    assert payload["clean_log_verdict"] == "PASS"
    assert payload["corrupt_log_verdict"] == "FAIL"
    assert payload["corruption_detected"] is True

    assert payload["quarantine_created"] is True
    assert payload["quarantine_manifest_created"] is True
    assert payload["quarantine_log_preserved"] is True
    assert payload["quarantine_errors"]

    assert payload["known_good_resolution_used"] is True
    assert payload["latest_decisions_match_known_good"] is True
    assert payload["corrupt_log_not_trusted"] is True
    assert payload["rejected_still_excluded"] is True
    assert payload["edited_text_still_present"] is True
    assert payload["operator_required"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_recovery_json_contract_fields_present():
    payload = _run_script()
    required_fields = {
        "verdict",
        "workspace",
        "clean_log_verdict",
        "corrupt_log_verdict",
        "corruption_detected",
        "quarantine_created",
        "quarantine_manifest_created",
        "quarantine_log_preserved",
        "quarantine_errors",
        "known_good_resolution_used",
        "latest_decisions_match_known_good",
        "rejected_still_excluded",
        "edited_text_still_present",
        "operator_required",
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


def test_recovery_preserved_workspace_artifacts(tmp_path):
    base_dir = tmp_path / "tamper-recovery"
    payload = _run_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    assert Path(payload["workspace"]) == base_dir.resolve()
    _assert_safety_flags_false(payload)

    artifacts = payload["artifact_paths"]

    # Quarantine directory lives inside the temp workspace.
    quarantine_log = Path(artifacts["quarantine_log"])
    quarantine_manifest = Path(artifacts["quarantine_manifest"])
    known_good = Path(artifacts["known_good_log"])
    restored = Path(artifacts["restored_log"])
    for path in (quarantine_log, quarantine_manifest, known_good, restored):
        assert path.is_file()
        path.relative_to(base_dir.resolve())

    # Corrupt log preserved in quarantine and still corrupt (not repaired).
    corrupt_lines = [
        line
        for line in quarantine_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    malformed = 0
    for line in corrupt_lines:
        try:
            json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
    assert malformed >= 1, "Quarantined log should preserve the malformed content"

    # Manifest contains original/quarantine paths, error types, and safety metadata.
    manifest = json.loads(quarantine_manifest.read_text(encoding="utf-8"))
    assert manifest["original_log_path"]
    assert manifest["quarantine_log_path"]
    assert manifest["detected_error_types"]
    assert manifest["dry_run"] is True
    assert manifest["local_only"] is True
    assert manifest["silently_repaired"] is False
    assert manifest["live_memory_written"] is False
    assert manifest["operator_required"] is True

    # Restored log is well-formed (recovered from known-good, not corrupt).
    restored_lines = [
        line for line in restored.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    for line in restored_lines:
        json.loads(line)
    assert restored.read_text(encoding="utf-8") == known_good.read_text(encoding="utf-8")

    # Rejected content never reaches the approved export.
    approved_export = Path(artifacts["approved_export"]).read_text(encoding="utf-8")
    assert "rejected-only" not in approved_export

    # Edited text preserved.
    edited_text = Path(artifacts["edited_text"]).read_text(encoding="utf-8")
    assert "Edited approved memory" in edited_text


def test_recovery_corrupt_log_not_trusted():
    payload = _run_script()
    assert payload["corrupt_log_not_trusted"] is True
    assert payload["known_good_resolution_used"] is True
    assert payload["latest_decisions_match_known_good"] is True


def test_recovery_script_has_no_network_ui_or_route_behavior():
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


def test_recovery_script_refuses_repository_root_workspace():
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
