#!/usr/bin/env python3
"""Dry-run/local smoke producing an operator inspection bundle after recovery.

This smoke runs the existing recovery-audit tamper-recovery flow in a temp
workspace, then writes a ``recovery_inspection_bundle/`` directory with an
operator-readable inspection summary (paths, recovered event sequence, SHA-256
hashes, and safety metadata). It never calls models, embeddings, networks,
live accounts, or live runtime memory/vector DB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_recovery_audit_tamper_recovery_smoke import (  # noqa: E402
    run_memory_review_recovery_audit_tamper_recovery_smoke,
)

BUNDLE_DIRNAME = "recovery_inspection_bundle"
SUMMARY_FILENAME = "inspection_summary.json"
README_FILENAME = "README.md"


@dataclass
class InspectionBundleReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    bundle_path: str = ""
    inspection_summary_path: str = ""
    inspection_summary_valid_json: bool = False
    detected_error_types_present: bool = False
    detected_error_type_count: int = 0
    detected_error_types_match_manifest: bool = False
    bundle_paths_inside_workspace: bool = False
    hashes_present: bool = False
    hashes_match_files: bool = False
    recovered_event_sequence_present: bool = False
    recovered_events_match_known_good: bool = False
    corrupt_log_preserved: bool = False
    known_good_resolution_used: bool = False
    silently_repaired: bool = False
    operator_required: bool = False
    dry_run: bool = True
    local_only: bool = True
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    live_vector_db_written: bool = False
    account_api_network_accessed: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _repo_root() -> Path:
    return PROJECT_ROOT.resolve()


def _read_autonomy_enabled() -> bool:
    path = _repo_root() / "config" / "autonomy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("enabled"))


def _reject_dangerous_base(base_dir: Path) -> Path:
    resolved = base_dir.expanduser().resolve()
    repo_root = _repo_root()
    home = Path.home().resolve()
    if resolved == resolved.parent:
        raise ValueError(f"Refusing to use filesystem root as smoke workspace: {resolved}")
    if resolved == home:
        raise ValueError(f"Refusing to use home directory as smoke workspace: {resolved}")
    if resolved == repo_root:
        raise ValueError(f"Refusing to use repository root as smoke workspace: {resolved}")
    if resolved.anchor and str(resolved) == resolved.anchor:
        raise ValueError(f"Refusing to use drive root as smoke workspace: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"Smoke workspace exists but is not a directory: {resolved}")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _event_sequence(log_path: Path) -> List[str]:
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [str(entry.get("event_type") or "") for entry in entries]


def _path_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _write_readme(bundle_dir: Path, summary: Dict[str, Any]) -> Path:
    readme_path = bundle_dir / README_FILENAME
    lines = [
        "# Recovery Inspection Bundle",
        "",
        "Dry-run/local operator inspection bundle for recovery-audit tamper-recovery.",
        "",
        f"- Workspace: `{summary.get('workspace', '')}`",
        f"- Bundle path: `{summary.get('bundle_path', '')}`",
        f"- Quarantine manifest: `{summary.get('quarantine_manifest_path', '')}`",
        f"- Quarantined corrupt log: `{summary.get('quarantined_corrupt_log_path', '')}`",
        f"- Known-good recovery audit: `{summary.get('known_good_recovery_audit_path', '')}`",
        "",
        "## Recovered event sequence",
        "",
    ]
    for event in summary.get("recovered_event_sequence") or []:
        lines.append(f"- `{event}`")
    lines.extend(
        [
            "",
            "## Detected error types",
            "",
            f"- Count: `{summary.get('detected_error_type_count', 0)}`",
            f"- Match manifest: `{summary.get('detected_error_types_match_manifest')}`",
        ]
    )
    for error_type in summary.get("detected_error_types") or []:
        lines.append(f"- `{error_type}`")
    lines.extend(
        [
            "",
            "## SHA-256 hashes",
            "",
            f"- Corrupt log: `{summary.get('corrupt_log_sha256', '')}`",
            f"- Known-good recovery audit: `{summary.get('known_good_recovery_audit_sha256', '')}`",
            f"- Quarantine manifest: `{summary.get('quarantine_manifest_sha256', '')}`",
            "",
            "## Safety",
            "",
            f"- dry_run: `{summary.get('dry_run')}`",
            f"- local_only: `{summary.get('local_only')}`",
            f"- silently_repaired: `{summary.get('silently_repaired')}`",
            f"- operator_required: `{summary.get('operator_required')}`",
            "",
            "Recovery used known-good clean data only. The corrupt log was preserved",
            "for inspection and was not silently repaired.",
        ]
    )
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return readme_path


def _build_inspection_bundle(workspace: Path) -> InspectionBundleReport:
    errors: List[str] = []
    report = InspectionBundleReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=True,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; recovery inspection bundle smoke is blocked.")
        return report

    recovery_report = run_memory_review_recovery_audit_tamper_recovery_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    if recovery_report.verdict != "PASS":
        errors.append(
            "Recovery-audit tamper-recovery smoke did not pass: "
            + "; ".join(recovery_report.errors)
        )

    artifacts = recovery_report.artifact_paths
    quarantine_manifest_path = Path(artifacts["quarantine_manifest"])
    quarantined_corrupt_log_path = Path(artifacts["quarantine_recovery_audit"])
    known_good_path = Path(artifacts["known_good_recovery_audit"])
    restored_path = Path(artifacts["restored_recovery_audit"])

    bundle_dir = workspace / BUNDLE_DIRNAME
    bundle_dir.mkdir(parents=True, exist_ok=True)
    report.bundle_path = str(bundle_dir.resolve())

    known_good_events = _event_sequence(known_good_path)
    recovered_events = _event_sequence(restored_path)

    corrupt_hash = _sha256_file(quarantined_corrupt_log_path)
    known_good_hash = _sha256_file(known_good_path)
    manifest_hash = _sha256_file(quarantine_manifest_path)

    manifest_payload = json.loads(quarantine_manifest_path.read_text(encoding="utf-8"))
    manifest_error_types = list(manifest_payload.get("detected_error_types") or [])
    detected_error_types = list(manifest_error_types)
    detected_error_type_count = len(detected_error_types)
    detected_error_types_match_manifest = detected_error_types == manifest_error_types

    inspection_notes = [
        "Dry-run/local recovery inspection bundle.",
        "Corrupt recovery audit log preserved byte-for-byte in quarantine.",
        "Recovery audit state re-resolved from known-good copy only.",
        "No silent repair occurred.",
    ]

    summary: Dict[str, Any] = {
        "verdict": "PASS",
        "workspace": report.workspace,
        "bundle_path": report.bundle_path,
        "quarantine_manifest_path": str(quarantine_manifest_path.resolve()),
        "quarantined_corrupt_log_path": str(quarantined_corrupt_log_path.resolve()),
        "known_good_recovery_audit_path": str(known_good_path.resolve()),
        "recovered_event_sequence": recovered_events,
        "detected_error_types": detected_error_types,
        "detected_error_type_count": detected_error_type_count,
        "detected_error_types_match_manifest": detected_error_types_match_manifest,
        "corrupt_log_sha256": corrupt_hash,
        "known_good_recovery_audit_sha256": known_good_hash,
        "quarantine_manifest_sha256": manifest_hash,
        "corrupt_log_preserved": recovery_report.quarantine_log_preserved,
        "known_good_resolution_used": recovery_report.known_good_recovery_audit_used,
        "recovered_events_match_known_good": recovery_report.recovered_events_match_known_good,
        "silently_repaired": False,
        "operator_required": True,
        "dry_run": True,
        "local_only": True,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "live_vector_db_written": False,
        "account_api_network_accessed": False,
        "autonomy_enabled": False,
        "inspection_notes": inspection_notes,
        "errors": [],
    }

    summary_path = bundle_dir / SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    readme_path = _write_readme(bundle_dir, summary)

    report.inspection_summary_path = str(summary_path.resolve())
    report.inspection_summary_valid_json = True
    try:
        loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        report.inspection_summary_valid_json = isinstance(loaded, dict)
        summary = loaded
    except json.JSONDecodeError:
        report.inspection_summary_valid_json = False
        errors.append("Inspection summary is not valid JSON.")

    report.detected_error_types_present = bool(summary.get("detected_error_types"))
    report.detected_error_type_count = int(summary.get("detected_error_type_count") or 0)
    report.detected_error_types_match_manifest = bool(
        summary.get("detected_error_types_match_manifest")
    )

    path_checks = (
        bundle_dir,
        summary_path,
        readme_path,
        quarantine_manifest_path,
        quarantined_corrupt_log_path,
        known_good_path,
        restored_path,
    )
    report.bundle_paths_inside_workspace = all(
        _path_inside_workspace(path, workspace) for path in path_checks
    )

    report.hashes_present = bool(
        summary.get("corrupt_log_sha256")
        and summary.get("known_good_recovery_audit_sha256")
        and summary.get("quarantine_manifest_sha256")
    )
    report.hashes_match_files = (
        summary.get("corrupt_log_sha256") == _sha256_file(quarantined_corrupt_log_path)
        and summary.get("known_good_recovery_audit_sha256") == _sha256_file(known_good_path)
        and summary.get("quarantine_manifest_sha256") == _sha256_file(quarantine_manifest_path)
    )
    report.recovered_event_sequence_present = bool(recovered_events)
    report.recovered_events_match_known_good = (
        recovered_events == known_good_events
        and recovery_report.recovered_events_match_known_good
    )
    report.corrupt_log_preserved = recovery_report.quarantine_log_preserved
    report.known_good_resolution_used = recovery_report.known_good_recovery_audit_used
    report.silently_repaired = bool(summary.get("silently_repaired"))
    report.operator_required = bool(summary.get("operator_required"))
    report.dry_run = bool(summary.get("dry_run"))
    report.local_only = bool(summary.get("local_only"))

    report.artifact_paths = {
        "bundle_dir": report.bundle_path,
        "inspection_summary": report.inspection_summary_path,
        "inspection_readme": str(readme_path.resolve()),
        "quarantine_manifest": str(quarantine_manifest_path.resolve()),
        "quarantined_corrupt_log": str(quarantined_corrupt_log_path.resolve()),
        "known_good_recovery_audit": str(known_good_path.resolve()),
        "restored_recovery_audit": str(restored_path.resolve()),
    }

    if not bundle_dir.is_dir():
        errors.append("Inspection bundle directory was not created.")
    if not summary_path.is_file():
        errors.append("Inspection summary was not created.")
    if not report.inspection_summary_valid_json:
        errors.append("Inspection summary is not valid JSON.")
    if not report.detected_error_types_present:
        errors.append("Inspection summary is missing detected_error_types.")
    if report.detected_error_type_count <= 0:
        errors.append("Inspection summary detected_error_type_count is not positive.")
    if summary.get("detected_error_type_count") != len(summary.get("detected_error_types") or []):
        errors.append("Inspection summary detected_error_type_count does not match error types.")
    if not report.detected_error_types_match_manifest:
        errors.append("Inspection summary detected_error_types do not match manifest.")
    if summary.get("detected_error_types") != manifest_error_types:
        errors.append("Inspection summary error types were not copied from manifest.")
    if not report.bundle_paths_inside_workspace:
        errors.append("One or more bundle paths are outside the temp workspace.")
    if not report.hashes_present:
        errors.append("Inspection summary is missing SHA-256 hashes.")
    if not report.hashes_match_files:
        errors.append("Inspection summary hashes do not match artifact files.")
    if not report.recovered_event_sequence_present:
        errors.append("Recovered event sequence is missing.")
    if not report.recovered_events_match_known_good:
        errors.append("Recovered event sequence does not match known-good state.")
    if not report.corrupt_log_preserved:
        errors.append("Corrupt recovery audit log was not preserved.")
    if not report.known_good_resolution_used:
        errors.append("Known-good recovery audit was not used.")
    if report.silently_repaired:
        errors.append("Inspection summary indicates silent repair.")
    if not report.operator_required:
        errors.append("Inspection summary did not mark operator_required.")
    if not report.dry_run:
        errors.append("Inspection summary did not mark dry_run.")
    if not report.local_only:
        errors.append("Inspection summary did not mark local_only.")

    for flag_name in (
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name):
            errors.append(f"{flag_name} unexpectedly true.")

    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    return report


def run_memory_review_recovery_inspection_bundle_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> InspectionBundleReport:
    """Build a dry-run operator inspection bundle after recovery-audit tamper-recovery."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_recovery_inspection_bundle_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        report = _build_inspection_bundle(workspace)
        report.workspace_preserved = (not owned_temp) or keep_temp
        return report
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: InspectionBundleReport) -> str:
    lines = [
        "Memory review recovery inspection bundle smoke",
        "=" * 50,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Bundle path: {report.bundle_path}",
        f"Inspection summary: {report.inspection_summary_path}",
        "",
        "Bundle checks:",
        f"  summary valid JSON: {report.inspection_summary_valid_json}",
        f"  detected error types present: {report.detected_error_types_present}",
        f"  detected error type count: {report.detected_error_type_count}",
        f"  detected error types match manifest: {report.detected_error_types_match_manifest}",
        f"  paths inside workspace: {report.bundle_paths_inside_workspace}",
        f"  hashes present: {report.hashes_present}",
        f"  hashes match files: {report.hashes_match_files}",
        f"  recovered event sequence present: {report.recovered_event_sequence_present}",
        f"  recovered events match known-good: {report.recovered_events_match_known_good}",
        f"  corrupt log preserved: {report.corrupt_log_preserved}",
        f"  known-good resolution used: {report.known_good_resolution_used}",
        f"  silently_repaired: {report.silently_repaired}",
        f"  operator_required: {report.operator_required}",
        f"  dry_run: {report.dry_run}",
        f"  local_only: {report.local_only}",
        "",
        "Safety:",
        f"  model_called: {report.model_called}",
        f"  embeddings_used: {report.embeddings_used}",
        f"  live_memory_written: {report.live_memory_written}",
        f"  live_vector_db_written: {report.live_vector_db_written}",
        f"  account_api_network_accessed: {report.account_api_network_accessed}",
        f"  autonomy_enabled: {report.autonomy_enabled}",
    ]
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run local-only Memory review recovery inspection bundle smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON smoke result")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Optional workspace root. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve an automatically-created temporary workspace.",
    )
    args = parser.parse_args(argv)

    try:
        report = run_memory_review_recovery_inspection_bundle_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = InspectionBundleReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
