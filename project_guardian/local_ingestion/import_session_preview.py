"""Build UI-ready memory import session previews from explicit operator paths."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .transcription_ingest import DEFAULT_MAX_FILE_MB

IMPORT_SESSIONS_SUBDIR = "import_sessions"
PREVIEW_JSON = "import_session_preview.json"
PREVIEW_MD = "import_session_preview.md"

SUPPORTED_NOW = frozenset({".txt", ".md", ".vtt", ".srt"})
SUPPORTED_LATER = frozenset({".json", ".csv", ".eml", ".mbox", ".ics", ".docx", ".pdf"})

_CATEGORY_SUPPORTED_NOW = "supported_now"
_CATEGORY_SUPPORTED_LATER = "supported_later"
_CATEGORY_UNSUPPORTED = "unsupported"
_CATEGORY_SKIPPED = "skipped"


class ImportSessionPreviewError(Exception):
    """Raised when import session preview cannot be built safely."""


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
class ImportSessionPreviewReport:
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


def default_session_parent_dir(dest_dir: Path) -> Path:
    return Path(dest_dir) / IMPORT_SESSIONS_SUBDIR


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _looks_binary(raw: bytes) -> bool:
    if not raw:
        return False
    if b"\x00" in raw:
        return True
    sample = raw[:4096]
    if not sample:
        return False
    non_text = sum(1 for b in sample if b < 9 or (13 < b < 32 and b != 27))
    return (non_text / len(sample)) > 0.30


def _peek_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return _looks_binary(handle.read(4096))
    except OSError:
        return True


def _classify_extension(extension: str) -> Optional[str]:
    ext = extension.lower()
    if ext in SUPPORTED_NOW:
        return _CATEGORY_SUPPORTED_NOW
    if ext in SUPPORTED_LATER:
        return _CATEGORY_SUPPORTED_LATER
    return None


def _reason_for_category(category: str, *, extension: str = "") -> str:
    if category == _CATEGORY_SUPPORTED_NOW:
        return "Transcription or text file supported by the current ingestion pipeline."
    if category == _CATEGORY_SUPPORTED_LATER:
        return f"Planned future import support for {extension or 'this format'}."
    if category == _CATEGORY_UNSUPPORTED:
        if extension:
            return f"Unsupported or binary file type ({extension})."
        return "Unsupported or binary file type."
    return "Skipped during preview scan."


def _import_action_available(category: str) -> bool:
    return category == _CATEGORY_SUPPORTED_NOW


def _resolve_input_paths(inputs: Sequence[Path]) -> List[Path]:
    if not inputs:
        raise ImportSessionPreviewError("At least one explicit --input path is required.")
    resolved: List[Path] = []
    for raw in inputs:
        path = Path(raw)
        try:
            path = path.resolve(strict=False)
        except OSError as exc:
            raise ImportSessionPreviewError(f"Input path unavailable: {raw}") from exc
        if not path.exists():
            raise ImportSessionPreviewError(f"Input path not found: {raw}")
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


def _classify_file(path: Path, *, max_bytes: int) -> FileEntry:
    name = path.name
    extension = path.suffix.lower()
    try:
        stat = path.stat()
        size_bytes = int(stat.st_size)
    except OSError:
        return FileEntry(
            path=str(path),
            name=name,
            extension=extension,
            size_bytes=0,
            category=_CATEGORY_SKIPPED,
            reason="File could not be inspected.",
            import_action_available=False,
        )

    if path.is_symlink():
        return FileEntry(
            path=str(path),
            name=name,
            extension=extension,
            size_bytes=size_bytes,
            category=_CATEGORY_SKIPPED,
            reason="Symlinks are not followed during preview.",
            import_action_available=False,
        )

    if size_bytes > max_bytes:
        return FileEntry(
            path=str(path),
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
            path=str(path),
            name=name,
            extension=extension,
            size_bytes=size_bytes,
            category=known,
            reason=_reason_for_category(known, extension=extension),
            import_action_available=_import_action_available(known),
        )

    if _peek_binary(path):
        return FileEntry(
            path=str(path),
            name=name,
            extension=extension,
            size_bytes=size_bytes,
            category=_CATEGORY_UNSUPPORTED,
            reason=_reason_for_category(_CATEGORY_UNSUPPORTED, extension=extension or "(none)"),
            import_action_available=False,
        )

    return FileEntry(
        path=str(path),
        name=name,
        extension=extension,
        size_bytes=size_bytes,
        category=_CATEGORY_UNSUPPORTED,
        reason="Unknown text-like file type is not supported yet.",
        import_action_available=False,
    )


def _scan_input_path(path: Path, *, recursive: bool, max_bytes: int) -> List[FileEntry]:
    entries: List[FileEntry] = []
    if path.is_symlink():
        entries.append(
            FileEntry(
                path=str(path),
                name=path.name,
                extension=path.suffix.lower(),
                size_bytes=0,
                category=_CATEGORY_SKIPPED,
                reason="Symlinks are not followed during preview.",
                import_action_available=False,
            )
        )
        return entries

    if path.is_file():
        entries.append(_classify_file(path, max_bytes=max_bytes))
        return entries

    if path.is_dir():
        for child in _iter_files_in_directory(path, recursive=recursive):
            if child.is_dir():
                if not recursive:
                    entries.append(
                        FileEntry(
                            path=str(child),
                            name=child.name,
                            extension="",
                            size_bytes=0,
                            category=_CATEGORY_SKIPPED,
                            reason="Subdirectory requires --recursive.",
                            import_action_available=False,
                        )
                    )
                continue
            entries.append(_classify_file(child, max_bytes=max_bytes))
        return entries

    entries.append(
        FileEntry(
            path=str(path),
            name=path.name,
            extension=path.suffix.lower(),
            size_bytes=0,
            category=_CATEGORY_SKIPPED,
            reason="Path is not a readable file or directory.",
            import_action_available=False,
        )
    )
    return entries


def _build_summary(entries: Sequence[FileEntry]) -> Dict[str, int]:
    counts = {
        "total_inputs": 0,
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


def _build_next_actions(summary: Dict[str, int]) -> List[str]:
    actions: List[str] = ["No files were imported yet. This is a preview-only session."]
    if summary["supported_now_count"] > 0:
        actions.append(
            "These files can be imported as transcription memory candidates "
            "using the existing ingestion CLI when you are ready."
        )
    if summary["supported_later_count"] > 0:
        actions.append("These files are planned for later import support.")
    if summary["unsupported_count"] > 0:
        actions.append("Unsupported files were listed for review but will not be imported.")
    if summary["skipped_count"] > 0:
        actions.append("Some paths were skipped because of size limits, symlinks, or scan rules.")
    if summary["files_seen"] == 0:
        actions.append("No files were found in the provided inputs.")
    return actions


def _render_markdown(preview: Dict[str, Any]) -> str:
    summary = preview["summary"]
    lines = [
        "# Memory import session preview",
        "",
        f"**Session ID:** {preview['session_id']}",
        f"**Created:** {preview['created_at']}",
        "",
        "## Safety",
        "",
        "This is a preview-only session. No files were imported, no model was called, "
        "and no live memory was written.",
        "",
        "## Summary",
        "",
        f"- Total explicit inputs: {preview['total_inputs']}",
        f"- Files seen: {summary['files_seen']}",
        f"- Supported now: {summary['supported_now_count']}",
        f"- Supported later: {summary['supported_later_count']}",
        f"- Unsupported: {summary['unsupported_count']}",
        f"- Skipped: {summary['skipped_count']}",
        "",
        "## Next steps",
        "",
    ]
    for action in preview["next_actions"]:
        lines.append(f"- {action}")
    lines.extend(["", "## Files", ""])
    if not preview["file_entries"]:
        lines.append("_No files were found in the provided inputs._")
    else:
        for entry in preview["file_entries"]:
            lines.extend(
                [
                    f"### {entry['name']}",
                    f"- Path: `{entry['path']}`",
                    f"- Category: **{entry['category']}**",
                    f"- Size: {entry['size_bytes']} bytes",
                    f"- Reason: {entry['reason']}",
                    f"- Import action available: {entry['import_action_available']}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def preview_memory_import_session(
    *,
    dest_dir: Path,
    input_paths: Sequence[Path],
    recursive: bool = False,
    session_dir: Optional[Path] = None,
    max_file_mb: float = DEFAULT_MAX_FILE_MB,
) -> ImportSessionPreviewReport:
    """Preview explicit file/folder inputs for a future drag-and-drop import UI."""
    dest = Path(dest_dir)
    resolved_inputs = _resolve_input_paths(input_paths)
    max_bytes = int(max_file_mb * 1024 * 1024)
    session_id = _new_session_id()
    out_dir = Path(session_dir) if session_dir is not None else default_session_parent_dir(dest) / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    file_entries: List[FileEntry] = []
    for input_path in resolved_inputs:
        file_entries.extend(_scan_input_path(input_path, recursive=recursive, max_bytes=max_bytes))

    summary = _build_summary(file_entries)
    summary["total_inputs"] = len(resolved_inputs)
    next_actions = _build_next_actions(summary)

    preview: Dict[str, Any] = {
        "session_id": session_id,
        "created_at": _utc_now_iso(),
        "dest_dir": str(dest.resolve()),
        "recursive": recursive,
        "max_file_mb": max_file_mb,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "import_applied": False,
        "total_inputs": len(resolved_inputs),
        "source_paths": [str(p) for p in resolved_inputs],
        "file_entries": [entry.to_dict() for entry in file_entries],
        "summary": summary,
        "next_actions": next_actions,
    }

    json_path = out_dir / PREVIEW_JSON
    md_path = out_dir / PREVIEW_MD
    json_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(preview), encoding="utf-8")

    return ImportSessionPreviewReport(
        session_id=session_id,
        session_dir=str(out_dir),
        json_path=str(json_path),
        markdown_path=str(md_path),
        preview=preview,
    )
