"""End-to-end smoke run for the local memory ingestion pipeline (temp folders only)."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .approved_memory_context import (
    CONTEXT_BUNDLE_JSON,
    CONTEXT_BUNDLE_MD,
    build_approved_memory_context,
)
from .approved_memory_export import (
    APPROVED_MEMORY_EXPORT_FILENAME,
    export_approved_memory_candidates,
)
from .approved_memory_search import load_memory_store, search_memory_store
from .approved_memory_store import (
    APPROVED_MEMORY_STORE_FILENAME,
    default_memory_store_path,
    write_approved_memory_store,
)
from .import_session_apply import APPLY_REPORT_JSON, APPLY_REPORT_MD, apply_memory_import_session
from .import_session_preview import PREVIEW_JSON, PREVIEW_MD, preview_memory_import_session
from .memory_candidate_review import (
    REVIEW_DECISIONS_FILENAME,
    approve_candidate,
    list_candidates,
    resolve_review_paths,
)
from .memory_candidates import REVIEW_QUEUE_FILENAME

SAMPLE_FILES = (
    ("drywall_quote.txt", "Customer asked for a drywall quote for the kitchen remodel."),
    ("schedule_materials.md", "# Schedule\n\nOrder lumber and drywall materials for next week."),
)
SEARCH_QUERY = "drywall quote"


class LocalMemoryPipelineSmokeError(Exception):
    """Raised when the local memory pipeline smoke run fails."""


@dataclass
class SmokeSummary:
    verdict: str
    temp_root: str
    preview_created: bool
    apply_report_created: bool
    candidates_created: int
    approvals_created: int
    approved_export_created: bool
    memory_store_created: bool
    search_result_count: int
    context_bundle_created: bool
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_autonomy_enabled() -> bool:
    path = _repo_root() / "config" / "autonomy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("enabled"))


def _write_sample_files(source_dir: Path) -> List[Path]:
    source_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for name, content in SAMPLE_FILES:
        path = source_dir / name
        path.write_text(content, encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def _pick_drywall_candidate(candidates: List[Dict[str, Any]]) -> Optional[str]:
    for item in candidates:
        candidate_id = str(item.get("candidate_id") or "")
        haystack = " ".join(
            [
                str(item.get("original_filename") or ""),
                str(item.get("text_preview") or ""),
            ]
        ).lower()
        if "drywall" in haystack and candidate_id:
            return candidate_id
    if candidates:
        return str(candidates[0].get("candidate_id") or "") or None
    return None


def run_local_memory_pipeline_smoke(
    *,
    base_dir: Optional[Path] = None,
    keep_temp: bool = False,
) -> SmokeSummary:
    """Run preview → apply → review → export → store → search → context on temp data."""
    if _read_autonomy_enabled():
        raise LocalMemoryPipelineSmokeError("Autonomy must remain disabled for smoke runs.")

    owned_temp = base_dir is None
    temp_root = Path(base_dir) if base_dir is not None else Path(
        tempfile.mkdtemp(prefix="elysia_local_memory_smoke_")
    )
    source_dir = temp_root / "source"
    dest_dir = temp_root / "dest"
    errors: List[str] = []

    summary = SmokeSummary(
        verdict="FAIL",
        temp_root=str(temp_root.resolve()),
        preview_created=False,
        apply_report_created=False,
        candidates_created=0,
        approvals_created=0,
        approved_export_created=False,
        memory_store_created=False,
        search_result_count=0,
        context_bundle_created=False,
        model_called=False,
        embeddings_used=False,
        live_memory_written=False,
        autonomy_enabled=False,
        errors=errors,
    )

    try:
        sample_paths = _write_sample_files(source_dir)

        preview = preview_memory_import_session(dest_dir=dest_dir, input_paths=sample_paths)
        preview_json = Path(preview.json_path)
        preview_md = Path(preview.markdown_path)
        summary.preview_created = preview_json.is_file() and preview_md.is_file()
        if not summary.preview_created:
            errors.append("Preview JSON/Markdown were not created.")

        apply_report = apply_memory_import_session(session_json=preview_json, apply=True)
        apply_json = Path(apply_report.json_path)
        apply_md = Path(apply_report.markdown_path)
        summary.apply_report_created = apply_json.is_file() and apply_md.is_file()
        summary.candidates_created = int(apply_report.report.get("candidate_count") or 0)
        if not summary.apply_report_created:
            errors.append("Apply report JSON/Markdown were not created.")
        if summary.candidates_created < 1:
            errors.append("Expected at least one staged memory candidate.")

        paths = resolve_review_paths(dest_dir=dest_dir)
        listed = list_candidates(paths)
        candidate_id = _pick_drywall_candidate(listed.candidates)
        if not candidate_id:
            errors.append("No candidate available to approve.")
        else:
            if not paths.decisions_path.is_file():
                paths.decisions_path.parent.mkdir(parents=True, exist_ok=True)
                paths.decisions_path.write_text("", encoding="utf-8")
            approve_candidate(paths, candidate_id)
            summary.approvals_created = 1

        queue_path = dest_dir / "memory_candidates" / REVIEW_QUEUE_FILENAME
        decisions_path = dest_dir / "memory_candidates" / REVIEW_DECISIONS_FILENAME
        if not queue_path.is_file():
            errors.append("Review queue was not created.")
        if summary.approvals_created and not decisions_path.is_file():
            errors.append("Review decisions file was not created.")

        export_report = export_approved_memory_candidates(dest_dir=dest_dir)
        export_path = Path(export_report.export_path)
        summary.approved_export_created = export_path.is_file()
        if not summary.approved_export_created:
            errors.append("Approved memory export was not created.")

        store_report = write_approved_memory_store(dest_dir=dest_dir, apply=True)
        store_path = Path(store_report.memory_store_path)
        summary.memory_store_created = store_path.is_file()
        if not summary.memory_store_created:
            errors.append("Approved memory store was not created.")

        search_report = search_memory_store(
            load_memory_store(default_memory_store_path(dest_dir)),
            SEARCH_QUERY,
            limit=5,
        )
        summary.search_result_count = search_report.count
        if summary.search_result_count < 1:
            errors.append(f"Search for '{SEARCH_QUERY}' returned no results.")

        context_report = build_approved_memory_context(
            dest_dir=dest_dir,
            query=SEARCH_QUERY,
            limit=5,
        )
        context_json = Path(context_report.json_path)
        context_md = Path(context_report.markdown_path)
        summary.context_bundle_created = context_json.is_file() and context_md.is_file()
        bundle = context_report.bundle
        if bundle.get("model_called") is not False:
            errors.append("Context bundle model_called is not false.")
        if bundle.get("embeddings_used") is not False:
            errors.append("Context bundle embeddings_used is not false.")
        if bundle.get("live_memory_written") is not False:
            errors.append("Context bundle live_memory_written is not false.")
        if not summary.context_bundle_created:
            errors.append("Context bundle JSON/Markdown were not created.")

        for path, label in (
            (preview_json, "preview JSON"),
            (preview_md, "preview Markdown"),
            (apply_json, "apply JSON"),
            (apply_md, "apply Markdown"),
            (queue_path, "review queue"),
            (decisions_path, "review decisions"),
            (export_path, "approved export"),
            (store_path, "memory store"),
            (context_json, "context JSON"),
            (context_md, "context Markdown"),
        ):
            if not path.is_file():
                errors.append(f"Missing artifact: {label} ({path})")

        summary.verdict = "PASS" if not errors else "FAIL"
        return summary
    finally:
        if owned_temp and not keep_temp and temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)


def format_operator_summary(summary: SmokeSummary) -> str:
    lines = [
        "Local memory pipeline smoke",
        "=" * 32,
        f"Verdict: {summary.verdict}",
        f"Temp root: {summary.temp_root}",
        "",
        f"Preview created: {summary.preview_created}",
        f"Apply report created: {summary.apply_report_created}",
        f"Candidates created: {summary.candidates_created}",
        f"Approvals created: {summary.approvals_created}",
        f"Approved export created: {summary.approved_export_created}",
        f"Memory store created: {summary.memory_store_created}",
        f"Search result count: {summary.search_result_count}",
        f"Context bundle created: {summary.context_bundle_created}",
        "",
        "Safety:",
        f"  model_called: {summary.model_called}",
        f"  embeddings_used: {summary.embeddings_used}",
        f"  live_memory_written: {summary.live_memory_written}",
        f"  autonomy_enabled: {summary.autonomy_enabled}",
    ]
    if summary.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {err}" for err in summary.errors)
    return "\n".join(lines)
