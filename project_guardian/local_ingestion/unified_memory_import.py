"""Unified local memory import preview/apply routing (no UI, no network, no models)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from project_guardian.chatgpt_export_import import iter_conversations_from_json_list

from .chatgpt_export_ingest import (
    PREVIEW_JSON as CHATGPT_PREVIEW_JSON,
    ChatGPTExportIngestError,
    apply_chatgpt_export,
    preview_chatgpt_export,
)
from .email_export_ingest import (
    PREVIEW_JSON as EMAIL_PREVIEW_JSON,
    EmailExportIngestError,
    apply_email_export,
    preview_email_export,
)
from .import_session_apply import (
    ImportSessionApplyError,
    apply_memory_import_session,
)
from .import_session_preview import (
    PREVIEW_JSON as TRANSCRIPTION_PREVIEW_JSON,
    ImportSessionPreviewError,
    preview_memory_import_session,
)
from .transcription_ingest import DEFAULT_MAX_FILE_MB

SOURCE_TYPE_TRANSCRIPTION = "transcription"
SOURCE_TYPE_CHATGPT = "chatgpt_export"
SOURCE_TYPE_EMAIL = "email_export"

VALID_SOURCE_TYPES = frozenset(
    {
        SOURCE_TYPE_TRANSCRIPTION,
        SOURCE_TYPE_CHATGPT,
        SOURCE_TYPE_EMAIL,
    }
)

TRANSCRIPTION_EXTENSIONS = frozenset({".txt", ".md", ".vtt", ".srt"})
EMAIL_EXTENSIONS = frozenset({".eml"})
CHATGPT_JSON_NAME = "conversations.json"
_CONVERSATIONS_JSON_RE = re.compile(r"^conversations-\d+\.json$", re.IGNORECASE)


class UnifiedMemoryImportError(Exception):
    """Raised when unified memory import cannot proceed safely."""


@dataclass
class UnifiedPreviewSummary:
    source_type: str
    session_json: str
    session_markdown: str
    items_seen: int
    candidates_available: int
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    autonomy_enabled: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedApplySummary:
    source_type: str
    dry_run: bool
    candidates_staged: int
    apply_report_path: str
    model_called: bool = False
    embeddings_used: bool = False
    live_memory_written: bool = False
    autonomy_enabled: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)

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
    normalized = str(source_type or "").strip().lower()
    if normalized not in VALID_SOURCE_TYPES:
        raise UnifiedMemoryImportError(
            f"Unknown source type {source_type!r}; expected one of: "
            f"{', '.join(sorted(VALID_SOURCE_TYPES))}"
        )
    return normalized


def _is_chatgpt_json_name(name: str) -> bool:
    lowered = name.lower()
    return lowered == CHATGPT_JSON_NAME or bool(_CONVERSATIONS_JSON_RE.match(name))


def _looks_like_chatgpt_export_json(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    if path.suffix.lower() != ".json" and not _is_chatgpt_json_name(path.name):
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return False
    for conv in iter_conversations_from_json_list(data):
        if isinstance(conv, dict) and isinstance(conv.get("mapping"), dict):
            return True
    return False


def _iter_scan_files(path: Path, *, recursive: bool) -> List[Path]:
    if path.is_symlink():
        return []
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    if recursive:
        return [p for p in path.rglob("*") if p.is_file() and not p.is_symlink()]
    return [p for p in path.iterdir() if p.is_file() and not p.is_symlink()]


def _detect_file_source_type(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext in TRANSCRIPTION_EXTENSIONS:
        return SOURCE_TYPE_TRANSCRIPTION
    if ext in EMAIL_EXTENSIONS:
        return SOURCE_TYPE_EMAIL
    if _is_chatgpt_json_name(path.name) or (
        ext == ".json" and _looks_like_chatgpt_export_json(path)
    ):
        return SOURCE_TYPE_CHATGPT
    return None


def detect_source_types(
    input_paths: Sequence[Path],
    *,
    recursive: bool = False,
) -> Set[str]:
    detected: Set[str] = set()
    for raw in input_paths:
        path = Path(raw)
        for file_path in _iter_scan_files(path, recursive=recursive):
            source = _detect_file_source_type(file_path)
            if source is not None:
                detected.add(source)
    return detected


def resolve_source_type(
    input_paths: Sequence[Path],
    *,
    source_type: Optional[str] = None,
    recursive: bool = False,
) -> str:
    if source_type is not None and str(source_type).strip():
        return _validate_source_type(source_type)

    detected = detect_source_types(input_paths, recursive=recursive)
    if not detected:
        raise UnifiedMemoryImportError(
            "Could not detect a supported memory import source type from the provided paths. "
            "Use --source-type with one of: transcription, chatgpt_export, email_export."
        )
    if len(detected) > 1:
        types = ", ".join(sorted(detected))
        raise UnifiedMemoryImportError(
            f"Mixed source types detected ({types}). "
            "Provide --source-type explicitly for folders containing multiple import kinds."
        )
    return next(iter(detected))


def _resolve_chatgpt_export_path(input_paths: Sequence[Path]) -> Path:
    candidates: List[Path] = []
    for raw in input_paths:
        path = Path(raw)
        if path.is_symlink():
            continue
        if path.is_file():
            candidates.append(path)
            continue
        if path.is_dir():
            named = path / CHATGPT_JSON_NAME
            if named.is_file() and not named.is_symlink():
                candidates.append(named)
            candidates.extend(
                p
                for p in sorted(path.glob("conversations-*.json"))
                if p.is_file() and not p.is_symlink()
            )
            single_json = [
                p for p in sorted(path.glob("*.json")) if p.is_file() and not p.is_symlink()
            ]
            candidates.extend(single_json)

    seen: set[str] = set()
    unique: List[Path] = []
    for candidate in candidates:
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    chatgpt_like = [p for p in unique if _looks_like_chatgpt_export_json(p)]
    if len(chatgpt_like) == 1:
        return chatgpt_like[0]
    if len(chatgpt_like) > 1:
        raise UnifiedMemoryImportError(
            "Multiple ChatGPT export JSON files found; provide a single explicit export file."
        )
    if len(unique) == 1:
        return unique[0]
    raise UnifiedMemoryImportError(
        "No ChatGPT export JSON found. Expected conversations.json or a JSON export file."
    )


def detect_source_type_from_session_json(session_json: Path) -> str:
    path = Path(session_json)
    name = path.name.lower()
    if name == TRANSCRIPTION_PREVIEW_JSON.lower():
        return SOURCE_TYPE_TRANSCRIPTION
    if name == CHATGPT_PREVIEW_JSON.lower():
        return SOURCE_TYPE_CHATGPT
    if name == EMAIL_PREVIEW_JSON.lower():
        return SOURCE_TYPE_EMAIL

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnifiedMemoryImportError(f"Cannot read session JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise UnifiedMemoryImportError("Session JSON must be an object.")

    if "conversations" in payload and "export_path" in payload:
        return SOURCE_TYPE_CHATGPT
    if "summary" in payload and isinstance(payload.get("summary"), dict):
        return SOURCE_TYPE_TRANSCRIPTION
    if "file_entries" in payload and isinstance(payload.get("file_entries"), list):
        return SOURCE_TYPE_EMAIL

    raise UnifiedMemoryImportError(
        "Could not determine source type from session JSON. "
        "Use a preview JSON from transcription, ChatGPT export, or email export."
    )


def _preview_counts(source_type: str, preview: Dict[str, Any]) -> tuple[int, int]:
    if source_type == SOURCE_TYPE_CHATGPT:
        items = int(preview.get("conversation_count") or 0)
        candidates = int(preview.get("candidate_count_estimate") or 0)
        return items, candidates
    if source_type == SOURCE_TYPE_EMAIL:
        entries = preview.get("file_entries") or []
        items = len(entries)
        candidates = sum(
            1
            for entry in entries
            if isinstance(entry, dict) and entry.get("import_action_available")
        )
        return items, candidates
    summary = preview.get("summary") or {}
    items = int(summary.get("files_seen") or 0)
    candidates = int(summary.get("supported_now_count") or 0)
    return items, candidates


def format_preview_operator_summary(summary: UnifiedPreviewSummary) -> str:
    label = {
        SOURCE_TYPE_TRANSCRIPTION: "files",
        SOURCE_TYPE_CHATGPT: "conversations",
        SOURCE_TYPE_EMAIL: "emails",
    }.get(summary.source_type, "items")
    lines = [
        "Unified memory import preview",
        f"  source_type: {summary.source_type}",
        f"  session JSON: {summary.session_json}",
        f"  session Markdown: {summary.session_markdown}",
        f"  {label} seen: {summary.items_seen}",
        f"  candidates available later: {summary.candidates_available}",
        "  No memory was written.",
    ]
    return "\n".join(lines)


def format_apply_operator_summary(summary: UnifiedApplySummary) -> str:
    mode = "dry-run" if summary.dry_run else "applied"
    lines = [
        "Unified memory import apply",
        f"  source_type: {summary.source_type}",
        f"  mode: {mode}",
        f"  candidates staged: {summary.candidates_staged}",
        f"  apply report: {summary.apply_report_path}",
        "  No live memory was written.",
    ]
    return "\n".join(lines)


def unified_preview_memory_import(
    *,
    dest_dir: Path,
    input_paths: Sequence[Path],
    source_type: Optional[str] = None,
    recursive: bool = False,
    max_file_mb: float = DEFAULT_MAX_FILE_MB,
) -> UnifiedPreviewSummary:
    if _read_autonomy_enabled():
        raise UnifiedMemoryImportError("Autonomy is enabled; unified memory import is blocked.")

    resolved = resolve_source_type(input_paths, source_type=source_type, recursive=recursive)
    autonomy_enabled = _read_autonomy_enabled()

    if resolved == SOURCE_TYPE_TRANSCRIPTION:
        try:
            report = preview_memory_import_session(
                dest_dir=dest_dir,
                input_paths=input_paths,
                recursive=recursive,
                max_file_mb=max_file_mb,
            )
        except ImportSessionPreviewError as exc:
            raise UnifiedMemoryImportError(str(exc)) from exc
    elif resolved == SOURCE_TYPE_CHATGPT:
        export_json = _resolve_chatgpt_export_path(input_paths)
        try:
            report = preview_chatgpt_export(
                export_json=export_json,
                dest_dir=dest_dir,
            )
        except ChatGPTExportIngestError as exc:
            raise UnifiedMemoryImportError(str(exc)) from exc
    else:
        try:
            report = preview_email_export(
                dest_dir=dest_dir,
                input_paths=input_paths,
                recursive=recursive,
                max_file_mb=max_file_mb,
            )
        except EmailExportIngestError as exc:
            raise UnifiedMemoryImportError(str(exc)) from exc

    items_seen, candidates_available = _preview_counts(resolved, report.preview)
    return UnifiedPreviewSummary(
        source_type=resolved,
        session_json=report.json_path,
        session_markdown=report.markdown_path,
        items_seen=items_seen,
        candidates_available=candidates_available,
        model_called=False,
        embeddings_used=False,
        live_memory_written=False,
        autonomy_enabled=autonomy_enabled,
        detail=report.to_dict(),
    )


def unified_apply_memory_import(
    *,
    session_json: Path,
    apply: bool = False,
) -> UnifiedApplySummary:
    if _read_autonomy_enabled():
        raise UnifiedMemoryImportError("Autonomy is enabled; unified memory import is blocked.")

    source_type = detect_source_type_from_session_json(session_json)
    autonomy_enabled = _read_autonomy_enabled()

    if source_type == SOURCE_TYPE_TRANSCRIPTION:
        try:
            report = apply_memory_import_session(session_json=session_json, apply=apply)
        except ImportSessionApplyError as exc:
            raise UnifiedMemoryImportError(str(exc)) from exc
        payload = report.report
        candidates_staged = int(payload.get("candidate_count") or 0) if apply else 0
    elif source_type == SOURCE_TYPE_CHATGPT:
        try:
            report = apply_chatgpt_export(preview_json=session_json, apply=apply)
        except ChatGPTExportIngestError as exc:
            raise UnifiedMemoryImportError(str(exc)) from exc
        payload = report.report
        candidates_staged = int(payload.get("staged_count") or 0) if apply else 0
    else:
        try:
            report = apply_email_export(preview_json=session_json, apply=apply)
        except EmailExportIngestError as exc:
            raise UnifiedMemoryImportError(str(exc)) from exc
        payload = report.report
        candidates_staged = int(payload.get("staged_count") or 0) if apply else 0

    return UnifiedApplySummary(
        source_type=source_type,
        dry_run=not apply,
        candidates_staged=candidates_staged if apply else 0,
        apply_report_path=report.json_path,
        model_called=False,
        embeddings_used=False,
        live_memory_written=False,
        autonomy_enabled=autonomy_enabled,
        detail=report.to_dict(),
    )
