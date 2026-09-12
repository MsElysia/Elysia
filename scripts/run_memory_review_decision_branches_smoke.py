#!/usr/bin/env python3
"""Dry-run/local smoke for Memory review decision branch coverage."""

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
    approve_candidate,
    edit_candidate,
    list_candidates,
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
class ReviewDecisionBranchesReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    source_type: str
    candidates_created: int
    approved_count: int
    rejected_count: int
    edited_count: int
    approved_ids: List[str] = field(default_factory=list)
    rejected_ids: List[str] = field(default_factory=list)
    edited_ids: List[str] = field(default_factory=list)
    rejected_excluded_from_search: bool = False
    edited_text_present: bool = False
    search_ready: bool = False
    search_result_count: int = 0
    rejected_search_result_count: int = 0
    edited_search_result_count: int = 0
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


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        item = json.loads(stripped)
        if isinstance(item, dict):
            records.append(item)
    return records


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
        "approved_candidates": candidates_dir / "approved_candidates.jsonl",
        "rejected_candidates": candidates_dir / "rejected_candidates.jsonl",
        "approved_export": candidates_dir / APPROVED_MEMORY_EXPORT_FILENAME,
        "memory_store": dest_dir / MEMORY_STORE_SUBDIR / APPROVED_MEMORY_STORE_FILENAME,
    }


def _empty_report(workspace: Path, *, workspace_preserved: bool) -> ReviewDecisionBranchesReport:
    return ReviewDecisionBranchesReport(
        verdict="FAIL",
        workspace=str(workspace.resolve()),
        workspace_preserved=workspace_preserved,
        source_type=SOURCE_TYPE_TRANSCRIPTION,
        candidates_created=0,
        approved_count=0,
        rejected_count=0,
        edited_count=0,
        autonomy_enabled=_read_autonomy_enabled(),
    )


def _run_decision_flow(workspace: Path, *, workspace_preserved: bool) -> ReviewDecisionBranchesReport:
    source_dir = workspace / "source"
    dest_dir = workspace / "dest"
    errors: List[str] = []
    report = _empty_report(workspace, workspace_preserved=workspace_preserved)

    if _read_autonomy_enabled():
        report.errors.append("Autonomy is enabled; decision branch smoke is blocked.")
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
    approve_id = str(_candidate_by_filename(candidates, "approve_branch.txt")["candidate_id"])
    reject_id = str(_candidate_by_filename(candidates, "reject_branch.txt")["candidate_id"])
    edit_id = str(_candidate_by_filename(candidates, "edit_branch.txt")["candidate_id"])

    approve_candidate(paths, approve_id, notes="Decision branch smoke approve fixture.")
    reject_candidate(paths, reject_id, notes="Decision branch smoke reject fixture.")
    edit_report = edit_candidate(
        paths,
        edit_id,
        EDITED_TEXT,
        notes="Decision branch smoke edit fixture.",
    )
    approve_candidate(
        paths,
        edit_id,
        notes="Decision branch smoke approve edited fixture.",
        force=True,
    )

    export_report = export_approved_memory_candidates(dest_dir=dest_dir)
    store_report = write_approved_memory_store(dest_dir=dest_dir, apply=True)
    store_records = load_memory_store(default_memory_store_path(dest_dir))

    approved_ids = [
        str(record.get("candidate_id") or "")
        for record in export_report.records
        if str(record.get("candidate_id") or "")
    ]
    rejected_ids = [reject_id]
    edited_ids = [edit_id]
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
        EDITED_TEXT in export_text_by_id.get(edit_id, "")
        and EDITED_TEXT in store_text_by_id.get(edit_id, "")
    )

    decisions = _read_jsonl(paths.decisions_path)
    approved_decisions = [
        item for item in decisions if item.get("new_status") == "approved"
    ]
    rejected_decisions = [
        item for item in decisions if item.get("new_status") == "rejected"
    ]
    edited_decisions = [
        item for item in decisions if item.get("new_status") == "edited"
    ]

    report.approved_ids = approved_ids
    report.rejected_ids = rejected_ids
    report.edited_ids = edited_ids
    report.approved_count = len(approved_decisions)
    report.rejected_count = len(rejected_decisions)
    report.edited_count = len(edited_decisions)
    report.rejected_excluded_from_search = (
        reject_id not in approved_ids
        and all(str(record.get("candidate_id") or "") != reject_id for record in store_records)
        and rejected_search.count == 0
    )
    report.edited_text_present = edited_text_present
    report.search_ready = (
        Path(store_report.memory_store_path).is_file()
        and approved_search.count >= 2
        and edited_search.count >= 1
    )
    report.search_result_count = int(approved_search.count)
    report.rejected_search_result_count = int(rejected_search.count)
    report.edited_search_result_count = int(edited_search.count)
    report.artifact_paths = {
        key: str(path.resolve())
        for key, path in _artifact_paths(dest_dir).items()
    }
    if edit_report.edited_text_path:
        report.artifact_paths["edited_text"] = str(Path(edit_report.edited_text_path).resolve())

    if report.candidates_created < 3:
        errors.append("Expected at least three candidates for approve/reject/edit branches.")
    if approve_id not in approved_ids:
        errors.append("Approved fixture candidate was not exported.")
    if edit_id not in approved_ids:
        errors.append("Edited fixture candidate was not approved/exported.")
    if reject_id in approved_ids:
        errors.append("Rejected fixture candidate was exported.")
    if report.approved_count < 2:
        errors.append("Expected at least two approved decisions.")
    if report.rejected_count < 1:
        errors.append("Expected at least one rejected decision.")
    if report.edited_count < 1:
        errors.append("Expected at least one edited decision.")
    if not report.rejected_excluded_from_search:
        errors.append("Rejected candidate was not excluded from approved/search output.")
    if not report.edited_text_present:
        errors.append("Edited approved text was not preserved in export/store output.")
    if not report.search_ready:
        errors.append("Approved-memory search readiness was not verified.")
    if Path(store_report.memory_store_path) != _artifact_paths(dest_dir)["memory_store"].resolve():
        errors.append("Memory store path did not match expected temp workspace path.")
    if export_report.exported_count != store_report.stored_count:
        errors.append("Approved export/store counts do not match.")

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


def run_memory_review_decision_branches_smoke(
    *,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> ReviewDecisionBranchesReport:
    """Run approve/reject/edit review branches on local fixture candidates."""
    owned_temp = base_dir is None
    workspace = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_review_decisions_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        return _run_decision_flow(
            workspace,
            workspace_preserved=(not owned_temp) or keep_temp,
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace, ignore_errors=True)


def format_operator_summary(report: ReviewDecisionBranchesReport) -> str:
    lines = [
        "Memory review decision branches smoke",
        "=" * 38,
        f"Verdict: {report.verdict}",
        f"Source type: {report.source_type}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Candidates created: {report.candidates_created}",
        f"Approved count: {report.approved_count}",
        f"Rejected count: {report.rejected_count}",
        f"Edited count: {report.edited_count}",
        f"Rejected excluded from search: {report.rejected_excluded_from_search}",
        f"Edited text present: {report.edited_text_present}",
        f"Search ready: {report.search_ready}",
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
        description="Run local-only Memory review decision branch smoke.",
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
        report = run_memory_review_decision_branches_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = ReviewDecisionBranchesReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            source_type=SOURCE_TYPE_TRANSCRIPTION,
            candidates_created=0,
            approved_count=0,
            rejected_count=0,
            edited_count=0,
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
