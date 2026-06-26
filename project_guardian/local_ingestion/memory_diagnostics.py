"""Local-only memory diagnostics, demo workspace, and health smoke helpers."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
from .memory_candidate_review import (
    REVIEW_DECISIONS_FILENAME,
    approve_candidate,
    list_candidates,
    resolve_review_paths,
)
from .memory_candidates import MEMORY_CANDIDATES_SUBDIR, REVIEW_QUEUE_FILENAME
from .unified_memory_import import (
    SOURCE_TYPE_CHATGPT,
    SOURCE_TYPE_EMAIL,
    SOURCE_TYPE_TRANSCRIPTION,
    unified_apply_memory_import,
    unified_preview_memory_import,
)

EMPTY_WORKSPACE = "EMPTY_WORKSPACE"
READY_FOR_IMPORT = "READY_FOR_IMPORT"
HAS_PENDING_REVIEW = "HAS_PENDING_REVIEW"
HAS_APPROVED_MEMORY = "HAS_APPROVED_MEMORY"
HAS_CONTEXT_BUNDLE = "HAS_CONTEXT_BUNDLE"
NEEDS_ATTENTION = "NEEDS_ATTENTION"

SEARCH_QUERY = "drywall quote"


class MemoryDiagnosticsError(Exception):
    """Raised when a local diagnostics/demo action cannot proceed safely."""


@dataclass
class MemoryDoctorReport:
    dest_dir: str
    exists: bool
    is_dir: bool
    import_session_count: int
    chatgpt_import_session_count: int
    email_import_session_count: int
    pending_candidates_count: int
    review_decisions_count: int
    approved_decisions_count: int
    rejected_decisions_count: int
    approved_export_exists: bool
    approved_memory_store_exists: bool
    approved_memory_count: Optional[int]
    context_bundle_files_exist: bool
    import_ready_file_count: int
    verdict: str
    warnings: List[str] = field(default_factory=list)
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    autonomy_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DemoWorkspaceReport:
    verdict: str
    dest_dir: str
    applied: bool
    pipeline_run: bool
    planned_files: List[str]
    files_written: List[str]
    candidates_created: int = 0
    approvals_created: int = 0
    approved_export_created: bool = False
    approved_memory_store_created: bool = False
    approved_memory_count: int = 0
    search_result_count: int = 0
    context_bundle_created: bool = False
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryHealthSmokeReport:
    verdict: str
    demo_workspace_created: bool
    doctor_verdict: str
    candidates_created: int
    approvals_created: int
    search_result_count: int
    context_bundle_created: bool
    temp_path: Optional[str]
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    autonomy_enabled: bool = False
    errors: List[str] = field(default_factory=list)
    demo_summary: Dict[str, Any] = field(default_factory=dict)
    doctor_report: Dict[str, Any] = field(default_factory=dict)

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


def _resolve_path(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _count_child_dirs(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(1 for child in path.iterdir() if child.is_dir())
    except OSError:
        return 0


def _read_optional_jsonl(path: Path, *, label: str, warnings: List[str]) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []

    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    item = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    warnings.append(f"Malformed JSON in {label} at line {line_no}: {exc}")
                    continue
                if not isinstance(item, dict):
                    warnings.append(f"Expected JSON object in {label} at line {line_no}.")
                    continue
                records.append(item)
    except OSError as exc:
        warnings.append(f"Unable to read {label}: {exc}")
    return records


def _latest_decision_statuses(decisions: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    latest: Dict[str, str] = {}
    for record in decisions:
        candidate_id = str(record.get("candidate_id") or "").strip()
        status = str(record.get("new_status") or "").strip()
        if candidate_id and status:
            latest[candidate_id] = status
    return latest


def _pending_candidate_count(
    candidates: Sequence[Dict[str, Any]],
    decisions: Sequence[Dict[str, Any]],
) -> int:
    final_statuses = {"approved", "rejected", "edited"}
    latest = _latest_decision_statuses(decisions)
    count = 0
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        status = latest.get(candidate_id) or str(candidate.get("review_status") or "pending")
        if status not in final_statuses:
            count += 1
    return count


def _count_import_ready_files(dest_dir: Path) -> int:
    supported_transcription = {".txt", ".md", ".vtt", ".srt"}
    known_dirs = (
        dest_dir / "sample_inputs" / "transcription",
        dest_dir / "sample_inputs" / "chatgpt",
        dest_dir / "sample_inputs" / "email",
    )
    count = 0
    seen: set[Path] = set()
    for directory in known_dirs:
        if not directory.is_dir():
            continue
        try:
            children = list(directory.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_file() or child in seen:
                continue
            seen.add(child)
            if child.suffix.lower() in supported_transcription:
                count += 1
            elif child.suffix.lower() == ".eml":
                count += 1
            elif child.name.lower() == "conversations.json":
                count += 1
    return count


def _choose_doctor_verdict(
    *,
    warnings: Sequence[str],
    context_bundle_files_exist: bool,
    approved_memory_count: Optional[int],
    approved_export_exists: bool,
    pending_candidates_count: int,
    import_ready_file_count: int,
) -> str:
    if warnings:
        return NEEDS_ATTENTION
    if context_bundle_files_exist:
        return HAS_CONTEXT_BUNDLE
    if (approved_memory_count or 0) > 0 or approved_export_exists:
        return HAS_APPROVED_MEMORY
    if pending_candidates_count > 0:
        return HAS_PENDING_REVIEW
    if import_ready_file_count > 0:
        return READY_FOR_IMPORT
    return EMPTY_WORKSPACE


def run_memory_doctor(dest_dir: Path) -> MemoryDoctorReport:
    """Inspect known local-memory workspace artifacts without writing anything."""
    dest = _resolve_path(dest_dir)
    warnings: List[str] = []
    exists = dest.exists()
    is_dir = dest.is_dir()
    autonomy_enabled = _read_autonomy_enabled()

    if exists and not is_dir:
        warnings.append(f"Destination exists but is not a directory: {dest}")

    candidates_path = dest / MEMORY_CANDIDATES_SUBDIR / REVIEW_QUEUE_FILENAME
    decisions_path = dest / MEMORY_CANDIDATES_SUBDIR / REVIEW_DECISIONS_FILENAME
    export_path = dest / MEMORY_CANDIDATES_SUBDIR / APPROVED_MEMORY_EXPORT_FILENAME
    store_path = default_memory_store_path(dest)
    context_json = dest / "memory_context" / CONTEXT_BUNDLE_JSON
    context_md = dest / "memory_context" / CONTEXT_BUNDLE_MD

    candidates = _read_optional_jsonl(
        candidates_path,
        label="review queue",
        warnings=warnings,
    )
    decisions = _read_optional_jsonl(
        decisions_path,
        label="review decisions",
        warnings=warnings,
    )
    store_records = _read_optional_jsonl(
        store_path,
        label="approved memory store",
        warnings=warnings,
    )

    approved_memory_count: Optional[int]
    if store_path.is_file():
        approved_memory_count = len(store_records)
    else:
        approved_memory_count = None

    approved_decisions = sum(1 for item in decisions if item.get("new_status") == "approved")
    rejected_decisions = sum(1 for item in decisions if item.get("new_status") == "rejected")
    pending_count = _pending_candidate_count(candidates, decisions)
    import_ready_count = _count_import_ready_files(dest) if is_dir else 0
    context_exists = context_json.is_file() and context_md.is_file()
    verdict = _choose_doctor_verdict(
        warnings=warnings,
        context_bundle_files_exist=context_exists,
        approved_memory_count=approved_memory_count,
        approved_export_exists=export_path.is_file(),
        pending_candidates_count=pending_count,
        import_ready_file_count=import_ready_count,
    )

    return MemoryDoctorReport(
        dest_dir=str(dest),
        exists=exists,
        is_dir=is_dir,
        import_session_count=_count_child_dirs(dest / "import_sessions"),
        chatgpt_import_session_count=_count_child_dirs(dest / "chatgpt_import_sessions"),
        email_import_session_count=_count_child_dirs(dest / "email_import_sessions"),
        pending_candidates_count=pending_count,
        review_decisions_count=len(decisions),
        approved_decisions_count=approved_decisions,
        rejected_decisions_count=rejected_decisions,
        approved_export_exists=export_path.is_file(),
        approved_memory_store_exists=store_path.is_file(),
        approved_memory_count=approved_memory_count,
        context_bundle_files_exist=context_exists,
        import_ready_file_count=import_ready_count,
        verdict=verdict,
        warnings=warnings,
        model_called=False,
        embeddings_used=False,
        live_memory_written=False,
        autonomy_enabled=autonomy_enabled,
    )


def _planned_demo_relative_files() -> List[Path]:
    return [
        Path("README.md"),
        Path("sample_inputs") / "transcription" / "demo_transcript.txt",
        Path("sample_inputs") / "chatgpt" / "conversations.json",
        Path("sample_inputs") / "email" / "demo_email.eml",
    ]


def _reject_dangerous_dest(dest: Path) -> None:
    resolved = _resolve_path(dest)
    repo_root = _repo_root().resolve()
    home = Path.home().resolve()

    if resolved == resolved.parent:
        raise MemoryDiagnosticsError(f"Refusing to use filesystem root as demo destination: {resolved}")
    if resolved == home:
        raise MemoryDiagnosticsError(f"Refusing to use home directory as demo destination: {resolved}")
    if resolved == repo_root:
        raise MemoryDiagnosticsError(f"Refusing to use repository root as demo destination: {resolved}")
    if resolved.anchor and str(resolved) == resolved.anchor:
        raise MemoryDiagnosticsError(f"Refusing to use drive root as demo destination: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise MemoryDiagnosticsError(f"Destination exists but is not a directory: {resolved}")


def _assert_under_dest(dest: Path, target: Path) -> Path:
    dest_resolved = dest.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(dest_resolved)
    except ValueError as exc:
        raise MemoryDiagnosticsError(f"Refusing to write outside destination: {target_resolved}") from exc
    return target_resolved


def _sample_chatgpt_export() -> List[Dict[str, Any]]:
    return [
        {
            "title": "Demo drywall quote chat",
            "id": "demo-conv-1",
            "create_time": 1700000000,
            "update_time": 1700000100,
            "current_node": "node-2",
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Need a drywall quote for the kitchen remodel."]},
                        "create_time": 1700000001,
                    },
                },
                "node-2": {
                    "id": "node-2",
                    "parent": "node-1",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Ask for wall dimensions before estimating materials."]},
                        "create_time": 1700000002,
                    },
                },
            },
        }
    ]


def _sample_email() -> str:
    return "\n".join(
        [
            "From: demo.sender@example.com",
            "To: operator@example.com",
            "Subject: Drywall quote follow-up",
            "Date: Mon, 1 Jan 2026 12:00:00 +0000",
            "Message-ID: <demo-memory-email@example.com>",
            "Content-Type: text/plain; charset=utf-8",
            "",
            "Please send the drywall quote for the kitchen remodel.",
        ]
    )


def _sample_readme() -> str:
    return "\n".join(
        [
            "# Memory Demo Workspace",
            "",
            "This workspace contains fake local-only sample inputs for the Elysia memory pipeline.",
            "",
            "- No account access is required.",
            "- No model, embedding, or network call is made by the demo generator.",
            "- Running the demo pipeline stages candidates for operator review only.",
            "- Approved demo memory is written only inside this destination directory.",
            "",
        ]
    )


def _write_demo_files(dest: Path) -> List[str]:
    dest.mkdir(parents=True, exist_ok=True)
    files = {
        Path("README.md"): _sample_readme(),
        Path("sample_inputs") / "transcription" / "demo_transcript.txt": (
            "Customer asked for a drywall quote for the kitchen remodel.\n"
            "Reminder: confirm dimensions before ordering materials.\n"
        ),
        Path("sample_inputs") / "chatgpt" / "conversations.json": json.dumps(
            _sample_chatgpt_export(),
            indent=2,
        )
        + "\n",
        Path("sample_inputs") / "email" / "demo_email.eml": _sample_email() + "\n",
    }

    written: List[str] = []
    for relative, text in files.items():
        path = _assert_under_dest(dest, dest / relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(str(path))
    return written


def _approve_all_pending_candidates(dest: Path) -> int:
    paths = resolve_review_paths(dest_dir=dest)
    listed = list_candidates(paths)
    approved = 0
    for candidate in listed.candidates:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        approve_candidate(paths, candidate_id)
        approved += 1
    return approved


def _run_demo_pipeline(dest: Path) -> Dict[str, Any]:
    sources = (
        (
            SOURCE_TYPE_TRANSCRIPTION,
            [dest / "sample_inputs" / "transcription" / "demo_transcript.txt"],
        ),
        (
            SOURCE_TYPE_CHATGPT,
            [dest / "sample_inputs" / "chatgpt" / "conversations.json"],
        ),
        (
            SOURCE_TYPE_EMAIL,
            [dest / "sample_inputs" / "email" / "demo_email.eml"],
        ),
    )

    candidates_created = 0
    for source_type, inputs in sources:
        preview = unified_preview_memory_import(
            dest_dir=dest,
            input_paths=inputs,
            source_type=source_type,
        )
        applied = unified_apply_memory_import(
            session_json=Path(preview.session_json),
            apply=True,
        )
        candidates_created += applied.candidates_staged

    approvals_created = _approve_all_pending_candidates(dest)
    export_report = export_approved_memory_candidates(dest_dir=dest)
    store_report = write_approved_memory_store(dest_dir=dest, apply=True)
    store_path = Path(store_report.memory_store_path)
    records = load_memory_store(store_path)
    search_report = search_memory_store(records, SEARCH_QUERY, limit=5)
    context_report = build_approved_memory_context(dest_dir=dest, query=SEARCH_QUERY, limit=5)

    return {
        "candidates_created": candidates_created,
        "approvals_created": approvals_created,
        "approved_export_created": Path(export_report.export_path).is_file(),
        "approved_memory_store_created": store_path.is_file(),
        "approved_memory_count": len(records),
        "search_result_count": search_report.count,
        "context_bundle_created": Path(context_report.json_path).is_file()
        and Path(context_report.markdown_path).is_file(),
    }


def create_memory_demo_workspace(
    *,
    dest_dir: Path,
    apply: bool = False,
    run_pipeline: bool = False,
) -> DemoWorkspaceReport:
    """Create fake sample local-memory inputs, optionally running the local pipeline."""
    if _read_autonomy_enabled():
        raise MemoryDiagnosticsError("Autonomy is enabled; demo workspace creation is blocked.")
    if run_pipeline and not apply:
        raise MemoryDiagnosticsError("--run-pipeline requires --apply.")

    dest = _resolve_path(dest_dir)
    _reject_dangerous_dest(dest)
    planned_files = [str(dest / relative) for relative in _planned_demo_relative_files()]

    if not apply:
        return DemoWorkspaceReport(
            verdict="DRY_RUN",
            dest_dir=str(dest),
            applied=False,
            pipeline_run=False,
            planned_files=planned_files,
            files_written=[],
            autonomy_enabled=False,
        )

    written = _write_demo_files(dest)
    report = DemoWorkspaceReport(
        verdict="PASS",
        dest_dir=str(dest),
        applied=True,
        pipeline_run=run_pipeline,
        planned_files=planned_files,
        files_written=written,
        autonomy_enabled=False,
    )

    if run_pipeline:
        pipeline = _run_demo_pipeline(dest)
        report.candidates_created = int(pipeline["candidates_created"])
        report.approvals_created = int(pipeline["approvals_created"])
        report.approved_export_created = bool(pipeline["approved_export_created"])
        report.approved_memory_store_created = bool(pipeline["approved_memory_store_created"])
        report.approved_memory_count = int(pipeline["approved_memory_count"])
        report.search_result_count = int(pipeline["search_result_count"])
        report.context_bundle_created = bool(pipeline["context_bundle_created"])
        if (
            report.candidates_created < 1
            or report.approvals_created < 1
            or report.search_result_count < 1
            or not report.context_bundle_created
        ):
            report.verdict = "FAIL"
            report.errors.append("Demo pipeline did not create the expected local artifacts.")

    return report


def run_memory_health_smoke(*, keep_temp: bool = False) -> MemoryHealthSmokeReport:
    """Create a temp demo workspace, run the pipeline, run doctor, then clean up."""
    temp_root = Path(tempfile.mkdtemp(prefix="elysia_memory_health_smoke_"))
    dest = temp_root / "demo_workspace"
    errors: List[str] = []
    demo_summary: Dict[str, Any] = {}
    doctor_report: Dict[str, Any] = {}
    doctor_verdict = ""
    candidates_created = 0
    approvals_created = 0
    search_result_count = 0
    context_bundle_created = False
    demo_workspace_created = False

    try:
        demo = create_memory_demo_workspace(
            dest_dir=dest,
            apply=True,
            run_pipeline=True,
        )
        demo_summary = demo.to_dict()
        demo_workspace_created = dest.is_dir()
        candidates_created = demo.candidates_created
        approvals_created = demo.approvals_created
        search_result_count = demo.search_result_count
        context_bundle_created = demo.context_bundle_created

        doctor = run_memory_doctor(dest)
        doctor_report = doctor.to_dict()
        doctor_verdict = doctor.verdict

        if demo.verdict != "PASS":
            errors.extend(demo.errors or ["Demo pipeline failed."])
        if doctor.verdict != HAS_CONTEXT_BUNDLE:
            errors.append(f"Expected doctor verdict {HAS_CONTEXT_BUNDLE}, got {doctor.verdict}.")
        if candidates_created < 1:
            errors.append("No candidates were created.")
        if approvals_created < 1:
            errors.append("No approvals were created.")
        if search_result_count < 1:
            errors.append("Search returned no approved memories.")
        if not context_bundle_created:
            errors.append("Context bundle was not created.")
        if any(
            [
                demo.model_called,
                demo.embeddings_used,
                demo.live_memory_written,
                demo.autonomy_enabled,
                doctor.model_called,
                doctor.embeddings_used,
                doctor.live_memory_written,
                doctor.autonomy_enabled,
            ]
        ):
            errors.append("A safety flag was unexpectedly enabled.")
    except Exception as exc:  # noqa: BLE001 - report smoke failures as JSON instead of crashing.
        errors.append(str(exc))
    finally:
        if not keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)

    return MemoryHealthSmokeReport(
        verdict="PASS" if not errors else "FAIL",
        demo_workspace_created=demo_workspace_created,
        doctor_verdict=doctor_verdict,
        candidates_created=candidates_created,
        approvals_created=approvals_created,
        search_result_count=search_result_count,
        context_bundle_created=context_bundle_created,
        temp_path=str(temp_root) if keep_temp else None,
        model_called=False,
        embeddings_used=False,
        live_memory_written=False,
        autonomy_enabled=False,
        errors=errors,
        demo_summary=demo_summary,
        doctor_report=doctor_report,
    )


def format_memory_doctor_report(report: MemoryDoctorReport) -> str:
    lines = [
        "Memory doctor",
        "=" * 13,
        f"Verdict: {report.verdict}",
        f"Destination: {report.dest_dir}",
        f"Exists: {report.exists}",
        f"Import sessions: {report.import_session_count}",
        f"ChatGPT import sessions: {report.chatgpt_import_session_count}",
        f"Email import sessions: {report.email_import_session_count}",
        f"Pending candidates: {report.pending_candidates_count}",
        f"Review decisions: {report.review_decisions_count}",
        f"Approved decisions: {report.approved_decisions_count}",
        f"Rejected decisions: {report.rejected_decisions_count}",
        f"Approved export exists: {report.approved_export_exists}",
        f"Approved memory store exists: {report.approved_memory_store_exists}",
        f"Approved memory count: {report.approved_memory_count}",
        f"Context bundle files exist: {report.context_bundle_files_exist}",
        f"Import-ready files: {report.import_ready_file_count}",
        "",
        "Safety:",
        f"  model_called: {report.model_called}",
        f"  embeddings_used: {report.embeddings_used}",
        f"  live_memory_written: {report.live_memory_written}",
        f"  autonomy_enabled: {report.autonomy_enabled}",
    ]
    if report.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {warning}" for warning in report.warnings)
    return "\n".join(lines)


def format_memory_health_smoke_report(report: MemoryHealthSmokeReport) -> str:
    lines = [
        "Memory health smoke",
        "=" * 19,
        f"Verdict: {report.verdict}",
        f"Demo workspace created: {report.demo_workspace_created}",
        f"Doctor verdict: {report.doctor_verdict}",
        f"Candidates created: {report.candidates_created}",
        f"Approvals created: {report.approvals_created}",
        f"Search result count: {report.search_result_count}",
        f"Context bundle created: {report.context_bundle_created}",
        f"Temp path: {report.temp_path}",
        "",
        "Safety:",
        f"  model_called: {report.model_called}",
        f"  embeddings_used: {report.embeddings_used}",
        f"  live_memory_written: {report.live_memory_written}",
        f"  autonomy_enabled: {report.autonomy_enabled}",
    ]
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  - {error}" for error in report.errors)
    return "\n".join(lines)
