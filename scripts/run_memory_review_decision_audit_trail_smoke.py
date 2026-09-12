#!/usr/bin/env python3
"""Dry-run/local smoke proving the Memory review decision audit trail is trustworthy.

This smoke stages local fixture candidates into a temp workspace, applies
approve/reject/edit decisions twice, then reads the append-only
`review_decisions.jsonl` audit log and verifies it stays well-formed and
operator-safe: every entry is valid JSON with the required audit fields, records
candidate identity and previous/new status, represents approve/reject/edit
transitions, keeps chronological timestamps, and still resolves to the correct
latest decision per candidate after repeated runs. It never calls models,
embeddings, networks, live accounts, or live runtime memory/vector DB.
"""

from __future__ import annotations

import argparse
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

from project_guardian.local_ingestion.approved_memory_export import (  # noqa: E402
    export_approved_memory_candidates,
)
from project_guardian.local_ingestion.approved_memory_search import (  # noqa: E402
    load_memory_store,
    search_memory_store,
)
from project_guardian.local_ingestion.approved_memory_store import (  # noqa: E402
    default_memory_store_path,
    write_approved_memory_store,
)
from project_guardian.local_ingestion.memory_candidate_review import (  # noqa: E402
    REVIEW_DECISIONS_FILENAME,
    ReviewPaths,
    approve_candidate,
    edit_candidate,
    find_latest_edited_text_path,
    list_candidates,
    load_all_decisions,
    load_latest_decisions,
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.memory_candidates import (  # noqa: E402
    MEMORY_CANDIDATES_SUBDIR,
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
SEARCH_QUERY = "kitchen"
REJECTED_QUERY = "rejected-only"

REQUIRED_DECISION_FIELDS = (
    "decision_id",
    "candidate_id",
    "previous_status",
    "new_status",
    "decided_at",
    "operator_required",
    "live_memory_written",
    "source_queue_path",
)


@dataclass
class ReviewDecisionAuditTrailReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    source_type: str
    candidates_created: int
    decision_log_path: str = ""
    decision_log_exists: bool = False
    decision_log_line_count: int = 0
    decision_entries_valid_json: bool = False
    required_fields_present: bool = False
    candidate_ids_present: bool = False
    previous_status_present: bool = False
    new_status_present: bool = False
    approve_transition_present: bool = False
    reject_transition_present: bool = False
    edit_transition_present: bool = False
    timestamps_present: bool = False
    timestamps_chronological: bool = False
    latest_decisions_resolved: bool = False
    latest_approved_count: int = 0
    latest_rejected_count: int = 0
    latest_edited_count: int = 0
    rejected_still_excluded: bool = False
    edited_text_still_present: bool = False
    operator_required: bool = False
    live_memory_written: bool = False
    model_called: bool = False
    embeddings_used: bool = False
    live_vector_db_written: bool = False
    account_api_network_accessed: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class _DecisionIds:
    approve: str
    reject: str
    edit: str


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


def _apply_decisions(paths: ReviewPaths, ids: _DecisionIds) -> None:
    """Apply approve/reject/edit decisions.

    Uses force=True so first and repeated passes behave identically. The edit
    branch stays in the ``edited`` state (no subsequent approve) so the audit log
    exposes all three distinct latest statuses.
    """
    approve_candidate(paths, ids.approve, notes="Audit trail smoke approve fixture.", force=True)
    reject_candidate(paths, ids.reject, notes="Audit trail smoke reject fixture.", force=True)
    edit_candidate(
        paths,
        ids.edit,
        EDITED_TEXT,
        notes="Audit trail smoke edit fixture.",
        force=True,
    )


def _run_audit_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> ReviewDecisionAuditTrailReport:
    source_dir = workspace / "source"
    dest_dir = workspace / "dest"
    errors: List[str] = []

    report = ReviewDecisionAuditTrailReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        source_type=SOURCE_TYPE_TRANSCRIPTION,
        candidates_created=0,
        autonomy_enabled=_read_autonomy_enabled(),
    )

    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; audit trail smoke is blocked.")
        return report

    fixture_paths = _write_fixture_sources(source_dir)
    preview = unified_preview_memory_import(
        dest_dir=dest_dir,
        input_paths=fixture_paths,
        source_type=SOURCE_TYPE_TRANSCRIPTION,
    )
    applied = unified_apply_memory_import(session_json=Path(preview.session_json), apply=True)
    report.candidates_created = int(applied.candidates_staged or 0)

    paths = resolve_review_paths(dest_dir=dest_dir)
    listed = list_candidates(paths, include_all=True)
    candidates = listed.candidates
    ids = _DecisionIds(
        approve=str(_candidate_by_filename(candidates, "approve_branch.txt")["candidate_id"]),
        reject=str(_candidate_by_filename(candidates, "reject_branch.txt")["candidate_id"]),
        edit=str(_candidate_by_filename(candidates, "edit_branch.txt")["candidate_id"]),
    )

    _apply_decisions(paths, ids)
    _apply_decisions(paths, ids)

    decisions_path = paths.decisions_path
    report.decision_log_path = str(decisions_path.resolve())
    report.decision_log_exists = decisions_path.is_file()

    raw_lines = (
        [line for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if report.decision_log_exists
        else []
    )
    report.decision_log_line_count = len(raw_lines)

    parsed_entries: List[Dict[str, Any]] = []
    valid_json = report.decision_log_exists and bool(raw_lines)
    for line in raw_lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            valid_json = False
            continue
        if isinstance(item, dict):
            parsed_entries.append(item)
        else:
            valid_json = False
    report.decision_entries_valid_json = valid_json

    report.required_fields_present = bool(parsed_entries) and all(
        all(field_name in entry for field_name in REQUIRED_DECISION_FIELDS)
        for entry in parsed_entries
    )
    report.candidate_ids_present = bool(parsed_entries) and all(
        str(entry.get("candidate_id") or "").strip() for entry in parsed_entries
    )
    report.previous_status_present = bool(parsed_entries) and all(
        str(entry.get("previous_status") or "").strip() for entry in parsed_entries
    )
    report.new_status_present = bool(parsed_entries) and all(
        str(entry.get("new_status") or "").strip() for entry in parsed_entries
    )

    statuses = {str(entry.get("new_status") or "") for entry in parsed_entries}
    report.approve_transition_present = "approved" in statuses
    report.reject_transition_present = "rejected" in statuses
    report.edit_transition_present = "edited" in statuses

    timestamps = [str(entry.get("decided_at") or "") for entry in parsed_entries]
    report.timestamps_present = bool(timestamps) and all(timestamps)
    report.timestamps_chronological = report.timestamps_present and all(
        earlier <= later for earlier, later in zip(timestamps, timestamps[1:])
    )

    report.operator_required = bool(parsed_entries) and all(
        entry.get("operator_required") is True for entry in parsed_entries
    )
    report.live_memory_written = any(
        entry.get("live_memory_written") is True for entry in parsed_entries
    )

    latest = load_latest_decisions(decisions_path)
    all_decisions = load_all_decisions(decisions_path)
    report.latest_approved_count = sum(
        1 for decision in latest.values() if str(decision.get("new_status") or "") == "approved"
    )
    report.latest_rejected_count = sum(
        1 for decision in latest.values() if str(decision.get("new_status") or "") == "rejected"
    )
    report.latest_edited_count = sum(
        1 for decision in latest.values() if str(decision.get("new_status") or "") == "edited"
    )
    report.latest_decisions_resolved = (
        str((latest.get(ids.approve) or {}).get("new_status") or "") == "approved"
        and str((latest.get(ids.reject) or {}).get("new_status") or "") == "rejected"
        and str((latest.get(ids.edit) or {}).get("new_status") or "") == "edited"
    )

    export_report = export_approved_memory_candidates(dest_dir=dest_dir)
    store_report = write_approved_memory_store(dest_dir=dest_dir, apply=True)
    store_records = load_memory_store(default_memory_store_path(dest_dir))
    approved_candidate_ids = {
        str(record.get("candidate_id") or "") for record in export_report.records
    }
    store_candidate_ids = {str(record.get("candidate_id") or "") for record in store_records}
    rejected_search = search_memory_store(store_records, REJECTED_QUERY, limit=5)
    report.rejected_still_excluded = (
        ids.reject not in approved_candidate_ids
        and ids.reject not in store_candidate_ids
        and rejected_search.count == 0
    )

    edited_path_text = find_latest_edited_text_path(ids.edit, all_decisions) or ""
    edited_text_value = ""
    if edited_path_text:
        edited_file = Path(edited_path_text)
        if edited_file.is_file():
            edited_text_value = edited_file.read_text(encoding="utf-8")
    report.edited_text_still_present = EDITED_TEXT in edited_text_value

    report.artifact_paths = {
        "review_queue": str(paths.queue_path.resolve()),
        "review_decisions": str(decisions_path.resolve()),
        "approved_export": str(Path(export_report.export_path).resolve()),
        "memory_store": str(Path(store_report.memory_store_path).resolve()),
    }
    if edited_path_text:
        report.artifact_paths["edited_text"] = str(Path(edited_path_text).resolve())

    if report.candidates_created < 3:
        errors.append("Expected at least three candidates for approve/reject/edit branches.")
    if not report.decision_log_exists:
        errors.append("Review decision log was not created.")
    if not report.decision_entries_valid_json:
        errors.append("Review decision log contained invalid JSON entries.")
    if not report.required_fields_present:
        errors.append("Review decision entries were missing required audit fields.")
    if not report.candidate_ids_present:
        errors.append("Review decision entries were missing candidate identity.")
    if not report.previous_status_present:
        errors.append("Review decision entries were missing previous status.")
    if not report.new_status_present:
        errors.append("Review decision entries were missing new status.")
    if not report.approve_transition_present:
        errors.append("Approve transition was not represented in the audit log.")
    if not report.reject_transition_present:
        errors.append("Reject transition was not represented in the audit log.")
    if not report.edit_transition_present:
        errors.append("Edit transition was not represented in the audit log.")
    if not report.timestamps_present:
        errors.append("Review decision entries were missing timestamps.")
    if not report.timestamps_chronological:
        errors.append("Review decision timestamps were not chronological.")
    if not report.latest_decisions_resolved:
        errors.append("Latest-decision resolution did not return expected statuses.")
    if report.latest_approved_count != 1:
        errors.append("Expected exactly one latest approved candidate.")
    if report.latest_rejected_count != 1:
        errors.append("Expected exactly one latest rejected candidate.")
    if report.latest_edited_count != 1:
        errors.append("Expected exactly one latest edited candidate.")
    if not report.rejected_still_excluded:
        errors.append("Rejected candidate was not excluded from approved/search output.")
    if not report.edited_text_still_present:
        errors.append("Edited text was not preserved in the audit trail.")
    if not report.operator_required:
        errors.append("Review decision entries did not all mark operator_required.")

    for flag_name in (
        "live_memory_written",
        "model_called",
        "embeddings_used",
        "live_vector_db_written",
        "account_api_network_accessed",
        "autonomy_enabled",
    ):
        if getattr(report, flag_name):
            errors.append(f"{flag_name} unexpectedly true.")

    report.errors = errors
    report.verdict = "PASS" if not errors else "FAIL"
    return report


def run_memory_review_decision_audit_trail_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ReviewDecisionAuditTrailReport:
    """Run repeated approve/reject/edit decisions and audit the decision log."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_review_audit_trail_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        return _run_audit_flow(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: ReviewDecisionAuditTrailReport) -> str:
    lines = [
        "Memory review decision audit trail smoke",
        "=" * 40,
        f"Verdict: {report.verdict}",
        f"Source type: {report.source_type}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Candidates created: {report.candidates_created}",
        "",
        "Audit log:",
        f"  path: {report.decision_log_path}",
        f"  exists: {report.decision_log_exists}",
        f"  line count: {report.decision_log_line_count}",
        f"  valid JSON: {report.decision_entries_valid_json}",
        f"  required fields present: {report.required_fields_present}",
        f"  candidate ids present: {report.candidate_ids_present}",
        f"  previous status present: {report.previous_status_present}",
        f"  new status present: {report.new_status_present}",
        f"  approve/reject/edit transitions: "
        f"{report.approve_transition_present}/{report.reject_transition_present}/"
        f"{report.edit_transition_present}",
        f"  timestamps present/chronological: "
        f"{report.timestamps_present}/{report.timestamps_chronological}",
        f"  latest resolved: {report.latest_decisions_resolved}",
        f"  latest approved/rejected/edited: "
        f"{report.latest_approved_count}/{report.latest_rejected_count}/"
        f"{report.latest_edited_count}",
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
        description="Run local-only Memory review decision audit trail smoke.",
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
        report = run_memory_review_decision_audit_trail_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ReviewDecisionAuditTrailReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            source_type=SOURCE_TYPE_TRANSCRIPTION,
            candidates_created=0,
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
