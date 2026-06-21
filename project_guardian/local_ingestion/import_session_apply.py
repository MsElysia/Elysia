"""Apply a reviewed import session preview to stage transcription memory candidates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .import_session_preview import _CATEGORY_SUPPORTED_NOW
from .transcription_ingest import (
    DEFAULT_MAX_FILE_MB,
    MANIFEST_FILENAME,
    ingest_transcription_files,
    normalize_transcription_text,
    _decode_text,
)

APPLY_REPORT_JSON = "import_session_apply_report.json"
APPLY_REPORT_MD = "import_session_apply_report.md"


class ImportSessionApplyError(Exception):
    """Raised when an import session cannot be applied safely."""


@dataclass
class ApplyFileResult:
    path: str
    name: str
    preview_category: str
    action: str
    reason: str
    ingest_status: Optional[str] = None
    candidate_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImportSessionApplyReport:
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


def _load_preview(session_json: Path) -> Dict[str, Any]:
    path = Path(session_json)
    if not path.is_file():
        raise ImportSessionApplyError(f"Session preview not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImportSessionApplyError(f"Malformed session preview JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ImportSessionApplyError("Session preview JSON must be an object.")
    if "file_entries" not in payload or "dest_dir" not in payload:
        raise ImportSessionApplyError("Session preview JSON is missing required fields.")
    return payload


def _validate_source_hash(path: Path, expected_sha256: str) -> bool:
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    decoded = _decode_text(raw)
    if decoded is None:
        return False
    normalized = normalize_transcription_text(decoded, path.suffix.lower())
    if not normalized:
        return False
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest == expected_sha256


def _evaluate_preview_entry(entry: Dict[str, Any]) -> Tuple[Optional[Path], str, str]:
    """Return (path to ingest, action, reason) for one preview file entry."""
    category = str(entry.get("category") or "")
    name = str(entry.get("name") or Path(str(entry.get("path") or "")).name)
    path_str = str(entry.get("path") or "")

    if category != _CATEGORY_SUPPORTED_NOW or not entry.get("import_action_available"):
        return None, "skipped_preview_category", f"Not eligible for apply ({category})."

    if not path_str:
        return None, "skipped_missing_path", "Preview entry has no path."

    path = Path(path_str)
    if path.is_symlink():
        return None, "skipped_symlink", "Symlinks are not followed during apply."

    if not path.is_file():
        return None, "skipped_missing_source", "Source file no longer exists."

    try:
        current_size = int(path.stat().st_size)
    except OSError:
        return None, "skipped_unreadable", "Source file could not be inspected."

    preview_size = int(entry.get("size_bytes") or 0)
    if preview_size != current_size:
        return (
            None,
            "skipped_size_changed",
            f"Source size changed (preview {preview_size}, current {current_size}).",
        )

    expected_sha = str(entry.get("sha256") or entry.get("text_sha256") or "").strip()
    if expected_sha and not _validate_source_hash(path, expected_sha):
        return None, "skipped_hash_mismatch", "Source content no longer matches preview hash."

    return path, "eligible", "Eligible for transcription ingestion."


def _ingest_action_from_status(status: str, *, dry_run: bool) -> str:
    if status == "ingested":
        return "imported"
    if status == "dry_run":
        return "dry_run_would_import"
    if status == "duplicate":
        return "duplicate"
    return status


def _render_apply_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Memory import session apply report",
        "",
        f"**Session ID:** {report['session_id']}",
        f"**Applied at:** {report['applied_at']}",
        f"**Dry run:** {report['dry_run']}",
        f"**Apply requested:** {report['apply_requested']}",
        "",
        "## Safety",
        "",
        "No model was called. No embeddings were used. No live memory was written.",
        "",
        "## Summary",
        "",
        f"- Imported: {report['imported_count']}",
        f"- Candidates staged: {report['candidate_count']}",
        f"- Skipped: {report['skipped_count']}",
        "",
        "## Files",
        "",
    ]
    for entry in report["files"]:
        lines.extend(
            [
                f"### {entry['name']}",
                f"- Path: `{entry['path']}`",
                f"- Preview category: {entry['preview_category']}",
                f"- Action: **{entry['action']}**",
                f"- Reason: {entry['reason']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def apply_memory_import_session(
    *,
    session_json: Path,
    apply: bool = False,
) -> ImportSessionApplyReport:
    """Apply supported_now files from a preview session JSON (dry-run by default)."""
    session_path = Path(session_json).resolve()
    preview = _load_preview(session_path)
    session_dir = session_path.parent
    session_id = str(preview.get("session_id") or session_dir.name)
    dest_dir = Path(str(preview["dest_dir"]))
    max_file_mb = float(preview.get("max_file_mb") or DEFAULT_MAX_FILE_MB)

    file_results: List[ApplyFileResult] = []
    paths_to_ingest: List[Path] = []
    ingest_path_set: set[str] = set()

    for entry in preview.get("file_entries") or []:
        if not isinstance(entry, dict):
            continue
        path, action, reason = _evaluate_preview_entry(entry)
        category = str(entry.get("category") or "")
        name = str(entry.get("name") or "")
        path_str = str(entry.get("path") or "")
        if path is not None:
            resolved = str(path.resolve())
            if resolved not in ingest_path_set:
                paths_to_ingest.append(path)
                ingest_path_set.add(resolved)
            file_results.append(
                ApplyFileResult(
                    path=path_str,
                    name=name,
                    preview_category=category,
                    action="pending_ingest" if apply else "dry_run_would_import",
                    reason=reason,
                )
            )
        else:
            file_results.append(
                ApplyFileResult(
                    path=path_str,
                    name=name,
                    preview_category=category,
                    action=action,
                    reason=reason,
                )
            )

    ingest_report = None
    if paths_to_ingest:
        ingest_report = ingest_transcription_files(
            paths_to_ingest,
            dest_dir,
            apply=apply,
            max_file_mb=max_file_mb,
            stage_memory_candidates=apply,
        )
        ingest_by_path = {r.original_path: r for r in ingest_report.results}
        for file_result in file_results:
            if file_result.action not in {"pending_ingest", "dry_run_would_import"}:
                continue
            ingest_result = ingest_by_path.get(str(Path(file_result.path).resolve()))
            if ingest_result is None:
                file_result.action = "skipped_ingest_miss"
                file_result.reason = "File was not processed by ingestion."
                continue
            file_result.ingest_status = ingest_result.status
            file_result.action = _ingest_action_from_status(ingest_result.status, dry_run=not apply)
            file_result.candidate_status = ingest_result.memory_candidate_status
            if ingest_result.status == "duplicate":
                file_result.reason = "Duplicate content already ingested."
            elif ingest_result.status in {"ingested", "dry_run"}:
                file_result.reason = (
                    "Imported and candidate staged."
                    if ingest_result.memory_candidate_status == "staged"
                    else "Imported through transcription pipeline."
                    if ingest_result.status == "ingested"
                    else "Would import through transcription pipeline."
                )
            else:
                file_result.reason = ingest_result.status

    imported_count = sum(1 for f in file_results if f.action == "imported")
    candidate_count = sum(1 for f in file_results if f.candidate_status == "staged")
    skipped_count = sum(1 for f in file_results if f.action.startswith("skipped_"))

    payload: Dict[str, Any] = {
        "session_id": session_id,
        "applied_at": _utc_now_iso(),
        "dry_run": not apply,
        "apply_requested": apply,
        "imported_count": imported_count,
        "candidate_count": candidate_count,
        "skipped_count": skipped_count,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "session_json": str(session_path),
        "dest_dir": str(dest_dir.resolve()),
        "files": [f.to_dict() for f in file_results],
    }
    if ingest_report is not None:
        payload["ingest_summary"] = {
            "scanned": ingest_report.scanned,
            "ingested": ingest_report.ingested,
            "duplicates": ingest_report.duplicates,
            "skipped": ingest_report.skipped,
            "candidates_staged": ingest_report.candidates_staged,
            "candidates_duplicate": ingest_report.candidates_duplicate,
        }

    json_path = session_dir / APPLY_REPORT_JSON
    md_path = session_dir / APPLY_REPORT_MD
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_apply_markdown(payload), encoding="utf-8")

    return ImportSessionApplyReport(
        session_id=session_id,
        session_dir=str(session_dir),
        json_path=str(json_path),
        markdown_path=str(md_path),
        report=payload,
    )
