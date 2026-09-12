"""End-to-end smoke run for the local memory ingestion pipeline (temp folders only)."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
from .chatgpt_export_ingest import (
    EXTRACTED_TEXT_SUBDIR,
    METADATA_SUBDIR,
    apply_chatgpt_export,
    preview_chatgpt_export,
)
from .email_export_ingest import (
    apply_email_export,
    preview_email_export,
)
from .import_session_apply import APPLY_REPORT_JSON, APPLY_REPORT_MD, apply_memory_import_session
from .import_session_preview import PREVIEW_JSON, PREVIEW_MD, preview_memory_import_session
from .memory_candidate_review import (
    REVIEW_DECISIONS_FILENAME,
    approve_candidate,
    list_candidates,
    resolve_review_paths,
)
from .memory_candidates import (
    REVIEW_QUEUE_FILENAME,
    SOURCE_TYPE_CHATGPT_EXPORT,
    SOURCE_TYPE_EMAIL_EXPORT,
    SOURCE_TYPE_PHONE_TRANSCRIPTION,
)

SOURCE_TYPE_TRANSCRIPTION = "transcription"
SOURCE_TYPE_CHATGPT = "chatgpt_export"
SOURCE_TYPE_EMAIL = "email_export"
VALID_SOURCE_TYPES = frozenset({SOURCE_TYPE_TRANSCRIPTION, SOURCE_TYPE_CHATGPT, SOURCE_TYPE_EMAIL})
DEFAULT_SOURCE_TYPE = SOURCE_TYPE_TRANSCRIPTION

SAMPLE_FILES = (
    ("drywall_quote.txt", "Customer asked for a drywall quote for the kitchen remodel."),
    ("schedule_materials.md", "# Schedule\n\nOrder lumber and drywall materials for next week."),
)
SEARCH_QUERY = "drywall quote"
CHATGPT_EXPORT_FILENAME = "conversations.json"
EMAIL_EML_FILENAME = "drywall_quote.eml"


class LocalMemoryPipelineSmokeError(Exception):
    """Raised when the local memory pipeline smoke run fails."""


@dataclass
class SmokeSummary:
    verdict: str
    temp_root: str
    source_type: str
    preview_created: bool
    apply_report_created: bool
    chatgpt_preview_created: bool
    chatgpt_apply_report_created: bool
    email_preview_created: bool
    email_apply_report_created: bool
    extracted_text_created: bool
    candidate_source_type: str
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


def _validate_source_type(source_type: str) -> str:
    normalized = str(source_type or DEFAULT_SOURCE_TYPE).strip().lower()
    if normalized not in VALID_SOURCE_TYPES:
        raise LocalMemoryPipelineSmokeError(
            f"Unknown source type {source_type!r}; expected one of: {', '.join(sorted(VALID_SOURCE_TYPES))}"
        )
    return normalized


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sample_files(source_dir: Path) -> List[Path]:
    source_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for name, content in SAMPLE_FILES:
        path = source_dir / name
        path.write_text(content, encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def _sample_chatgpt_export() -> list[dict]:
    return [
        {
            "title": "Drywall quote chat",
            "id": "conv-1",
            "create_time": 1700000000,
            "update_time": 1700000100,
            "current_node": "node-2",
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Need a drywall quote for the kitchen."]},
                        "create_time": 1700000001,
                    },
                },
                "node-2": {
                    "id": "node-2",
                    "parent": "node-1",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Sure, what are the dimensions?"]},
                        "create_time": 1700000002,
                    },
                },
            },
        },
        {
            "title": "Empty chat",
            "id": "conv-empty",
            "mapping": {},
        },
    ]


def _write_chatgpt_export(export_path: Path) -> None:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(json.dumps(_sample_chatgpt_export()), encoding="utf-8")


def _write_sample_eml(eml_path: Path) -> None:
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "From: sender@example.com",
        "To: user@example.com",
        "Subject: Drywall quote follow-up",
        "Date: Mon, 1 Jan 2026 12:00:00 +0000",
        "Message-ID: <smoke-email@example.com>",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Please send the drywall quote for the kitchen remodel.",
    ]
    eml_path.write_text("\n".join(lines), encoding="utf-8")


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


def _read_queue_records(queue_path: Path) -> List[Dict[str, Any]]:
    if not queue_path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _verify_candidate_records(
    queue_path: Path,
    *,
    expected_source_type: str,
    errors: List[str],
) -> None:
    records = _read_queue_records(queue_path)
    if not records:
        errors.append("Review queue has no candidate records.")
        return
    for record in records:
        if record.get("source_type") != expected_source_type:
            errors.append(
                f"Candidate source_type expected {expected_source_type!r}, got {record.get('source_type')!r}."
            )
        if record.get("review_status") != "pending":
            errors.append(
                f"Candidate review_status expected 'pending', got {record.get('review_status')!r}."
            )
        if record.get("live_memory_written") is not False:
            errors.append("Candidate live_memory_written is not false.")


def _finalize_review_export_search_context(
    *,
    dest_dir: Path,
    search_query: str,
    summary: SmokeSummary,
    errors: List[str],
) -> None:
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
        search_query,
        limit=5,
    )
    summary.search_result_count = search_report.count
    if summary.search_result_count < 1:
        errors.append(f"Search for '{search_query}' returned no results.")

    context_report = build_approved_memory_context(
        dest_dir=dest_dir,
        query=search_query,
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
        (queue_path, "review queue"),
        (decisions_path, "review decisions"),
        (export_path, "approved export"),
        (store_path, "memory store"),
        (context_json, "context JSON"),
        (context_md, "context Markdown"),
    ):
        if not path.is_file():
            errors.append(f"Missing artifact: {label} ({path})")


def _run_transcription_smoke(
    *,
    source_dir: Path,
    dest_dir: Path,
    summary: SmokeSummary,
    errors: List[str],
) -> None:
    sample_paths = _write_sample_files(source_dir)
    summary.candidate_source_type = SOURCE_TYPE_PHONE_TRANSCRIPTION

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

    queue_path = dest_dir / "memory_candidates" / REVIEW_QUEUE_FILENAME
    _verify_candidate_records(
        queue_path,
        expected_source_type=SOURCE_TYPE_PHONE_TRANSCRIPTION,
        errors=errors,
    )

    _finalize_review_export_search_context(
        dest_dir=dest_dir,
        search_query=SEARCH_QUERY,
        summary=summary,
        errors=errors,
    )

    for path, label in (
        (preview_json, "preview JSON"),
        (preview_md, "preview Markdown"),
        (apply_json, "apply JSON"),
        (apply_md, "apply Markdown"),
    ):
        if not path.is_file():
            errors.append(f"Missing artifact: {label} ({path})")


def _run_chatgpt_export_smoke(
    *,
    source_dir: Path,
    dest_dir: Path,
    summary: SmokeSummary,
    errors: List[str],
) -> None:
    export_path = source_dir / CHATGPT_EXPORT_FILENAME
    _write_chatgpt_export(export_path)
    export_hash_before = _file_sha256(export_path)
    summary.candidate_source_type = SOURCE_TYPE_CHATGPT_EXPORT

    preview = preview_chatgpt_export(export_json=export_path, dest_dir=dest_dir)
    preview_json = Path(preview.json_path)
    preview_md = Path(preview.markdown_path)
    session_dir = Path(preview.session_dir)
    summary.chatgpt_preview_created = preview_json.is_file() and preview_md.is_file()
    if not summary.chatgpt_preview_created:
        errors.append("ChatGPT preview JSON/Markdown were not created.")

    apply_report = apply_chatgpt_export(preview_json=preview_json, apply=True)
    apply_json = Path(apply_report.json_path)
    apply_md = Path(apply_report.markdown_path)
    summary.chatgpt_apply_report_created = apply_json.is_file() and apply_md.is_file()
    summary.candidates_created = int(apply_report.report.get("staged_count") or 0)
    if not summary.chatgpt_apply_report_created:
        errors.append("ChatGPT apply report JSON/Markdown were not created.")
    if summary.candidates_created < 1:
        errors.append("Expected at least one staged ChatGPT memory candidate.")

    extracted_dir = session_dir / EXTRACTED_TEXT_SUBDIR
    metadata_dir = session_dir / METADATA_SUBDIR
    summary.extracted_text_created = any(extracted_dir.glob("*.txt"))
    metadata_created = any(metadata_dir.glob("*.json"))
    if not summary.extracted_text_created:
        errors.append("ChatGPT extracted text files were not created.")
    if not metadata_created:
        errors.append("ChatGPT metadata files were not created.")

    queue_path = dest_dir / "memory_candidates" / REVIEW_QUEUE_FILENAME
    _verify_candidate_records(
        queue_path,
        expected_source_type=SOURCE_TYPE_CHATGPT_EXPORT,
        errors=errors,
    )

    _finalize_review_export_search_context(
        dest_dir=dest_dir,
        search_query=SEARCH_QUERY,
        summary=summary,
        errors=errors,
    )

    export_hash_after = _file_sha256(export_path)
    if export_hash_after != export_hash_before:
        errors.append("Source ChatGPT export file changed during smoke run.")

    for path, label in (
        (preview_json, "ChatGPT preview JSON"),
        (preview_md, "ChatGPT preview Markdown"),
        (apply_json, "ChatGPT apply JSON"),
        (apply_md, "ChatGPT apply Markdown"),
    ):
        if not path.is_file():
            errors.append(f"Missing artifact: {label} ({path})")


def _run_email_export_smoke(
    *,
    source_dir: Path,
    dest_dir: Path,
    summary: SmokeSummary,
    errors: List[str],
) -> None:
    eml_path = source_dir / EMAIL_EML_FILENAME
    _write_sample_eml(eml_path)
    eml_hash_before = _file_sha256(eml_path)
    summary.candidate_source_type = SOURCE_TYPE_EMAIL_EXPORT

    preview = preview_email_export(dest_dir=dest_dir, input_paths=[eml_path])
    preview_json = Path(preview.json_path)
    preview_md = Path(preview.markdown_path)
    session_dir = Path(preview.session_dir)
    summary.email_preview_created = preview_json.is_file() and preview_md.is_file()
    if not summary.email_preview_created:
        errors.append("Email preview JSON/Markdown were not created.")

    apply_report = apply_email_export(preview_json=preview_json, apply=True)
    apply_json = Path(apply_report.json_path)
    apply_md = Path(apply_report.markdown_path)
    summary.email_apply_report_created = apply_json.is_file() and apply_md.is_file()
    summary.candidates_created = int(apply_report.report.get("staged_count") or 0)
    if not summary.email_apply_report_created:
        errors.append("Email apply report JSON/Markdown were not created.")
    if summary.candidates_created < 1:
        errors.append("Expected at least one staged email memory candidate.")

    extracted_dir = session_dir / EXTRACTED_TEXT_SUBDIR
    metadata_dir = session_dir / METADATA_SUBDIR
    summary.extracted_text_created = any(extracted_dir.glob("*.txt"))
    metadata_created = any(metadata_dir.glob("*.json"))
    if not summary.extracted_text_created:
        errors.append("Email extracted text files were not created.")
    if not metadata_created:
        errors.append("Email metadata files were not created.")

    queue_path = dest_dir / "memory_candidates" / REVIEW_QUEUE_FILENAME
    _verify_candidate_records(
        queue_path,
        expected_source_type=SOURCE_TYPE_EMAIL_EXPORT,
        errors=errors,
    )

    _finalize_review_export_search_context(
        dest_dir=dest_dir,
        search_query=SEARCH_QUERY,
        summary=summary,
        errors=errors,
    )

    eml_hash_after = _file_sha256(eml_path)
    if eml_hash_after != eml_hash_before:
        errors.append("Source email export file changed during smoke run.")

    for path, label in (
        (preview_json, "Email preview JSON"),
        (preview_md, "Email preview Markdown"),
        (apply_json, "Email apply JSON"),
        (apply_md, "Email apply Markdown"),
    ):
        if not path.is_file():
            errors.append(f"Missing artifact: {label} ({path})")


def _empty_summary(temp_root: Path, source_type: str) -> SmokeSummary:
    return SmokeSummary(
        verdict="FAIL",
        temp_root=str(temp_root.resolve()),
        source_type=source_type,
        preview_created=False,
        apply_report_created=False,
        chatgpt_preview_created=False,
        chatgpt_apply_report_created=False,
        email_preview_created=False,
        email_apply_report_created=False,
        extracted_text_created=False,
        candidate_source_type="",
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
        errors=[],
    )


def run_local_memory_pipeline_smoke(
    *,
    base_dir: Optional[Path] = None,
    keep_temp: bool = False,
    source_type: str = DEFAULT_SOURCE_TYPE,
) -> SmokeSummary:
    """Run preview → apply → review → export → store → search → context on temp data."""
    if _read_autonomy_enabled():
        raise LocalMemoryPipelineSmokeError("Autonomy must remain disabled for smoke runs.")

    normalized_source = _validate_source_type(source_type)

    owned_temp = base_dir is None
    temp_root = Path(base_dir) if base_dir is not None else Path(
        tempfile.mkdtemp(prefix="elysia_local_memory_smoke_")
    )
    source_dir = temp_root / "source"
    dest_dir = temp_root / "dest"
    errors: List[str] = []

    summary = _empty_summary(temp_root, normalized_source)
    summary.errors = errors

    runners: Dict[str, Callable[..., None]] = {
        SOURCE_TYPE_TRANSCRIPTION: _run_transcription_smoke,
        SOURCE_TYPE_CHATGPT: _run_chatgpt_export_smoke,
        SOURCE_TYPE_EMAIL: _run_email_export_smoke,
    }

    try:
        runners[normalized_source](
            source_dir=source_dir,
            dest_dir=dest_dir,
            summary=summary,
            errors=errors,
        )
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
        f"Source type: {summary.source_type}",
        f"Temp root: {summary.temp_root}",
        "",
        f"Preview created: {summary.preview_created}",
        f"Apply report created: {summary.apply_report_created}",
        f"ChatGPT preview created: {summary.chatgpt_preview_created}",
        f"ChatGPT apply report created: {summary.chatgpt_apply_report_created}",
        f"Email preview created: {summary.email_preview_created}",
        f"Email apply report created: {summary.email_apply_report_created}",
        f"Extracted text created: {summary.extracted_text_created}",
        f"Candidate source type: {summary.candidate_source_type}",
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
