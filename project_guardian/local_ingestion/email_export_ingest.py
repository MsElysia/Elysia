"""Preview and apply local `.eml` email exports into memory candidates (no network/accounts)."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .memory_candidates import (
    SOURCE_TYPE_EMAIL_EXPORT,
    SUGGESTED_MEMORY_TYPE_EMAIL,
    make_candidate_id,
    read_known_candidate_ids,
    review_queue_path,
    stage_memory_candidate,
)
from .transcription_ingest import DEFAULT_MAX_FILE_MB

EMAIL_IMPORT_SESSIONS_SUBDIR = "email_import_sessions"
PREVIEW_JSON = "email_export_preview.json"
PREVIEW_MD = "email_export_preview.md"
APPLY_REPORT_JSON = "email_export_apply_report.json"
APPLY_REPORT_MD = "email_export_apply_report.md"
EXTRACTED_TEXT_SUBDIR = "extracted_text"
METADATA_SUBDIR = "metadata"

SUPPORTED_NOW = frozenset({".eml"})
SUPPORTED_LATER = frozenset({".mbox"})

_CATEGORY_SUPPORTED_NOW = "supported_now"
_CATEGORY_SUPPORTED_LATER = "supported_later"
_CATEGORY_UNSUPPORTED = "unsupported"
_CATEGORY_SKIPPED = "skipped"


class EmailExportIngestError(Exception):
    """Raised when email export preview/apply cannot proceed safely."""


@dataclass
class FileEntry:
    path: str
    name: str
    extension: str
    size_bytes: int
    category: str
    reason: str
    import_action_available: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EmailExportPreviewReport:
    session_id: str
    session_dir: str
    json_path: str
    markdown_path: str
    preview: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_dir": self.session_dir,
            "json_path": self.json_path,
            "markdown_path": self.markdown_path,
            "preview": self.preview,
        }


@dataclass
class EmailExportApplyReport:
    session_id: str
    session_dir: str
    json_path: str
    markdown_path: str
    report: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_dir": self.session_dir,
            "json_path": self.json_path,
            "markdown_path": self.markdown_path,
            "report": self.report,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _reject_symlink(path: Path, *, label: str) -> None:
    raw = Path(path)
    if raw.is_symlink():
        raise EmailExportIngestError(f"Symlinks are not followed for {label}.")


def _safe_resolve(path: Path, *, label: str) -> Path:
    raw = Path(path)
    _reject_symlink(raw, label=label)
    return raw.resolve()


def _classify_extension(extension: str) -> Optional[str]:
    ext = extension.lower()
    if ext in SUPPORTED_NOW:
        return _CATEGORY_SUPPORTED_NOW
    if ext in SUPPORTED_LATER:
        return _CATEGORY_SUPPORTED_LATER
    return None


def _reason_for_category(category: str, *, extension: str = "") -> str:
    if category == _CATEGORY_SUPPORTED_NOW:
        return "Local .eml email export supported by the current ingestion pipeline."
    if category == _CATEGORY_SUPPORTED_LATER:
        return f"Planned future import support for {extension or 'this format'} (.mbox not imported yet)."
    if category == _CATEGORY_UNSUPPORTED:
        if extension:
            return f"Unsupported file type for email export import ({extension})."
        return "Unsupported file type for email export import."
    return "Skipped during preview scan."


def _import_action_available(category: str) -> bool:
    return category == _CATEGORY_SUPPORTED_NOW


def _resolve_input_paths(inputs: Sequence[Path]) -> List[Path]:
    if not inputs:
        raise EmailExportIngestError("At least one explicit --input path is required.")
    resolved: List[Path] = []
    for raw in inputs:
        path = _safe_resolve(Path(raw), label="input path")
        if not path.exists():
            raise EmailExportIngestError(f"Input path not found: {raw}")
        resolved.append(path)
    return resolved


def _iter_files_in_directory(directory: Path, *, recursive: bool) -> Iterable[Path]:
    if recursive:
        for root, dirnames, filenames in os.walk(directory, followlinks=False):
            root_path = Path(root)
            dirnames[:] = [d for d in dirnames if not (root_path / d).is_symlink()]
            for name in sorted(filenames):
                yield root_path / name
        return
    for entry in sorted(directory.iterdir()):
        if entry.is_symlink():
            yield entry
        elif entry.is_file():
            yield entry


def _skipped_symlink_entry(path: Path) -> FileEntry:
    raw = Path(path)
    return FileEntry(
        path=str(raw),
        name=raw.name,
        extension=raw.suffix.lower(),
        size_bytes=0,
        category=_CATEGORY_SKIPPED,
        reason="Symlinks are not followed during preview.",
        import_action_available=False,
    )


def _classify_file(path: Path, *, max_bytes: int) -> FileEntry:
    raw = Path(path)
    if raw.is_symlink():
        return _skipped_symlink_entry(raw)

    name = raw.name
    extension = raw.suffix.lower()
    try:
        stat = raw.stat()
        size_bytes = int(stat.st_size)
    except OSError:
        return FileEntry(
            path=str(raw),
            name=name,
            extension=extension,
            size_bytes=0,
            category=_CATEGORY_SKIPPED,
            reason="File could not be inspected.",
            import_action_available=False,
        )

    if size_bytes > max_bytes:
        return FileEntry(
            path=str(raw),
            name=name,
            extension=extension,
            size_bytes=size_bytes,
            category=_CATEGORY_SKIPPED,
            reason=f"File exceeds max size ({size_bytes} bytes).",
            import_action_available=False,
        )

    known = _classify_extension(extension)
    if known is not None:
        return FileEntry(
            path=str(raw),
            name=name,
            extension=extension,
            size_bytes=size_bytes,
            category=known,
            reason=_reason_for_category(known, extension=extension),
            import_action_available=_import_action_available(known),
        )

    return FileEntry(
        path=str(raw),
        name=name,
        extension=extension,
        size_bytes=size_bytes,
        category=_CATEGORY_UNSUPPORTED,
        reason=_reason_for_category(_CATEGORY_UNSUPPORTED, extension=extension or "(none)"),
        import_action_available=False,
    )


def _scan_input_path(path: Path, *, recursive: bool, max_bytes: int) -> List[FileEntry]:
    entries: List[FileEntry] = []
    raw = Path(path)
    if raw.is_symlink():
        entries.append(_skipped_symlink_entry(raw))
        return entries

    if raw.is_file():
        entries.append(_classify_file(raw, max_bytes=max_bytes))
        return entries

    if raw.is_dir():
        for child in _iter_files_in_directory(raw, recursive=recursive):
            child_path = Path(child)
            if child_path.is_symlink():
                entries.append(_skipped_symlink_entry(child_path))
                continue
            if child_path.is_dir():
                if not recursive:
                    entries.append(
                        FileEntry(
                            path=str(child_path),
                            name=child_path.name,
                            extension="",
                            size_bytes=0,
                            category=_CATEGORY_SKIPPED,
                            reason="Subdirectory requires --recursive.",
                            import_action_available=False,
                        )
                    )
                continue
            entries.append(_classify_file(child_path, max_bytes=max_bytes))
        return entries

    entries.append(
        FileEntry(
            path=str(raw),
            name=raw.name,
            extension=raw.suffix.lower(),
            size_bytes=0,
            category=_CATEGORY_SKIPPED,
            reason="Path is not a readable file or directory.",
            import_action_available=False,
        )
    )
    return entries


def _count_categories(entries: Sequence[FileEntry]) -> Dict[str, int]:
    counts = {
        "files_seen": len(entries),
        "supported_now_count": 0,
        "supported_later_count": 0,
        "unsupported_count": 0,
        "skipped_count": 0,
    }
    for entry in entries:
        if entry.category == _CATEGORY_SUPPORTED_NOW:
            counts["supported_now_count"] += 1
        elif entry.category == _CATEGORY_SUPPORTED_LATER:
            counts["supported_later_count"] += 1
        elif entry.category == _CATEGORY_UNSUPPORTED:
            counts["unsupported_count"] += 1
        elif entry.category == _CATEGORY_SKIPPED:
            counts["skipped_count"] += 1
    return counts


def _strip_html(html_body: str) -> str:
    without_blocks = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_body)
    without_tags = re.sub(r"<[^>]+>", " ", without_blocks)
    unescaped = html.unescape(without_tags)
    return " ".join(unescaped.split())


def _is_attachment(part: Any) -> bool:
    disposition = str(part.get_content_disposition() or "").lower()
    if disposition == "attachment":
        return True
    filename = part.get_filename()
    return bool(filename and disposition != "inline")


def _decode_payload(part: Any) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return str(raw or "")
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _extract_bodies(message: Any) -> Tuple[str, str, bool, bool, List[str]]:
    """Return plain_text, html_text, attachments_ignored, html_body_used, warnings."""
    plain_parts: List[str] = []
    html_parts: List[str] = []
    attachments_ignored = False
    warnings: List[str] = []

    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            if _is_attachment(part):
                attachments_ignored = True
                continue
            content_type = str(part.get_content_type() or "").lower()
            if content_type == "text/plain":
                plain_parts.append(_decode_payload(part).strip())
            elif content_type == "text/html":
                html_parts.append(_decode_payload(part).strip())
    else:
        content_type = str(message.get_content_type() or "").lower()
        body = _decode_payload(message).strip()
        if content_type == "text/html":
            html_parts.append(body)
        else:
            plain_parts.append(body)

    plain_text = "\n\n".join(p for p in plain_parts if p)
    html_text = "\n\n".join(p for p in html_parts if p)
    html_body_used = False

    if plain_text:
        return plain_text, html_text, attachments_ignored, False, warnings

    if html_text:
        html_body_used = True
        stripped = _strip_html(html_text)
        if not stripped:
            warnings.append("HTML body could not be converted to readable text.")
        return stripped, html_text, attachments_ignored, html_body_used, warnings

    warnings.append("No readable plain-text or HTML body found.")
    return "", html_text, attachments_ignored, html_body_used, warnings


def _format_header_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_format_header_value(v) for v in value if v)
    return str(value).strip()


def _format_date(message: Any) -> str:
    raw = message.get("Date")
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, IndexError):
        return str(raw).strip()


def extract_eml_content(path: Path) -> Tuple[str, Dict[str, Any]]:
    """Parse a local `.eml` file into readable text and metadata (no network)."""
    raw = Path(path)
    _reject_symlink(raw, label="email file")
    if not raw.is_file():
        raise EmailExportIngestError(f"Email file not found: {raw}")

    try:
        file_bytes = raw.read_bytes()
    except OSError as exc:
        raise EmailExportIngestError(f"Email file unreadable: {raw}") from exc

    try:
        message = BytesParser(policy=policy.default).parsebytes(file_bytes)
    except Exception as exc:
        raise EmailExportIngestError(f"Malformed email file: {raw}") from exc

    body_text, _html_raw, attachments_ignored, html_body_used, warnings = _extract_bodies(message)
    from_addr = _format_header_value(message.get("From"))
    to_addr = _format_header_value(message.get("To"))
    cc_addr = _format_header_value(message.get("Cc"))
    subject = _format_header_value(message.get("Subject")) or "(no subject)"
    date_str = _format_date(message)
    message_id = _format_header_value(message.get("Message-ID"))

    lines = [
        f"From: {from_addr}" if from_addr else "From:",
        f"To: {to_addr}" if to_addr else "To:",
    ]
    if cc_addr:
        lines.append(f"Cc: {cc_addr}")
    if date_str:
        lines.append(f"Date: {date_str}")
    lines.append(f"Subject: {subject}")
    lines.extend(["", "Body:", body_text if body_text else "(empty body)"])
    normalized = "\n".join(lines).strip() + "\n"

    metadata: Dict[str, Any] = {
        "from": from_addr,
        "to": to_addr,
        "cc": cc_addr,
        "date": date_str,
        "subject": subject,
        "message_id": message_id,
        "original_filename": raw.name,
        "attachments_ignored": attachments_ignored,
        "html_body_used": html_body_used,
        "extraction_warnings": warnings,
    }
    return normalized, metadata


def _render_preview_markdown(preview: Dict[str, Any]) -> str:
    lines = [
        "# Email export preview",
        "",
        f"**Session ID:** {preview['session_id']}",
        f"**Created:** {preview['created_at']}",
        "",
        "## Summary",
        "",
        f"- Files seen: {preview['files_seen']}",
        f"- Supported now (.eml): {preview['supported_now_count']}",
        f"- Supported later (.mbox): {preview['supported_later_count']}",
        f"- Unsupported: {preview['unsupported_count']}",
        f"- Skipped: {preview['skipped_count']}",
        "",
        "## Safety",
        "",
        "Preview-only. No memory candidates staged. No network or account access.",
        "",
        "## Files",
        "",
    ]
    for entry in preview.get("file_entries") or []:
        lines.extend(
            [
                f"### {entry['name']}",
                f"- Path: `{entry['path']}`",
                f"- Category: **{entry['category']}**",
                f"- Import available: {entry['import_action_available']}",
                f"- Reason: {entry['reason']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def preview_email_export(
    *,
    dest_dir: Path,
    input_paths: Sequence[Path],
    recursive: bool = False,
    session_dir: Optional[Path] = None,
    max_file_mb: float = DEFAULT_MAX_FILE_MB,
) -> EmailExportPreviewReport:
    dest = _safe_resolve(dest_dir, label="destination directory")
    resolved_inputs = _resolve_input_paths(input_paths)
    max_bytes = int(max_file_mb * 1024 * 1024)
    session_id = _new_session_id()
    out_dir = (
        Path(session_dir)
        if session_dir is not None
        else dest / EMAIL_IMPORT_SESSIONS_SUBDIR / session_id
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    file_entries: List[FileEntry] = []
    for input_path in resolved_inputs:
        file_entries.extend(_scan_input_path(input_path, recursive=recursive, max_bytes=max_bytes))

    counts = _count_categories(file_entries)
    preview: Dict[str, Any] = {
        "session_id": session_id,
        "created_at": _utc_now_iso(),
        "dest_dir": str(dest),
        "source_paths": [str(p) for p in resolved_inputs],
        "recursive": recursive,
        "max_file_mb": max_file_mb,
        "file_entries": [entry.to_dict() for entry in file_entries],
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "import_applied": False,
        **counts,
    }

    json_path = out_dir / PREVIEW_JSON
    md_path = out_dir / PREVIEW_MD
    json_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_preview_markdown(preview), encoding="utf-8")

    return EmailExportPreviewReport(
        session_id=session_id,
        session_dir=str(out_dir),
        json_path=str(json_path),
        markdown_path=str(md_path),
        preview=preview,
    )


def _load_preview_json(preview_json: Path) -> Dict[str, Any]:
    path = Path(preview_json)
    _reject_symlink(path, label="preview JSON")
    if not path.is_file():
        raise EmailExportIngestError(f"Preview JSON not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EmailExportIngestError(f"Malformed preview JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise EmailExportIngestError("Preview JSON must be an object.")
    for key in ("dest_dir", "file_entries", "session_id", "max_file_mb"):
        if key not in payload:
            raise EmailExportIngestError(f"Preview JSON missing required field: {key}")
    return payload


def _validate_file_unchanged(path: Path, expected_size: int) -> None:
    raw = Path(path)
    _reject_symlink(raw, label="email file")
    if not raw.is_file():
        raise EmailExportIngestError(f"Source file no longer exists: {raw}")
    try:
        current_size = int(raw.stat().st_size)
    except OSError as exc:
        raise EmailExportIngestError(f"Source file could not be inspected: {raw}") from exc
    if current_size != int(expected_size):
        raise EmailExportIngestError(
            f"Source file size changed (preview {expected_size}, current {current_size})."
        )


def _render_apply_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Email export apply report",
        "",
        f"**Session ID:** {report['session_id']}",
        f"**Applied at:** {report['applied_at']}",
        f"**Dry run:** {report['dry_run']}",
        "",
        "## Summary",
        "",
        f"- Staged: {report['staged_count']}",
        f"- Duplicates: {report['duplicate_count']}",
        f"- Skipped: {report['skipped_count']}",
        "",
        "## Files",
        "",
    ]
    for entry in report.get("files") or []:
        lines.extend(
            [
                f"### {entry.get('name', entry.get('path'))}",
                f"- Action: **{entry['action']}**",
                f"- Reason: {entry['reason']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def apply_email_export(
    *,
    preview_json: Path,
    apply: bool = False,
) -> EmailExportApplyReport:
    preview_path = _safe_resolve(preview_json, label="preview JSON")
    preview = _load_preview_json(preview_path)
    session_dir = preview_path.parent
    session_id = str(preview["session_id"])
    dest_dir = Path(str(preview["dest_dir"]))

    known_ids = read_known_candidate_ids(review_queue_path(dest_dir)) if apply else set()
    results: List[Dict[str, Any]] = []
    staged_count = 0
    duplicate_count = 0
    skipped_count = 0
    imported_at = _utc_now_iso()

    for entry in preview.get("file_entries") or []:
        name = str(entry.get("name") or "")
        path_str = str(entry.get("path") or "")
        category = str(entry.get("category") or "")

        if category != _CATEGORY_SUPPORTED_NOW or not entry.get("import_action_available"):
            skipped_count += 1
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "skipped_preview_category",
                    "reason": f"Not eligible for apply ({category}).",
                }
            )
            continue

        if not path_str:
            skipped_count += 1
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "skipped_missing_path",
                    "reason": "Preview entry has no path.",
                }
            )
            continue

        source_path = Path(path_str)
        try:
            _validate_file_unchanged(source_path, int(entry.get("size_bytes") or 0))
        except EmailExportIngestError as exc:
            skipped_count += 1
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "skipped_validation_failed",
                    "reason": str(exc),
                }
            )
            continue

        try:
            normalized_text, meta = extract_eml_content(source_path)
        except EmailExportIngestError as exc:
            skipped_count += 1
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "skipped_parse_failed",
                    "reason": str(exc),
                }
            )
            continue

        if not normalized_text.strip():
            skipped_count += 1
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "skipped_empty",
                    "reason": "No readable email text extracted.",
                }
            )
            continue

        source_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        candidate_id = make_candidate_id(source_sha256, name)
        text_path = session_dir / EXTRACTED_TEXT_SUBDIR / f"{candidate_id}.txt"
        meta_path = session_dir / METADATA_SUBDIR / f"{candidate_id}.json"

        if not apply:
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "dry_run_would_stage",
                    "reason": "Would stage memory candidate.",
                    "candidate_id": candidate_id,
                }
            )
            continue

        text_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(normalized_text, encoding="utf-8", newline="\n")
        meta["source_sha256"] = source_sha256
        meta["candidate_id"] = candidate_id
        meta["imported_at"] = imported_at
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        staged_at = _utc_now_iso()
        status, _wrote = stage_memory_candidate(
            dest_dir,
            source_text_path=text_path,
            source_metadata_path=meta_path,
            source_sha256=source_sha256,
            original_filename=name,
            imported_at=imported_at,
            staged_at=staged_at,
            normalized_text=normalized_text,
            known_candidate_ids=known_ids,
            source_type=SOURCE_TYPE_EMAIL_EXPORT,
            suggested_memory_type=SUGGESTED_MEMORY_TYPE_EMAIL,
        )
        if status == "staged":
            staged_count += 1
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "staged",
                    "reason": "Memory candidate staged for review.",
                    "candidate_id": candidate_id,
                }
            )
        else:
            duplicate_count += 1
            results.append(
                {
                    "path": path_str,
                    "name": name,
                    "action": "duplicate",
                    "reason": "Candidate already exists in review queue.",
                    "candidate_id": candidate_id,
                }
            )

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "applied_at": _utc_now_iso(),
        "dry_run": not apply,
        "apply_requested": apply,
        "staged_count": staged_count,
        "duplicate_count": duplicate_count,
        "skipped_count": skipped_count,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "preview_json": str(preview_path),
        "dest_dir": str(dest_dir.resolve()),
        "files": results,
    }

    json_path = session_dir / APPLY_REPORT_JSON
    md_path = session_dir / APPLY_REPORT_MD
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_apply_markdown(payload), encoding="utf-8")

    return EmailExportApplyReport(
        session_id=session_id,
        session_dir=str(session_dir),
        json_path=str(json_path),
        markdown_path=str(md_path),
        report=payload,
    )
