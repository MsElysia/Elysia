#!/usr/bin/env python3
"""Dry-run/local smoke proving safe recovery from a corrupted recovery audit log.

This smoke builds a valid ``recovery_audit.jsonl`` from the existing recovery
audit-trail flow in a temp workspace, saves a known-good copy, then corrupts
the working log (malformed JSON plus unsafe metadata). It proves the corruption
is detected, quarantines the corrupt log into a temp-only quarantine directory
with a manifest, preserves the corrupt content for inspection, and re-resolves
recovery audit state from the known-good copy only. It proves the corrupt log
is never trusted for recovery audit validation. It never calls models,
embeddings, networks, live accounts, or live runtime memory/vector DB.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_recovery_audit_tamper_evidence_smoke import (  # noqa: E402
    audit_recovery_log,
)
from run_memory_review_recovery_audit_trail_smoke import (  # noqa: E402
    RECOVERY_AUDIT_FILENAME,
    run_memory_review_recovery_audit_trail_smoke,
)


@dataclass
class RecoveryAuditTamperRecoveryReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    clean_recovery_audit_verdict: str = "UNKNOWN"
    corrupt_recovery_audit_verdict: str = "UNKNOWN"
    corruption_detected: bool = False
    quarantine_created: bool = False
    quarantine_manifest_created: bool = False
    quarantine_log_preserved: bool = False
    quarantine_errors: List[str] = field(default_factory=list)
    known_good_recovery_audit_used: bool = False
    recovered_events_match_known_good: bool = False
    corrupt_recovery_audit_not_trusted: bool = False
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


def _error_tokens(errors: Sequence[str]) -> List[str]:
    tokens = (
        "malformed_json",
        "missing_required_field",
        "non_chronological",
        "unsupported_event",
        "unsafe_metadata",
    )
    found: List[str] = []
    for token in tokens:
        if any(token in err for err in errors):
            found.append(token)
    return found


def _event_sequence(log_path: Path) -> List[str]:
    entries = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [str(entry.get("event_type") or "") for entry in entries]


def _build_clean_recovery_audit_log(workspace: Path) -> Tuple[Path, List[Dict[str, Any]]]:
    trail_report = run_memory_review_recovery_audit_trail_smoke(
        base_dir=workspace,
        keep_temp=True,
    )
    if trail_report.verdict != "PASS":
        raise ValueError(
            "Recovery audit trail smoke did not pass while building clean log: "
            + "; ".join(trail_report.errors)
        )
    clean_path = workspace / RECOVERY_AUDIT_FILENAME
    if not clean_path.is_file():
        raise ValueError(f"Clean recovery audit log was not created: {clean_path}")
    clean_entries = [
        json.loads(line)
        for line in clean_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return clean_path, clean_entries


def _run_recovery_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> RecoveryAuditTamperRecoveryReport:
    errors: List[str] = []
    report = RecoveryAuditTamperRecoveryReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; recovery audit tamper recovery smoke is blocked.")
        return report

    recovery_audit_path, clean_entries = _build_clean_recovery_audit_log(workspace)

    known_good_dir = workspace / "known_good"
    known_good_dir.mkdir(parents=True, exist_ok=True)
    known_good_path = known_good_dir / RECOVERY_AUDIT_FILENAME
    shutil.copy2(recovery_audit_path, known_good_path)

    clean_verdict, clean_errors = audit_recovery_log(known_good_path)
    report.clean_recovery_audit_verdict = clean_verdict
    known_good_events = _event_sequence(known_good_path)
    if clean_verdict != "PASS" or clean_errors:
        errors.append(f"Clean recovery audit log did not pass: {clean_errors}")
    if not known_good_events:
        errors.append("Known-good recovery audit log had no events.")

    unsafe_entry = dict(clean_entries[-1])
    unsafe_entry["event_at"] = "2999-01-01T00:00:00+00:00"
    unsafe_entry["dry_run"] = False
    corrupt_lines = [json.dumps(entry, ensure_ascii=False) for entry in clean_entries]
    corrupt_lines.append("{ corrupt recovery audit line not valid json")
    corrupt_lines.append(json.dumps(unsafe_entry, ensure_ascii=False))
    recovery_audit_path.write_text(
        "\n".join(corrupt_lines) + "\n", encoding="utf-8", newline="\n"
    )

    corrupt_verdict, corrupt_errors = audit_recovery_log(recovery_audit_path)
    report.corrupt_recovery_audit_verdict = corrupt_verdict
    report.quarantine_errors = _error_tokens(corrupt_errors)
    report.corruption_detected = corrupt_verdict == "FAIL" and bool(corrupt_errors)

    corrupt_content = recovery_audit_path.read_text(encoding="utf-8")
    report.corrupt_recovery_audit_not_trusted = corrupt_verdict == "FAIL"

    quarantine_dir = workspace / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    quarantine_log = quarantine_dir / "recovery_audit.corrupt.jsonl"
    shutil.copy2(recovery_audit_path, quarantine_log)
    report.quarantine_created = quarantine_dir.is_dir()
    report.quarantine_log_preserved = (
        quarantine_log.is_file()
        and quarantine_log.read_text(encoding="utf-8") == corrupt_content
    )

    manifest = {
        "original_recovery_audit_path": str(recovery_audit_path.resolve()),
        "quarantine_recovery_audit_path": str(quarantine_log.resolve()),
        "known_good_recovery_audit_path": str(known_good_path.resolve()),
        "detected_error_types": report.quarantine_errors,
        "quarantine_timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": True,
        "local_only": True,
        "silently_repaired": False,
        "operator_required": True,
        "live_memory_written": False,
        "model_called": False,
        "embeddings_used": False,
        "live_vector_db_written": False,
        "account_api_network_accessed": False,
        "autonomy_enabled": False,
    }
    manifest_path = quarantine_dir / "recovery_audit_quarantine_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    report.quarantine_manifest_created = manifest_path.is_file()
    report.operator_required = bool(manifest.get("operator_required"))
    report.dry_run = bool(manifest.get("dry_run"))
    report.local_only = bool(manifest.get("local_only"))
    report.silently_repaired = bool(manifest.get("silently_repaired"))

    shutil.copy2(known_good_path, recovery_audit_path)
    report.known_good_recovery_audit_used = True
    recovered_verdict, recovered_errors = audit_recovery_log(recovery_audit_path)
    recovered_events = _event_sequence(recovery_audit_path)
    report.recovered_events_match_known_good = (
        recovered_verdict == "PASS"
        and not recovered_errors
        and recovered_events == known_good_events
    )

    report.artifact_paths = {
        "known_good_recovery_audit": str(known_good_path.resolve()),
        "restored_recovery_audit": str(recovery_audit_path.resolve()),
        "quarantine_recovery_audit": str(quarantine_log.resolve()),
        "quarantine_manifest": str(manifest_path.resolve()),
    }

    if not report.corruption_detected:
        errors.append("Corruption was not detected before recovery.")
    if not report.quarantine_errors:
        errors.append("No specific corruption error types were captured.")
    if not report.quarantine_created:
        errors.append("Quarantine directory was not created.")
    if not report.quarantine_log_preserved:
        errors.append("Corrupt recovery audit log content was not preserved in quarantine.")
    if not report.quarantine_manifest_created:
        errors.append("Quarantine manifest was not created.")
    if not report.corrupt_recovery_audit_not_trusted:
        errors.append("Corrupt recovery audit log was trusted for recovery validation.")
    if not report.known_good_recovery_audit_used:
        errors.append("Recovery did not use the known-good recovery audit copy.")
    if not report.recovered_events_match_known_good:
        errors.append("Recovered recovery audit events did not match the known-good state.")
    if report.silently_repaired:
        errors.append("Recovery audit log was silently repaired.")
    if not report.operator_required:
        errors.append("Quarantine manifest did not mark operator_required.")
    if not report.dry_run:
        errors.append("Quarantine manifest did not mark dry_run.")
    if not report.local_only:
        errors.append("Quarantine manifest did not mark local_only.")

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


def run_memory_review_recovery_audit_tamper_recovery_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> RecoveryAuditTamperRecoveryReport:
    """Prove safe quarantine and known-good recovery from a corrupted recovery audit log."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_recovery_audit_tamper_recovery_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        return _run_recovery_flow(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: RecoveryAuditTamperRecoveryReport) -> str:
    lines = [
        "Memory review recovery audit tamper recovery smoke",
        "=" * 50,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Clean recovery audit verdict: {report.clean_recovery_audit_verdict}",
        f"Corrupt recovery audit verdict: {report.corrupt_recovery_audit_verdict}",
        f"Corruption detected: {report.corruption_detected}",
        f"Quarantine errors: {', '.join(report.quarantine_errors) or 'none'}",
        "",
        "Recovery:",
        f"  quarantine created: {report.quarantine_created}",
        f"  quarantine log preserved: {report.quarantine_log_preserved}",
        f"  quarantine manifest created: {report.quarantine_manifest_created}",
        f"  corrupt recovery audit not trusted: {report.corrupt_recovery_audit_not_trusted}",
        f"  known-good recovery audit used: {report.known_good_recovery_audit_used}",
        f"  recovered events match known-good: {report.recovered_events_match_known_good}",
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
        description="Run local-only Memory review recovery audit tamper recovery smoke.",
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
        report = run_memory_review_recovery_audit_tamper_recovery_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = RecoveryAuditTamperRecoveryReport(
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
