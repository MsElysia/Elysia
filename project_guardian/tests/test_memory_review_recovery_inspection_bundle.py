# project_guardian/tests/test_memory_review_recovery_inspection_bundle.py

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_memory_review_recovery_inspection_bundle_smoke.py"


def _run_script(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _assert_safety_flags_false(payload: dict) -> None:
    assert payload["model_called"] is False
    assert payload["embeddings_used"] is False
    assert payload["live_memory_written"] is False
    assert payload["live_vector_db_written"] is False
    assert payload["account_api_network_accessed"] is False
    assert payload["autonomy_enabled"] is False


def test_inspection_bundle_smoke_json_cli_passes():
    payload = _run_script()

    assert payload["verdict"] == "PASS"
    assert payload["bundle_path"]
    assert payload["inspection_summary_path"]
    assert payload["inspection_summary_valid_json"] is True
    assert payload["detected_error_types_present"] is True
    assert payload["detected_error_type_count"] > 0
    assert payload["detected_error_types_match_manifest"] is True
    assert payload["bundle_paths_inside_workspace"] is True
    assert payload["hashes_present"] is True
    assert payload["hashes_match_files"] is True
    assert payload["recovered_event_sequence_present"] is True
    assert payload["recovered_events_match_known_good"] is True
    assert payload["corrupt_log_preserved"] is True
    assert payload["known_good_resolution_used"] is True
    assert payload["silently_repaired"] is False
    assert payload["operator_required"] is True
    assert payload["dry_run"] is True
    assert payload["local_only"] is True
    assert payload["errors"] == []
    _assert_safety_flags_false(payload)


def test_inspection_bundle_json_contract_fields_present():
    payload = _run_script()
    required_fields = {
        "verdict",
        "workspace",
        "bundle_path",
        "inspection_summary_path",
        "inspection_summary_valid_json",
        "detected_error_types_present",
        "detected_error_type_count",
        "detected_error_types_match_manifest",
        "bundle_paths_inside_workspace",
        "hashes_present",
        "hashes_match_files",
        "recovered_event_sequence_present",
        "recovered_events_match_known_good",
        "corrupt_log_preserved",
        "known_good_resolution_used",
        "silently_repaired",
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


def test_inspection_bundle_preserved_workspace_artifacts(tmp_path):
    base_dir = tmp_path / "recovery-inspection-bundle"
    payload = _run_script("--base-dir", str(base_dir))

    assert payload["verdict"] == "PASS"
    assert payload["workspace_preserved"] is True
    workspace = base_dir.resolve()
    assert Path(payload["workspace"]) == workspace
    _assert_safety_flags_false(payload)

    artifacts = payload["artifact_paths"]
    bundle_dir = Path(artifacts["bundle_dir"])
    summary_path = Path(artifacts["inspection_summary"])
    readme_path = Path(artifacts["inspection_readme"])
    quarantine_manifest = Path(artifacts["quarantine_manifest"])
    quarantined_corrupt = Path(artifacts["quarantined_corrupt_log"])
    known_good = Path(artifacts["known_good_recovery_audit"])

    for path in (
        bundle_dir,
        summary_path,
        readme_path,
        quarantine_manifest,
        quarantined_corrupt,
        known_good,
    ):
        assert path.exists()
        path.relative_to(workspace)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(quarantine_manifest.read_text(encoding="utf-8"))
    assert summary["quarantine_manifest_path"] == str(quarantine_manifest.resolve())
    assert summary["quarantined_corrupt_log_path"] == str(quarantined_corrupt.resolve())
    assert summary["known_good_recovery_audit_path"] == str(known_good.resolve())
    assert summary["recovered_event_sequence"]
    assert summary["detected_error_types"]
    assert summary["detected_error_type_count"] == len(summary["detected_error_types"])
    assert summary["detected_error_types_match_manifest"] is True
    assert summary["detected_error_types"] == manifest["detected_error_types"]
    assert "malformed_json" in summary["detected_error_types"]
    assert "unsafe_metadata" in summary["detected_error_types"]
    assert summary["corrupt_log_sha256"] == _sha256_file(quarantined_corrupt)
    assert summary["known_good_recovery_audit_sha256"] == _sha256_file(known_good)
    assert summary["quarantine_manifest_sha256"] == _sha256_file(quarantine_manifest)
    assert summary["corrupt_log_preserved"] is True
    assert summary["known_good_resolution_used"] is True
    assert summary["recovered_events_match_known_good"] is True
    assert summary["silently_repaired"] is False
    assert summary["operator_required"] is True
    assert summary["dry_run"] is True
    assert summary["local_only"] is True
    assert summary["model_called"] is False
    assert summary["embeddings_used"] is False
    assert summary["live_memory_written"] is False
    assert summary["live_vector_db_written"] is False
    assert summary["account_api_network_accessed"] is False
    assert summary["autonomy_enabled"] is False

    known_good_events = [
        json.loads(line).get("event_type")
        for line in known_good.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert summary["recovered_event_sequence"] == known_good_events


def test_inspection_bundle_script_has_no_network_ui_or_route_behavior():
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


def test_inspection_bundle_script_refuses_repository_root_workspace():
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
