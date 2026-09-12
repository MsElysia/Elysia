#!/usr/bin/env python3
"""Dry-run/local smoke proving the recovery audit checker detects tampering.

This smoke builds a valid ``recovery_audit.jsonl`` from the existing recovery
audit-trail flow in a temp workspace, then writes tampered copies (malformed
JSON line, missing required field, out-of-order timestamp, unsupported recovery
event type, and unsafe metadata) and runs a self-contained, local-only audit
checker against each. It verifies the clean log passes and every tampered log
fails with a specific error message. It never calls models, embeddings,
networks, live accounts, or live runtime memory/vector DB.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_recovery_audit_trail_smoke import (  # noqa: E402
    EXPECTED_RECOVERY_EVENTS,
    RECOVERY_AUDIT_FILENAME,
    REQUIRED_RECOVERY_AUDIT_FIELDS,
    run_memory_review_recovery_audit_trail_smoke,
)

ALLOWED_RECOVERY_EVENT_TYPES = frozenset(EXPECTED_RECOVERY_EVENTS)

UNSAFE_METADATA_CHECKS = (
    ("operator_required", False, "operator_required=false"),
    ("dry_run", False, "dry_run=false"),
    ("local_only", False, "local_only=false"),
    ("silently_repaired", True, "silently_repaired=true"),
    ("live_memory_written", True, "live_memory_written=true"),
    ("model_called", True, "model_called=true"),
    ("embeddings_used", True, "embeddings_used=true"),
    ("live_vector_db_written", True, "live_vector_db_written=true"),
    ("account_api_network_accessed", True, "account_api_network_accessed=true"),
    ("autonomy_enabled", True, "autonomy_enabled=true"),
)


@dataclass
class TamperCaseResult:
    name: str
    verdict: str
    expected_token: str
    token_found: bool
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryAuditTamperEvidenceReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    clean_log_verdict: str = "UNKNOWN"
    tampered_cases_run: int = 0
    malformed_json_detected: bool = False
    missing_required_field_detected: bool = False
    non_chronological_detected: bool = False
    unsupported_event_detected: bool = False
    unsafe_metadata_detected: bool = False
    specific_errors_present: bool = False
    clean_log_still_passes: bool = False
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    live_vector_db_written: bool = False
    account_api_network_accessed: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    cases: List[Dict[str, Any]] = field(default_factory=list)

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


def audit_recovery_log(log_path: Path) -> Tuple[str, List[str]]:
    """Local-only audit checker for a recovery_audit.jsonl log.

    Returns a (verdict, errors) tuple. Detects malformed JSON, missing required
    fields, unsupported recovery event types, unsafe metadata, and
    non-chronological timestamps. No network/model/memory access is performed.
    """
    errors: List[str] = []
    if not log_path.is_file():
        return "FAIL", [f"missing_log_file: {log_path}"]

    raw_lines = [
        line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not raw_lines:
        return "FAIL", ["empty_log_file: no recovery audit entries found"]

    entries: List[Dict[str, Any]] = []
    for line_no, line in enumerate(raw_lines, start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"malformed_json: line {line_no} is not valid JSON ({exc})")
            continue
        if not isinstance(item, dict):
            errors.append(f"malformed_json: line {line_no} is not a JSON object")
            continue

        missing = [name for name in REQUIRED_RECOVERY_AUDIT_FIELDS if name not in item]
        if missing:
            errors.append(
                f"missing_required_field: line {line_no} missing {', '.join(missing)}"
            )

        event_type = str(item.get("event_type") or "").strip()
        if event_type and event_type not in ALLOWED_RECOVERY_EVENT_TYPES:
            errors.append(
                f"unsupported_event: line {line_no} event_type={event_type!r}"
            )

        for field_name, unsafe_value, label in UNSAFE_METADATA_CHECKS:
            if field_name in item and item.get(field_name) is unsafe_value:
                errors.append(f"unsafe_metadata: line {line_no} {label}")

        entries.append(item)

    timestamps = [
        str(entry.get("event_at") or "") for entry in entries if str(entry.get("event_at") or "")
    ]
    for index in range(1, len(timestamps)):
        if timestamps[index] < timestamps[index - 1]:
            errors.append(
                "non_chronological: entry "
                f"{index + 1} timestamp {timestamps[index]!r} precedes "
                f"{timestamps[index - 1]!r}"
            )
            break

    verdict = "PASS" if not errors else "FAIL"
    return verdict, errors


def _write_log(
    path: Path,
    entries: Sequence[Dict[str, Any]],
    *,
    extra_raw_lines: Sequence[str] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    lines.extend(extra_raw_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


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


def _run_tamper_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> RecoveryAuditTamperEvidenceReport:
    errors: List[str] = []
    report = RecoveryAuditTamperEvidenceReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; recovery audit tamper evidence smoke is blocked.")
        return report

    clean_log_path, clean_entries = _build_clean_recovery_audit_log(workspace)
    tamper_dir = workspace / "tampered"
    tamper_dir.mkdir(parents=True, exist_ok=True)

    clean_verdict, clean_errors = audit_recovery_log(clean_log_path)
    report.clean_log_verdict = clean_verdict
    report.clean_log_still_passes = clean_verdict == "PASS" and not clean_errors
    if not report.clean_log_still_passes:
        errors.append(f"Clean recovery audit log did not pass: {clean_errors}")

    template = dict(clean_entries[-1])

    def _future_entry(**overrides: Any) -> Dict[str, Any]:
        entry = dict(template)
        entry["event_at"] = "2999-01-01T00:00:00+00:00"
        entry.update(overrides)
        return entry

    missing_field_entry = _future_entry()
    missing_field_entry.pop("event_type", None)

    non_chrono_entry = dict(template)
    non_chrono_entry["event_at"] = "2000-01-01T00:00:00+00:00"

    unsupported_entry = _future_entry(event_type="invalid_recovery_action")

    unsafe_entry = _future_entry(dry_run=False)

    cases: List[TamperCaseResult] = []

    malformed_path = tamper_dir / "malformed_json.jsonl"
    _write_log(malformed_path, clean_entries, extra_raw_lines=["{ this is not valid json"])
    verdict, case_errors = audit_recovery_log(malformed_path)
    token_found = any("malformed_json" in err for err in case_errors)
    cases.append(TamperCaseResult("malformed_json", verdict, "malformed_json", token_found, case_errors))
    report.malformed_json_detected = verdict == "FAIL" and token_found

    missing_path = tamper_dir / "missing_field.jsonl"
    _write_log(missing_path, [*clean_entries, missing_field_entry])
    verdict, case_errors = audit_recovery_log(missing_path)
    token_found = any("missing_required_field" in err for err in case_errors)
    cases.append(
        TamperCaseResult("missing_field", verdict, "missing_required_field", token_found, case_errors)
    )
    report.missing_required_field_detected = verdict == "FAIL" and token_found

    non_chrono_path = tamper_dir / "non_chronological.jsonl"
    _write_log(non_chrono_path, [*clean_entries, non_chrono_entry])
    verdict, case_errors = audit_recovery_log(non_chrono_path)
    token_found = any("non_chronological" in err for err in case_errors)
    cases.append(
        TamperCaseResult("non_chronological", verdict, "non_chronological", token_found, case_errors)
    )
    report.non_chronological_detected = verdict == "FAIL" and token_found

    unsupported_path = tamper_dir / "unsupported_event.jsonl"
    _write_log(unsupported_path, [*clean_entries, unsupported_entry])
    verdict, case_errors = audit_recovery_log(unsupported_path)
    token_found = any("unsupported_event" in err for err in case_errors)
    cases.append(
        TamperCaseResult("unsupported_event", verdict, "unsupported_event", token_found, case_errors)
    )
    report.unsupported_event_detected = verdict == "FAIL" and token_found

    unsafe_path = tamper_dir / "unsafe_metadata.jsonl"
    _write_log(unsafe_path, [*clean_entries, unsafe_entry])
    verdict, case_errors = audit_recovery_log(unsafe_path)
    token_found = any("unsafe_metadata" in err for err in case_errors)
    cases.append(
        TamperCaseResult("unsafe_metadata", verdict, "unsafe_metadata", token_found, case_errors)
    )
    report.unsafe_metadata_detected = verdict == "FAIL" and token_found

    report.tampered_cases_run = len(cases)
    report.cases = [case.to_dict() for case in cases]

    all_failed = all(case.verdict == "FAIL" for case in cases)
    report.specific_errors_present = all(case.token_found for case in cases)

    reverify_verdict, reverify_errors = audit_recovery_log(clean_log_path)
    if reverify_verdict != "PASS" or reverify_errors:
        report.clean_log_still_passes = False
        errors.append(f"Clean recovery audit log regressed after tamper cases: {reverify_errors}")

    required_detections = (
        report.malformed_json_detected
        and report.missing_required_field_detected
        and report.non_chronological_detected
    )
    optional_detections = (
        report.unsupported_event_detected and report.unsafe_metadata_detected
    )

    if not report.clean_log_still_passes:
        errors.append("Clean recovery audit log did not remain PASS.")
    if not required_detections:
        errors.append(
            "A required tamper case (malformed/missing/non-chronological) was not detected."
        )
    if not optional_detections:
        errors.append(
            "An optional tamper case (unsupported event/unsafe metadata) was not detected."
        )
    if not all_failed:
        errors.append("A tampered log did not return verdict=FAIL.")
    if not report.specific_errors_present:
        errors.append("A tamper case did not produce a specific error token.")

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


def run_memory_review_recovery_audit_tamper_evidence_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> RecoveryAuditTamperEvidenceReport:
    """Build a clean recovery audit log and prove the checker detects tampering."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_recovery_audit_tamper_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        return _run_tamper_flow(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: RecoveryAuditTamperEvidenceReport) -> str:
    lines = [
        "Memory review recovery audit tamper evidence smoke",
        "=" * 48,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Clean log verdict: {report.clean_log_verdict}",
        f"Clean log still passes: {report.clean_log_still_passes}",
        f"Tampered cases run: {report.tampered_cases_run}",
        "",
        "Detections:",
        f"  malformed_json: {report.malformed_json_detected}",
        f"  missing_required_field: {report.missing_required_field_detected}",
        f"  non_chronological: {report.non_chronological_detected}",
        f"  unsupported_event: {report.unsupported_event_detected}",
        f"  unsafe_metadata: {report.unsafe_metadata_detected}",
        f"  specific errors present: {report.specific_errors_present}",
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
        description="Run local-only Memory review recovery audit tamper evidence smoke.",
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
        report = run_memory_review_recovery_audit_tamper_evidence_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = RecoveryAuditTamperEvidenceReport(
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
