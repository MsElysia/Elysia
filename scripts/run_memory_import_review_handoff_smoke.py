#!/usr/bin/env python3
"""Dry-run/local smoke for Memory import-to-review handoff coverage."""

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

from project_guardian.local_ingestion.approved_memory_context import (  # noqa: E402
    CONTEXT_BUNDLE_JSON,
    CONTEXT_BUNDLE_MD,
    MEMORY_CONTEXT_SUBDIR,
)
from project_guardian.local_ingestion.approved_memory_export import (  # noqa: E402
    APPROVED_MEMORY_EXPORT_FILENAME,
)
from project_guardian.local_ingestion.approved_memory_store import (  # noqa: E402
    APPROVED_MEMORY_STORE_FILENAME,
    MEMORY_STORE_SUBDIR,
)
from project_guardian.local_ingestion.local_memory_pipeline_smoke import (  # noqa: E402
    SOURCE_TYPE_CHATGPT,
    SOURCE_TYPE_EMAIL,
    SOURCE_TYPE_TRANSCRIPTION,
    VALID_SOURCE_TYPES,
    LocalMemoryPipelineSmokeError,
    run_local_memory_pipeline_smoke,
)
from project_guardian.local_ingestion.memory_candidate_review import (  # noqa: E402
    REVIEW_DECISIONS_FILENAME,
)
from project_guardian.local_ingestion.memory_candidates import (  # noqa: E402
    MEMORY_CANDIDATES_SUBDIR,
    REVIEW_QUEUE_FILENAME,
)

SOURCE_TYPE_ALL = "all"
DEFAULT_SOURCE_TYPES = (
    SOURCE_TYPE_TRANSCRIPTION,
    SOURCE_TYPE_CHATGPT,
    SOURCE_TYPE_EMAIL,
)


@dataclass
class SourceHandoffReport:
    source_type: str
    workspace: str
    candidates_created: int
    review_item_count: int
    review_items_available: bool
    approval_path_available: bool
    approved_export_available: bool
    memory_store_available: bool
    search_ready: bool
    search_result_count: int
    context_bundle_available: bool
    model_called: bool
    embeddings_used: bool
    live_memory_written: bool
    live_vector_db_written: bool
    autonomy_enabled: bool
    errors: List[str] = field(default_factory=list)
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HandoffSmokeReport:
    verdict: str
    workspace: str
    workspace_preserved: bool
    source_type: str
    source_types: List[str]
    candidates_created: int
    review_items_available: bool
    approval_path_available: bool
    search_ready: bool
    model_called: bool
    embeddings_used: bool
    live_memory_written: bool
    live_vector_db_written: bool
    account_api_network_accessed: bool
    autonomy_enabled: bool
    errors: List[str] = field(default_factory=list)
    per_source: List[Dict[str, Any]] = field(default_factory=list)

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


def _select_source_types(source_type: str) -> List[str]:
    normalized = str(source_type or SOURCE_TYPE_ALL).strip().lower()
    if normalized == SOURCE_TYPE_ALL:
        return list(DEFAULT_SOURCE_TYPES)
    if normalized not in VALID_SOURCE_TYPES:
        expected = ", ".join(sorted([SOURCE_TYPE_ALL, *VALID_SOURCE_TYPES]))
        raise ValueError(f"Unknown source type {source_type!r}; expected one of: {expected}")
    return [normalized]


def _count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count


def _artifact_paths(workspace: Path) -> Dict[str, Path]:
    dest = workspace / "dest"
    candidates_dir = dest / MEMORY_CANDIDATES_SUBDIR
    context_dir = dest / MEMORY_CONTEXT_SUBDIR
    return {
        "review_queue": candidates_dir / REVIEW_QUEUE_FILENAME,
        "review_decisions": candidates_dir / REVIEW_DECISIONS_FILENAME,
        "approved_export": candidates_dir / APPROVED_MEMORY_EXPORT_FILENAME,
        "memory_store": dest / MEMORY_STORE_SUBDIR / APPROVED_MEMORY_STORE_FILENAME,
        "context_json": context_dir / CONTEXT_BUNDLE_JSON,
        "context_markdown": context_dir / CONTEXT_BUNDLE_MD,
    }


def _source_report_from_summary(source_type: str, workspace: Path, summary: Any) -> SourceHandoffReport:
    paths = _artifact_paths(workspace)
    review_item_count = _count_jsonl(paths["review_queue"])
    review_items_available = paths["review_queue"].is_file() and review_item_count > 0
    approved_export_available = paths["approved_export"].is_file()
    memory_store_available = paths["memory_store"].is_file()
    decisions_available = paths["review_decisions"].is_file()
    context_bundle_available = (
        paths["context_json"].is_file() and paths["context_markdown"].is_file()
    )
    search_ready = bool(memory_store_available and int(summary.search_result_count or 0) > 0)
    approval_path_available = bool(
        decisions_available and approved_export_available and memory_store_available
    )

    errors = list(summary.errors or [])
    if summary.verdict != "PASS":
        errors.append(f"Underlying local pipeline smoke returned {summary.verdict}.")
    if int(summary.candidates_created or 0) <= 0:
        errors.append("No import candidates were created.")
    if not review_items_available:
        errors.append("Review queue handoff artifacts are missing or empty.")
    if not approval_path_available:
        errors.append("Approval/export/store path artifacts are incomplete.")
    if not search_ready:
        errors.append("Approved-memory search path is not ready.")
    if not context_bundle_available:
        errors.append("Context bundle artifacts are incomplete.")
    if any([summary.model_called, summary.embeddings_used, summary.live_memory_written, summary.autonomy_enabled]):
        errors.append("A safety flag was unexpectedly enabled.")

    return SourceHandoffReport(
        source_type=source_type,
        workspace=str(workspace.resolve()),
        candidates_created=int(summary.candidates_created or 0),
        review_item_count=review_item_count,
        review_items_available=review_items_available,
        approval_path_available=approval_path_available,
        approved_export_available=approved_export_available,
        memory_store_available=memory_store_available,
        search_ready=search_ready,
        search_result_count=int(summary.search_result_count or 0),
        context_bundle_available=context_bundle_available,
        model_called=bool(summary.model_called),
        embeddings_used=bool(summary.embeddings_used),
        live_memory_written=bool(summary.live_memory_written),
        live_vector_db_written=False,
        autonomy_enabled=bool(summary.autonomy_enabled),
        errors=errors,
        artifact_paths={key: str(path.resolve()) for key, path in paths.items()},
    )


def run_memory_import_review_handoff_smoke(
    *,
    source_type: str = SOURCE_TYPE_ALL,
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> HandoffSmokeReport:
    """Run local fixture import through review handoff and approved search readiness."""
    selected_sources = _select_source_types(source_type)
    owned_temp = base_dir is None
    workspace_root = (
        Path(tempfile.mkdtemp(prefix="elysia_memory_import_review_handoff_"))
        if owned_temp
        else _reject_dangerous_base(Path(base_dir))
    )
    workspace_root.mkdir(parents=True, exist_ok=True)
    errors: List[str] = []
    per_source: List[SourceHandoffReport] = []

    if _read_autonomy_enabled():
        errors.append("Autonomy is enabled; handoff smoke is blocked.")

    try:
        if not errors:
            for source in selected_sources:
                source_workspace = workspace_root / source
                try:
                    summary = run_local_memory_pipeline_smoke(
                        base_dir=source_workspace,
                        keep_temp=True,
                        source_type=source,
                    )
                    per_source.append(
                        _source_report_from_summary(source, source_workspace, summary)
                    )
                except LocalMemoryPipelineSmokeError as exc:
                    errors.append(f"{source}: {exc}")
                except Exception as exc:  # noqa: BLE001 - preserve smoke failures in JSON.
                    errors.append(f"{source}: {exc}")

        for item in per_source:
            errors.extend(f"{item.source_type}: {error}" for error in item.errors)

        candidates_created = sum(item.candidates_created for item in per_source)
        review_items_available = bool(per_source) and all(
            item.review_items_available for item in per_source
        )
        approval_path_available = bool(per_source) and all(
            item.approval_path_available for item in per_source
        )
        search_ready = bool(per_source) and all(item.search_ready for item in per_source)
        model_called = any(item.model_called for item in per_source)
        embeddings_used = any(item.embeddings_used for item in per_source)
        live_memory_written = any(item.live_memory_written for item in per_source)
        live_vector_db_written = any(item.live_vector_db_written for item in per_source)
        autonomy_enabled = _read_autonomy_enabled() or any(
            item.autonomy_enabled for item in per_source
        )
        account_api_network_accessed = False

        if candidates_created <= 0:
            errors.append("No import candidates were created across selected sources.")
        if not review_items_available:
            errors.append("Review handoff artifacts were not available for every source.")
        if not approval_path_available:
            errors.append("Approval path artifacts were not available for every source.")
        if not search_ready:
            errors.append("Approved-memory search was not ready for every source.")
        if any(
            [
                model_called,
                embeddings_used,
                live_memory_written,
                live_vector_db_written,
                account_api_network_accessed,
                autonomy_enabled,
            ]
        ):
            errors.append("One or more safety flags were unexpectedly enabled.")

        verdict = "PASS" if not errors else "FAIL"
        return HandoffSmokeReport(
            verdict=verdict,
            workspace=str(workspace_root.resolve()),
            workspace_preserved=(not owned_temp) or keep_temp,
            source_type=source_type,
            source_types=selected_sources,
            candidates_created=candidates_created,
            review_items_available=review_items_available,
            approval_path_available=approval_path_available,
            search_ready=search_ready,
            model_called=model_called,
            embeddings_used=embeddings_used,
            live_memory_written=live_memory_written,
            live_vector_db_written=live_vector_db_written,
            account_api_network_accessed=account_api_network_accessed,
            autonomy_enabled=autonomy_enabled,
            errors=errors,
            per_source=[item.to_dict() for item in per_source],
        )
    finally:
        if owned_temp and not keep_temp:
            shutil.rmtree(workspace_root, ignore_errors=True)


def format_operator_summary(report: HandoffSmokeReport) -> str:
    lines = [
        "Memory import-to-review handoff smoke",
        "=" * 41,
        f"Verdict: {report.verdict}",
        f"Source types: {', '.join(report.source_types)}",
        f"Workspace: {report.workspace}",
        f"Workspace preserved: {report.workspace_preserved}",
        f"Candidates created: {report.candidates_created}",
        f"Review items available: {report.review_items_available}",
        f"Approval path available: {report.approval_path_available}",
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
        description="Run a local-only Memory import-to-review handoff smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON smoke result")
    parser.add_argument(
        "--source-type",
        choices=sorted([SOURCE_TYPE_ALL, *VALID_SOURCE_TYPES]),
        default=SOURCE_TYPE_ALL,
        help="Source type to run, or all local fixture source types",
    )
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
        report = run_memory_import_review_handoff_smoke(
            source_type=args.source_type,
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
        )
    except ValueError as exc:
        report = HandoffSmokeReport(
            verdict="FAIL",
            workspace=str(args.base_dir or ""),
            workspace_preserved=False,
            source_type=args.source_type,
            source_types=[],
            candidates_created=0,
            review_items_available=False,
            approval_path_available=False,
            search_ready=False,
            model_called=False,
            embeddings_used=False,
            live_memory_written=False,
            live_vector_db_written=False,
            account_api_network_accessed=False,
            autonomy_enabled=_read_autonomy_enabled(),
            errors=[str(exc)],
            per_source=[],
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_operator_summary(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
