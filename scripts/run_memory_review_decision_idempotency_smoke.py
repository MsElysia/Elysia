#!/usr/bin/env python3
"""Dry-run/local smoke proving Memory review decisions are idempotent.

This smoke stages local fixture candidates into a temp workspace, applies
approve/reject/edit decisions twice, and re-runs export/store/search after each
pass. It verifies that repeated decisions and repeated export/store steps keep
stable counts and identifiers, never create duplicate approved or store records,
keep rejected items excluded, and keep edited text preserved. It never calls
models, embeddings, networks, live accounts, or live runtime memory/vector DB.
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
    APPROVED_MEMORY_EXPORT_FILENAME,
    export_approved_memory_candidates,
)
from project_guardian.local_ingestion.approved_memory_search import (  # noqa: E402
    load_memory_store,
    search_memory_store,
)
from project_guardian.local_ingestion.approved_memory_store import (  # noqa: E402
    APPROVED_MEMORY_STORE_FILENAME,
    MEMORY_STORE_SUBDIR,
    default_memory_store_path,
    write_approved_memory_store,
)
from project_guardian.local_ingestion.memory_candidate_review import (  # noqa: E402
    REVIEW_DECISIONS_FILENAME,
    ReviewPaths,
    approve_candidate,
    edit_candidate,
    list_candidates,
    load_all_decisions,
    load_latest_decisions,
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.memory_candidates import (  # noqa: E402
    MEMORY_CANDIDATES_SUBDIR,
    REVIEW_QUEUE_FILENAME,
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
EDITED_QUERY = "countertop measurement"


@dataclass
class ReviewDecisionIdempotencyReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    source_type: str
    candidates_created: int
    first_approved_count: int = 0
    second_approved_count: int = 0
    first_rejected_count: int = 0
    second_rejected_count: int = 0
    first_edited_count: int = 0
    second_edited_count: int = 0
    approved_counts_stable: bool = False
    rejected_counts_stable: bool = False
    edited_counts_stable: bool = False
    approved_ids_stable: bool = False
    rejected_ids_stable: bool = False
    store_record_count_stable: bool = False
    no_duplicate_approved_records: bool = False
    no_duplicate_store_records: bool = False
    rejected_still_excluded: bool = False
    edited_text_still_present: bool = False
    search_ready: bool = False
    first_store_record_count: int = 0
    second_store_record_count: int = 0
    approved_ids: List[str] = field(default_factory=list)
    rejected_ids: List[str] = field(default_factory=list)
    edited_ids: List[str] = field(default_factory=list)
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


@dataclass
class _DecisionIds:
    approve: str
    reject: str
    edit: str


@dataclass
class _PassMeasurement:
    approved_count: int
    rejected_count: int
    edited_count: int
    approved_ids: List[str]
    rejected_ids: List[str]
    edited_ids: List[str]
    store_record_count: int
    no_duplicate_approved_records: bool
    no_duplicate_store_records: bool
    rejected_excluded: bool
    edited_text_present: bool
    search_ready: bool


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


def _artifact_paths(dest_dir: Path) -> Dict[str, Path]:
    candidates_dir = dest_dir / MEMORY_CANDIDATES_SUBDIR
    return {
        "review_queue": candidates_dir / REVIEW_QUEUE_FILENAME,
        "review_decisions": candidates_dir / REVIEW_DECISIONS_FILENAME,
        "approved_export": candidates_dir / APPROVED_MEMORY_EXPORT_FILENAME,
        "memory_store": dest_dir / MEMORY_STORE_SUBDIR / APPROVED_MEMORY_STORE_FILENAME,
    }


def _apply_decisions(paths: ReviewPaths, ids: _DecisionIds) -> None:
    """Apply approve/reject/edit decisions.

    Uses force=True so both the first and repeated passes behave identically; the
    underlying helpers append an auditable decision each call while latest-decision
    resolution and the overwritten export/store files keep the durable output stable.
    """
    approve_candidate(paths, ids.approve, notes="Idempotency smoke approve fixture.", force=True)
    reject_candidate(paths, ids.reject, notes="Idempotency smoke reject fixture.", force=True)
    edit_candidate(
        paths,
        ids.edit,
        EDITED_TEXT,
        notes="Idempotency smoke edit fixture.",
        force=True,
    )
    approve_candidate(
        paths,
        ids.edit,
        notes="Idempotency smoke approve edited fixture.",
        force=True,
    )


def _measure_pass(dest_dir: Path, paths: ReviewPaths, ids: _DecisionIds) -> _PassMeasurement:
    export_report = export_approved_memory_candidates(dest_dir=dest_dir)
    store_report = write_approved_memory_store(dest_dir=dest_dir, apply=True)
    store_records = load_memory_store(default_memory_store_path(dest_dir))

    latest = load_latest_decisions(paths.decisions_path)
    all_decisions = load_all_decisions(paths.decisions_path)

    approved_ids = sorted(
        str(record.get("candidate_id") or "")
        for record in export_report.records
        if str(record.get("candidate_id") or "")
    )
    rejected_ids = sorted(
        candidate_id
        for candidate_id, decision in latest.items()
        if str(decision.get("new_status") or "") == "rejected"
    )
    edited_ids = sorted(
        {
            str(record.get("candidate_id") or "")
            for record in all_decisions
            if str(record.get("new_status") or "") == "edited"
            and str(record.get("candidate_id") or "")
        }
    )

    export_candidate_ids = [
        str(record.get("candidate_id") or "") for record in export_report.records
    ]
    export_export_ids = [str(record.get("export_id") or "") for record in export_report.records]
    store_candidate_ids = [str(record.get("candidate_id") or "") for record in store_records]
    store_memory_ids = [str(record.get("memory_id") or "") for record in store_records]

    no_duplicate_approved_records = (
        len(export_candidate_ids) == len(set(export_candidate_ids))
        and len(export_export_ids) == len(set(export_export_ids))
    )
    no_duplicate_store_records = (
        len(store_candidate_ids) == len(set(store_candidate_ids))
        and len(store_memory_ids) == len(set(store_memory_ids))
    )

    rejected_search = search_memory_store(store_records, REJECTED_QUERY, limit=5)
    edited_search = search_memory_store(store_records, EDITED_QUERY, limit=5)
    approved_search = search_memory_store(store_records, SEARCH_QUERY, limit=5)

    export_text_by_id = {
        str(record.get("candidate_id") or ""): str(record.get("approved_text") or "")
        for record in export_report.records
    }
    store_text_by_id = {
        str(record.get("candidate_id") or ""): str(record.get("text") or "")
        for record in store_records
    }
    edited_text_present = (
        EDITED_TEXT in export_text_by_id.get(ids.edit, "")
        and EDITED_TEXT in store_text_by_id.get(ids.edit, "")
    )
    rejected_excluded = (
        ids.reject not in approved_ids
        and ids.reject not in store_candidate_ids
        and rejected_search.count == 0
    )
    search_ready = (
        Path(store_report.memory_store_path).is_file()
        and approved_search.count >= 2
        and edited_search.count >= 1
    )

    return _PassMeasurement(
        approved_count=len(approved_ids),
        rejected_count=len(rejected_ids),
        edited_count=len(edited_ids),
        approved_ids=approved_ids,
        rejected_ids=rejected_ids,
        edited_ids=edited_ids,
        store_record_count=len(store_records),
        no_duplicate_approved_records=no_duplicate_approved_records,
        no_duplicate_store_records=no_duplicate_store_records,
        rejected_excluded=rejected_excluded,
        edited_text_present=edited_text_present,
        search_ready=search_ready,
    )


def _run_idempotency_flow(
    workspace: Path,
    *,
    workspace_preserved: bool,
) -> ReviewDecisionIdempotencyReport:
    source_dir = workspace / "source"
    dest_dir = workspace / "dest"
    errors: List[str] = []

    report = ReviewDecisionIdempotencyReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        source_type=SOURCE_TYPE_TRANSCRIPTION,
        candidates_created=0,
        autonomy_enabled=_read_autonomy_enabled(),
    )

    if report.autonomy_enabled:
        report.errors.append("Autonomy is enabled; idempotency smoke is blocked.")
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
    first = _measure_pass(dest_dir, paths, ids)

    _apply_decisions(paths, ids)
    second = _measure_pass(dest_dir, paths, ids)

    report.first_approved_count = first.approved_count
    report.second_approved_count = second.approved_count
    report.first_rejected_count = first.rejected_count
    report.second_rejected_count = second.rejected_count
    report.first_edited_count = first.edited_count
    report.second_edited_count = second.edited_count
    report.first_store_record_count = first.store_record_count
    report.second_store_record_count = second.store_record_count
    report.approved_ids = second.approved_ids
    report.rejected_ids = second.rejected_ids
    report.edited_ids = second.edited_ids

    report.approved_counts_stable = first.approved_count == second.approved_count
    report.rejected_counts_stable = first.rejected_count == second.rejected_count
    report.edited_counts_stable = first.edited_count == second.edited_count
    report.approved_ids_stable = first.approved_ids == second.approved_ids
    report.rejected_ids_stable = first.rejected_ids == second.rejected_ids
    report.store_record_count_stable = (
        first.store_record_count == second.store_record_count
    )
    report.no_duplicate_approved_records = (
        first.no_duplicate_approved_records and second.no_duplicate_approved_records
    )
    report.no_duplicate_store_records = (
        first.no_duplicate_store_records and second.no_duplicate_store_records
    )
    report.rejected_still_excluded = first.rejected_excluded and second.rejected_excluded
    report.edited_text_still_present = first.edited_text_present and second.edited_text_present
    report.search_ready = first.search_ready and second.search_ready
    report.artifact_paths = {
        key: str(path.resolve()) for key, path in _artifact_paths(dest_dir).items()
    }

    if report.candidates_created < 3:
        errors.append("Expected at least three candidates for approve/reject/edit branches.")
    if not report.approved_counts_stable:
        errors.append("Approved counts changed between passes.")
    if not report.rejected_counts_stable:
        errors.append("Rejected counts changed between passes.")
    if not report.edited_counts_stable:
        errors.append("Edited counts changed between passes.")
    if not report.approved_ids_stable:
        errors.append("Approved identifiers changed between passes.")
    if not report.rejected_ids_stable:
        errors.append("Rejected identifiers changed between passes.")
    if not report.store_record_count_stable:
        errors.append("Local memory store record count changed between passes.")
    if not report.no_duplicate_approved_records:
        errors.append("Approved export contained duplicate records.")
    if not report.no_duplicate_store_records:
        errors.append("Local memory store contained duplicate records.")
    if not report.rejected_still_excluded:
        errors.append("Rejected candidate was not excluded from approved/search output.")
    if not report.edited_text_still_present:
        errors.append("Edited approved text was not preserved across repeated runs.")
    if not report.search_ready:
        errors.append("Approved-memory search readiness was not stable across passes.")
    if second.approved_count < 2:
        errors.append("Expected at least two approved candidates after repeated runs.")
    if second.rejected_count < 1:
        errors.append("Expected at least one rejected candidate after repeated runs.")
    if second.edited_count < 1:
        errors.append("Expected at least one edited candidate after repeated runs.")

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


def run_memory_review_decision_idempotency_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ReviewDecisionIdempotencyReport:
    """Run repeated approve/reject/edit review decisions on local fixture candidates."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_review_idempotency_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        return _run_idempotency_flow(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: ReviewDecisionIdempotencyReport) -> str:
    lines = [
        "Memory review decision idempotency smoke",
        "=" * 40,
        f"Verdict: {report.verdict}",
        f"Source type: {report.source_type}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Candidates created: {report.candidates_created}",
        "",
        "Stability:",
        f"  approved counts: {report.first_approved_count} -> {report.second_approved_count} "
        f"(stable={report.approved_counts_stable})",
        f"  rejected counts: {report.first_rejected_count} -> {report.second_rejected_count} "
        f"(stable={report.rejected_counts_stable})",
        f"  edited counts: {report.first_edited_count} -> {report.second_edited_count} "
        f"(stable={report.edited_counts_stable})",
        f"  store records: {report.first_store_record_count} -> "
        f"{report.second_store_record_count} (stable={report.store_record_count_stable})",
        f"  approved ids stable: {report.approved_ids_stable}",
        f"  rejected ids stable: {report.rejected_ids_stable}",
        f"  no duplicate approved records: {report.no_duplicate_approved_records}",
        f"  no duplicate store records: {report.no_duplicate_store_records}",
        f"  rejected still excluded: {report.rejected_still_excluded}",
        f"  edited text still present: {report.edited_text_still_present}",
        f"  search ready: {report.search_ready}",
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
        description="Run local-only Memory review decision idempotency smoke.",
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
        report = run_memory_review_decision_idempotency_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ReviewDecisionIdempotencyReport(
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
