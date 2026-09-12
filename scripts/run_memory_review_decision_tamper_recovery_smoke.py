#!/usr/bin/env python3
"""Dry-run/local smoke proving safe recovery from a corrupted review decision log.

This smoke builds a valid append-only ``review_decisions.jsonl`` from local
fixtures in a temp workspace, saves a known-good copy, then corrupts the working
log (malformed JSON plus a missing required field). It proves the corruption is
detected, quarantines the corrupt log into a temp-only quarantine directory with
a manifest, preserves the corrupt content for inspection, and re-resolves the
latest review decisions from the known-good copy only. It proves the corrupt log
is never trusted for latest-decision resolution, that rejected candidates stay
excluded, and that edited text stays preserved. It never calls models,
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
from typing import Any, Dict, List, Sequence, Set, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_memory_review_decision_tamper_evidence_smoke import (  # noqa: E402
    audit_decision_log,
)

from project_guardian.local_ingestion.approved_memory_export import (  # noqa: E402
    export_approved_memory_candidates,
)
from project_guardian.local_ingestion.memory_candidate_review import (  # noqa: E402
    MemoryCandidateReviewError,
    approve_candidate,
    edit_candidate,
    find_latest_edited_text_path,
    list_candidates,
    load_all_decisions,
    load_latest_decisions,
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.unified_memory_import import (  # noqa: E402
    SOURCE_TYPE_TRANSCRIPTION,
    unified_apply_memory_import,
    unified_preview_memory_import,
)

EDITED_TEXT = (
    "Edited approved memory: kitchen countertop measurement is 42 inches and "
    "the revised tile color is blue."
)
REJECTED_MARKER = "rejected-only"


@dataclass
class _DecisionIds:
    approve: str
    reject: str
    edit: str

    def as_set(self) -> Set[str]:
        return {self.approve, self.reject, self.edit}


@dataclass
class TamperRecoveryReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    clean_log_verdict: str = "UNKNOWN"
    corrupt_log_verdict: str = "UNKNOWN"
    corruption_detected: bool = False
    quarantine_created: bool = False
    quarantine_manifest_created: bool = False
    quarantine_log_preserved: bool = False
    quarantine_errors: List[str] = field(default_factory=list)
    known_good_resolution_used: bool = False
    latest_decisions_match_known_good: bool = False
    corrupt_log_not_trusted: bool = False
    rejected_still_excluded: bool = False
    edited_text_still_present: bool = False
    operator_required: bool = False
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


def _write_fixture_sources(source_dir: Path) -> List[Path]:
    source_dir.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "approve_branch.txt": (
            "Approve branch fixture: kitchen cabinet measurements are ready for the estimate."
        ),
        "reject_branch.txt": (
            "Reject branch fixture: rejected-only note should never reach approved search output."
        ),
        "edit_branch.txt": (
            "Edit branch fixture: kitchen countertop measurement needs operator correction."
        ),
    }
    paths: List[Path] = []
    for name, content in fixtures.items():
        path = source_dir / name
        path.write_text(content + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def _candidate_by_filename(candidates: List[Dict[str, Any]], filename: str) -> Dict[str, Any]:
    for candidate in candidates:
        if str(candidate.get("original_filename") or "") == filename:
            return candidate
    raise ValueError(f"Candidate fixture not found: {filename}")


def _build_clean_log(workspace: Path) -> Tuple[Any, _DecisionIds, List[Dict[str, Any]]]:
    source_dir = workspace / "source"
    dest_dir = workspace / "dest"
    fixture_paths = _write_fixture_sources(source_dir)
    preview = unified_preview_memory_import(
        dest_dir=dest_dir,
        input_paths=fixture_paths,
        source_type=SOURCE_TYPE_TRANSCRIPTION,
    )
    unified_apply_memory_import(session_json=Path(preview.session_json), apply=True)

    paths = resolve_review_paths(dest_dir=dest_dir)
    candidates = list_candidates(paths, include_all=True).candidates
    ids = _DecisionIds(
        approve=str(_candidate_by_filename(candidates, "approve_branch.txt")["candidate_id"]),
        reject=str(_candidate_by_filename(candidates, "reject_branch.txt")["candidate_id"]),
        edit=str(_candidate_by_filename(candidates, "edit_branch.txt")["candidate_id"]),
    )

    approve_candidate(paths, ids.approve, notes="Tamper recovery clean approve fixture.")
    reject_candidate(paths, ids.reject, notes="Tamper recovery clean reject fixture.")
    edit_candidate(paths, ids.edit, EDITED_TEXT, notes="Tamper recovery clean edit fixture.")

    clean_entries = [
        json.loads(line)
        for line in paths.decisions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return paths, ids, clean_entries


def _status_map(latest: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    return {
        candidate_id: str(decision.get("new_status") or "")
        for candidate_id, decision in latest.items()
    }


def _error_tokens(errors: Sequence[str]) -> List[str]:
    tokens = (
        "malformed_json",
        "missing_required_field",
        "non_chronological",
        "unknown_candidate",
        "unsupported_transition",
    )
    found: List[str] = []
    for token in tokens:
        if any(token in err for err in errors):
            found.append(token)
    return found


def _run_recovery_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> TamperRecoveryReport:
    errors: List[str] = []
    report = TamperRecoveryReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        autonomy_enabled=_read_autonomy_enabled(),
    )
    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; tamper recovery smoke is blocked.")
        return report

    paths, ids, clean_entries = _build_clean_log(workspace)
    decisions_path = paths.decisions_path
    known_ids = ids.as_set()

    # 1) Save a known-good copy before any corruption.
    known_good_dir = workspace / "known_good"
    known_good_dir.mkdir(parents=True, exist_ok=True)
    known_good_path = known_good_dir / "review_decisions.jsonl"
    shutil.copy2(decisions_path, known_good_path)

    # 2) Confirm the clean log audits cleanly and resolves as expected.
    clean_verdict, clean_errors = audit_decision_log(
        known_good_path, known_candidate_ids=known_ids
    )
    report.clean_log_verdict = clean_verdict
    known_good_latest = load_latest_decisions(known_good_path)
    known_good_state = _status_map(known_good_latest)
    expected_state = {
        ids.approve: "approved",
        ids.reject: "rejected",
        ids.edit: "edited",
    }
    if clean_verdict != "PASS" or clean_errors:
        errors.append(f"Clean audit log did not pass: {clean_errors}")
    if known_good_state != expected_state:
        errors.append(f"Known-good latest decisions unexpected: {known_good_state}")

    # 3) Corrupt the working log: malformed JSON line + missing required field.
    missing_field_entry = dict(clean_entries[-1])
    missing_field_entry["decided_at"] = "2999-01-01T00:00:00+00:00"
    missing_field_entry.pop("new_status", None)
    corrupt_lines = [json.dumps(entry, ensure_ascii=False) for entry in clean_entries]
    corrupt_lines.append("{ corrupt line not valid json")
    corrupt_lines.append(json.dumps(missing_field_entry, ensure_ascii=False))
    decisions_path.write_text("\n".join(corrupt_lines) + "\n", encoding="utf-8", newline="\n")

    # 4) Detect corruption before recovery.
    corrupt_verdict, corrupt_errors = audit_decision_log(
        decisions_path, known_candidate_ids=known_ids
    )
    report.corrupt_log_verdict = corrupt_verdict
    report.quarantine_errors = _error_tokens(corrupt_errors)
    report.corruption_detected = corrupt_verdict == "FAIL" and bool(corrupt_errors)

    # 5) Prove the corrupt log cannot be trusted for latest-decision resolution.
    corrupt_content = decisions_path.read_text(encoding="utf-8")
    try:
        load_latest_decisions(decisions_path)
        report.corrupt_log_not_trusted = False
    except MemoryCandidateReviewError:
        report.corrupt_log_not_trusted = True

    # 6) Quarantine the corrupt log (preserve, do not repair in place).
    quarantine_dir = workspace / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    quarantine_log = quarantine_dir / "review_decisions.corrupt.jsonl"
    shutil.copy2(decisions_path, quarantine_log)
    report.quarantine_created = quarantine_dir.is_dir()
    report.quarantine_log_preserved = (
        quarantine_log.is_file()
        and quarantine_log.read_text(encoding="utf-8") == corrupt_content
    )

    # 7) Write a quarantine manifest describing the isolated log.
    manifest = {
        "original_log_path": str(decisions_path.resolve()),
        "quarantine_log_path": str(quarantine_log.resolve()),
        "known_good_log_path": str(known_good_path.resolve()),
        "detected_error_types": report.quarantine_errors,
        "quarantine_timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": True,
        "local_only": True,
        "silently_repaired": False,
        "live_memory_written": False,
        "operator_required": True,
    }
    manifest_path = quarantine_dir / "quarantine_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    report.quarantine_manifest_created = manifest_path.is_file()
    report.operator_required = bool(manifest.get("operator_required"))

    # 8) Recover by restoring latest decisions from the known-good copy only.
    shutil.copy2(known_good_path, decisions_path)
    recovered_latest = load_latest_decisions(decisions_path)
    report.known_good_resolution_used = True
    recovered_state = _status_map(recovered_latest)
    report.latest_decisions_match_known_good = (
        recovered_state == known_good_state == expected_state
    )

    # 9) Prove rejected candidate stays excluded from approved export.
    export_report = export_approved_memory_candidates(dest_dir=paths.dest_dir)
    approved_ids = {str(record.get("candidate_id") or "") for record in export_report.records}
    approved_text = Path(export_report.export_path).read_text(encoding="utf-8")
    report.rejected_still_excluded = (
        ids.reject not in approved_ids and REJECTED_MARKER not in approved_text
    )

    # 10) Prove edited text stays preserved after recovery.
    all_decisions = load_all_decisions(decisions_path)
    edited_path_text = find_latest_edited_text_path(ids.edit, all_decisions) or ""
    edited_value = ""
    if edited_path_text:
        edited_file = Path(edited_path_text)
        if edited_file.is_file():
            edited_value = edited_file.read_text(encoding="utf-8")
    report.edited_text_still_present = EDITED_TEXT in edited_value

    report.artifact_paths = {
        "known_good_log": str(known_good_path.resolve()),
        "restored_log": str(decisions_path.resolve()),
        "quarantine_log": str(quarantine_log.resolve()),
        "quarantine_manifest": str(manifest_path.resolve()),
        "approved_export": str(Path(export_report.export_path).resolve()),
    }
    if edited_path_text:
        report.artifact_paths["edited_text"] = str(Path(edited_path_text).resolve())

    if not report.corruption_detected:
        errors.append("Corruption was not detected before recovery.")
    if not report.quarantine_errors:
        errors.append("No specific corruption error types were captured.")
    if not report.quarantine_created:
        errors.append("Quarantine directory was not created.")
    if not report.quarantine_log_preserved:
        errors.append("Corrupt log content was not preserved in quarantine.")
    if not report.quarantine_manifest_created:
        errors.append("Quarantine manifest was not created.")
    if not report.corrupt_log_not_trusted:
        errors.append("Corrupt log was trusted for latest-decision resolution.")
    if not report.known_good_resolution_used:
        errors.append("Recovery did not use the known-good copy.")
    if not report.latest_decisions_match_known_good:
        errors.append("Recovered latest decisions did not match the known-good state.")
    if not report.rejected_still_excluded:
        errors.append("Rejected candidate was not excluded after recovery.")
    if not report.edited_text_still_present:
        errors.append("Edited text was not preserved after recovery.")
    if not report.operator_required:
        errors.append("Quarantine manifest did not mark operator_required.")

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


def run_memory_review_decision_tamper_recovery_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> TamperRecoveryReport:
    """Prove safe quarantine and known-good recovery from a corrupted audit log."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_review_tamper_recovery_"))
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


def format_operator_summary(report: TamperRecoveryReport) -> str:
    lines = [
        "Memory review decision tamper recovery smoke",
        "=" * 44,
        f"Verdict: {report.verdict}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Clean log verdict: {report.clean_log_verdict}",
        f"Corrupt log verdict: {report.corrupt_log_verdict}",
        f"Corruption detected: {report.corruption_detected}",
        f"Quarantine errors: {', '.join(report.quarantine_errors) or 'none'}",
        "",
        "Recovery:",
        f"  quarantine created: {report.quarantine_created}",
        f"  quarantine log preserved: {report.quarantine_log_preserved}",
        f"  quarantine manifest created: {report.quarantine_manifest_created}",
        f"  corrupt log not trusted: {report.corrupt_log_not_trusted}",
        f"  known-good resolution used: {report.known_good_resolution_used}",
        f"  latest decisions match known-good: {report.latest_decisions_match_known_good}",
        f"  rejected still excluded: {report.rejected_still_excluded}",
        f"  edited text still present: {report.edited_text_still_present}",
        f"  operator_required: {report.operator_required}",
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
        description="Run local-only Memory review decision tamper recovery smoke.",
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
        report = run_memory_review_decision_tamper_recovery_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = TamperRecoveryReport(
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
