"""Preview and apply local ChatGPT export JSON into memory candidates (no API/network)."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from project_guardian.chatgpt_export_import import (
    extract_messages_ordered,
    iter_conversations_from_json_list,
)

from .memory_candidates import (
    SOURCE_TYPE_CHATGPT_EXPORT,
    SUGGESTED_MEMORY_TYPE_CONVERSATION,
    make_candidate_id,
    read_known_candidate_ids,
    review_queue_path,
    stage_memory_candidate,
)

CHATGPT_IMPORT_SESSIONS_SUBDIR = "chatgpt_import_sessions"
PREVIEW_JSON = "chatgpt_export_preview.json"
PREVIEW_MD = "chatgpt_export_preview.md"
APPLY_REPORT_JSON = "chatgpt_export_apply_report.json"
APPLY_REPORT_MD = "chatgpt_export_apply_report.md"
EXTRACTED_TEXT_SUBDIR = "extracted_text"
METADATA_SUBDIR = "metadata"
DEFAULT_MAX_CONVERSATION_CHARS = 50000


class ChatGPTExportIngestError(Exception):
    """Raised when ChatGPT export preview/apply cannot proceed safely."""


@dataclass
class ConversationPreviewEntry:
    conversation_id: str
    title: str
    create_time: Optional[float]
    update_time: Optional[float]
    message_count: int
    estimated_text_length: int
    status: str
    import_action_available: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChatGPTExportPreviewReport:
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
class ChatGPTExportApplyReport:
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
        raise ChatGPTExportIngestError(f"Symlinks are not followed for {label}.")


def _safe_resolve(path: Path, *, label: str) -> Path:
    raw = Path(path)
    _reject_symlink(raw, label=label)
    return raw.resolve()


def _conversation_id(conv: Dict[str, Any], index: int) -> str:
    cid = conv.get("conversation_id") or conv.get("id") or ""
    cid = str(cid).strip()
    if cid:
        return cid
    title = str(conv.get("title") or "untitled").strip()
    digest = hashlib.sha256(f"{title}:{index}".encode("utf-8")).hexdigest()[:16]
    return f"fallback-{digest}"


def _role_label(role: str) -> str:
    role = role.lower()
    if role == "user":
        return "User"
    if role == "assistant":
        return "Assistant"
    if role == "tool":
        return "Tool"
    return role.capitalize() or "Unknown"


def conversation_to_text(
    conv: Dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CONVERSATION_CHARS,
) -> Tuple[str, bool, int]:
    """Return (text, truncated, message_count)."""
    messages = extract_messages_ordered(conv)
    lines: List[str] = []
    title = str(conv.get("title") or "ChatGPT conversation").strip()
    if title:
        lines.append(f"# {title}")
        lines.append("")
    for role, text, _ts in messages:
        if role not in ("user", "assistant"):
            continue
        lines.append(f"{_role_label(role)}: {text}")
        lines.append("")
    body = "\n".join(lines).strip()
    truncated = False
    if len(body) > max_chars:
        body = body[: max_chars - 40].rstrip() + "\n\n[truncated for safety]"
        truncated = True
    return body, truncated, len(messages)


def _load_export_json(export_path: Path) -> Any:
    path = Path(export_path)
    _reject_symlink(path, label="export JSON")
    if not path.is_file():
        raise ChatGPTExportIngestError(f"Export JSON not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChatGPTExportIngestError(f"Malformed export JSON: {path}") from exc
    except OSError as exc:
        raise ChatGPTExportIngestError(f"Export JSON unreadable: {path}") from exc


def _parse_conversations(data: Any) -> List[Dict[str, Any]]:
    return list(iter_conversations_from_json_list(data))


def _candidate_key(export_name: str, conversation_id: str) -> str:
    return f"{export_name}#{conversation_id}"


def _analyze_conversation(
    conv: Dict[str, Any],
    index: int,
    *,
    export_name: str,
    max_conversation_chars: int,
) -> ConversationPreviewEntry:
    conversation_id = _conversation_id(conv, index)
    title = str(conv.get("title") or "Untitled conversation").strip() or "Untitled conversation"
    create_time = conv.get("create_time")
    update_time = conv.get("update_time")
    try:
        text, truncated, message_count = conversation_to_text(
            conv,
            max_chars=max_conversation_chars,
        )
    except Exception:
        return ConversationPreviewEntry(
            conversation_id=conversation_id,
            title=title,
            create_time=create_time if isinstance(create_time, (int, float)) else None,
            update_time=update_time if isinstance(update_time, (int, float)) else None,
            message_count=0,
            estimated_text_length=0,
            status="skipped",
            import_action_available=False,
            reason="Conversation could not be parsed safely.",
        )
    if message_count == 0 or not text.strip():
        return ConversationPreviewEntry(
            conversation_id=conversation_id,
            title=title,
            create_time=create_time if isinstance(create_time, (int, float)) else None,
            update_time=update_time if isinstance(update_time, (int, float)) else None,
            message_count=message_count,
            estimated_text_length=len(text),
            status="skipped",
            import_action_available=False,
            reason="No user/assistant messages found.",
        )
    reason = "Eligible for memory candidate staging."
    if truncated:
        reason = "Eligible; conversation text will be truncated on apply."
    return ConversationPreviewEntry(
        conversation_id=conversation_id,
        title=title,
        create_time=create_time if isinstance(create_time, (int, float)) else None,
        update_time=update_time if isinstance(update_time, (int, float)) else None,
        message_count=message_count,
        estimated_text_length=len(text),
        status="preview_only",
        import_action_available=True,
        reason=reason,
    )


def _render_preview_markdown(preview: Dict[str, Any]) -> str:
    lines = [
        "# ChatGPT export preview",
        "",
        f"**Session ID:** {preview['session_id']}",
        f"**Export:** `{preview['export_path']}`",
        "",
        "## Safety",
        "",
        "Preview only. No memory candidates were written. No model was called. "
        "No live memory was written.",
        "",
        "## Summary",
        "",
        f"- Conversations: {preview['conversation_count']}",
        f"- Message estimate: {preview['message_count_estimate']}",
        f"- Candidate estimate: {preview['candidate_count_estimate']}",
        f"- Skipped: {preview['skipped_count']}",
        "",
        "## Conversations",
        "",
    ]
    for entry in preview.get("conversations") or []:
        lines.extend(
            [
                f"### {entry['title']}",
                f"- ID: `{entry['conversation_id']}`",
                f"- Messages: {entry['message_count']}",
                f"- Estimated length: {entry['estimated_text_length']} chars",
                f"- Import available: {entry['import_action_available']}",
                f"- Reason: {entry['reason']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def preview_chatgpt_export(
    *,
    export_json: Path,
    dest_dir: Path,
    limit: Optional[int] = None,
    max_conversation_chars: int = DEFAULT_MAX_CONVERSATION_CHARS,
    session_dir: Optional[Path] = None,
) -> ChatGPTExportPreviewReport:
    export_path = _safe_resolve(export_json, label="export JSON")
    dest = _safe_resolve(dest_dir, label="destination directory")
    data = _load_export_json(export_path)
    conversations = _parse_conversations(data)
    if limit is not None:
        conversations = conversations[: max(0, limit)]

    session_id = _new_session_id()
    out_dir = (
        Path(session_dir)
        if session_dir is not None
        else dest / CHATGPT_IMPORT_SESSIONS_SUBDIR / session_id
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    entries: List[ConversationPreviewEntry] = []
    message_total = 0
    for index, conv in enumerate(conversations):
        if not isinstance(conv, dict):
            entries.append(
                ConversationPreviewEntry(
                    conversation_id=f"invalid-{index}",
                    title="Invalid entry",
                    create_time=None,
                    update_time=None,
                    message_count=0,
                    estimated_text_length=0,
                    status="skipped",
                    import_action_available=False,
                    reason="Conversation entry is not an object.",
                )
            )
            continue
        entry = _analyze_conversation(
            conv,
            index,
            export_name=export_path.name,
            max_conversation_chars=max_conversation_chars,
        )
        entries.append(entry)
        message_total += entry.message_count

    eligible = [e for e in entries if e.import_action_available]
    skipped = [e for e in entries if not e.import_action_available]

    try:
        file_size = int(export_path.stat().st_size)
    except OSError:
        file_size = 0

    preview: Dict[str, Any] = {
        "session_id": session_id,
        "created_at": _utc_now_iso(),
        "dest_dir": str(dest),
        "export_path": str(export_path),
        "export_filename": export_path.name,
        "file_size_bytes": file_size,
        "limit": limit,
        "max_conversation_chars": max_conversation_chars,
        "conversation_count": len(entries),
        "message_count_estimate": message_total,
        "candidate_count_estimate": len(eligible),
        "skipped_count": len(skipped),
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "import_applied": False,
        "conversations": [e.to_dict() for e in entries],
    }

    json_path = out_dir / PREVIEW_JSON
    md_path = out_dir / PREVIEW_MD
    json_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_preview_markdown(preview), encoding="utf-8")

    return ChatGPTExportPreviewReport(
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
        raise ChatGPTExportIngestError(f"Preview JSON not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChatGPTExportIngestError(f"Malformed preview JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ChatGPTExportIngestError("Preview JSON must be an object.")
    for key in ("export_path", "file_size_bytes", "dest_dir", "conversations", "session_id"):
        if key not in payload:
            raise ChatGPTExportIngestError(f"Preview JSON missing required field: {key}")
    return payload


def _validate_export_unchanged(export_path: Path, expected_size: int) -> None:
    path = Path(export_path)
    _reject_symlink(path, label="export JSON")
    if not path.is_file():
        raise ChatGPTExportIngestError(f"Export file no longer exists: {path}")
    try:
        current_size = int(path.stat().st_size)
    except OSError as exc:
        raise ChatGPTExportIngestError(f"Export file could not be inspected: {export_path}") from exc
    if current_size != int(expected_size):
        raise ChatGPTExportIngestError(
            f"Export file size changed (preview {expected_size}, current {current_size})."
        )


def _render_apply_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# ChatGPT export apply report",
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
        "## Conversations",
        "",
    ]
    for entry in report.get("conversations") or []:
        lines.extend(
            [
                f"### {entry.get('title', entry.get('conversation_id'))}",
                f"- Action: **{entry['action']}**",
                f"- Reason: {entry['reason']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def apply_chatgpt_export(
    *,
    preview_json: Path,
    apply: bool = False,
    max_conversation_chars: Optional[int] = None,
) -> ChatGPTExportApplyReport:
    preview_path = _safe_resolve(preview_json, label="preview JSON")
    preview = _load_preview_json(preview_path)
    session_dir = preview_path.parent
    session_id = str(preview["session_id"])
    dest_dir = Path(str(preview["dest_dir"]))
    export_path = Path(str(preview["export_path"]))
    _reject_symlink(export_path, label="export JSON")
    export_path = export_path.resolve()
    max_chars = int(
        max_conversation_chars
        if max_conversation_chars is not None
        else preview.get("max_conversation_chars")
        or DEFAULT_MAX_CONVERSATION_CHARS
    )

    _validate_export_unchanged(export_path, int(preview["file_size_bytes"]))
    data = _load_export_json(export_path)
    conversations = _parse_conversations(data)
    limit = preview.get("limit")
    if limit is not None:
        conversations = conversations[: max(0, int(limit))]

    conv_by_id: Dict[str, Dict[str, Any]] = {}
    for index, conv in enumerate(conversations):
        if isinstance(conv, dict):
            conv_by_id[_conversation_id(conv, index)] = conv

    known_ids = read_known_candidate_ids(review_queue_path(dest_dir)) if apply else set()
    results: List[Dict[str, Any]] = []
    staged_count = 0
    duplicate_count = 0
    skipped_count = 0
    imported_at = _utc_now_iso()

    for entry in preview.get("conversations") or []:
        conversation_id = str(entry.get("conversation_id") or "")
        title = str(entry.get("title") or conversation_id)
        if not entry.get("import_action_available"):
            skipped_count += 1
            results.append(
                {
                    "conversation_id": conversation_id,
                    "title": title,
                    "action": "skipped_preview",
                    "reason": str(entry.get("reason") or "Not eligible in preview."),
                }
            )
            continue

        conv = conv_by_id.get(conversation_id)
        if conv is None:
            skipped_count += 1
            results.append(
                {
                    "conversation_id": conversation_id,
                    "title": title,
                    "action": "skipped_missing",
                    "reason": "Conversation not found in export file.",
                }
            )
            continue

        text, truncated, message_count = conversation_to_text(conv, max_chars=max_chars)
        if not text.strip() or message_count == 0:
            skipped_count += 1
            results.append(
                {
                    "conversation_id": conversation_id,
                    "title": title,
                    "action": "skipped_empty",
                    "reason": "No usable conversation text.",
                }
            )
            continue

        source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        original_filename = _candidate_key(export_path.name, conversation_id)
        candidate_id = make_candidate_id(source_sha256, original_filename)
        text_path = session_dir / EXTRACTED_TEXT_SUBDIR / f"{candidate_id}.txt"
        meta_path = session_dir / METADATA_SUBDIR / f"{candidate_id}.json"

        if not apply:
            results.append(
                {
                    "conversation_id": conversation_id,
                    "title": title,
                    "action": "dry_run_would_stage",
                    "reason": "Would stage memory candidate.",
                    "candidate_id": candidate_id,
                    "truncated": truncated,
                }
            )
            continue

        text_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(text + "\n", encoding="utf-8", newline="\n")
        metadata = {
            "conversation_id": conversation_id,
            "title": title,
            "export_path": str(export_path),
            "message_count": message_count,
            "truncated": truncated,
            "imported_at": imported_at,
            "source_sha256": source_sha256,
            "candidate_id": candidate_id,
        }
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        staged_at = _utc_now_iso()
        status, _wrote = stage_memory_candidate(
            dest_dir,
            source_text_path=text_path,
            source_metadata_path=meta_path,
            source_sha256=source_sha256,
            original_filename=original_filename,
            imported_at=imported_at,
            staged_at=staged_at,
            normalized_text=text,
            known_candidate_ids=known_ids,
            source_type=SOURCE_TYPE_CHATGPT_EXPORT,
            suggested_memory_type=SUGGESTED_MEMORY_TYPE_CONVERSATION,
        )
        if status == "staged":
            staged_count += 1
            results.append(
                {
                    "conversation_id": conversation_id,
                    "title": title,
                    "action": "staged",
                    "reason": "Memory candidate staged for review.",
                    "candidate_id": candidate_id,
                    "truncated": truncated,
                }
            )
        else:
            duplicate_count += 1
            results.append(
                {
                    "conversation_id": conversation_id,
                    "title": title,
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
        "export_path": str(export_path),
        "dest_dir": str(dest_dir.resolve()),
        "conversations": results,
    }

    json_path = session_dir / APPLY_REPORT_JSON
    md_path = session_dir / APPLY_REPORT_MD
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_apply_markdown(payload), encoding="utf-8")

    return ChatGPTExportApplyReport(
        session_id=session_id,
        session_dir=str(session_dir),
        json_path=str(json_path),
        markdown_path=str(md_path),
        report=payload,
    )
