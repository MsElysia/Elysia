"""
Durable operator chat storage (JSONL per conversation).

Used by the control panel and optionally by elysia.api.RuntimeAPIServer.
Does not call LLMs. Redacts common secret patterns before persistence.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "CHAT_LIST_MESSAGES_DEFAULT",
    "CHAT_MAX_MESSAGES_PER_CONVERSATION",
    "CHAT_TEXT_LIMIT",
    "DEFAULT_CONVERSATIONS_DIR",
    "LEGACY_IMPORT_MARKER",
    "ConversationMessage",
    "ConversationStore",
    "build_recent_transcript",
    "conversation_message_from_row",
    "format_transcript_for_prompt",
    "get_default_conversation_store",
    "redact_chat_text",
    "reset_default_conversation_store_for_tests",
    "sanitize_conversation_id",
]

DEFAULT_CONVERSATIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "runtime" / "conversations"
LEGACY_IMPORT_MARKER = ".legacy_control_panel_chat_history_imported"
LEGACY_IMPORT_MAX_MESSAGES = 60

CHAT_TEXT_LIMIT = 2000
CHAT_MAX_MESSAGES_PER_CONVERSATION = 60
CHAT_LIST_MESSAGES_DEFAULT = 20

_CHAT_KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|credential)\s*[:=]\s*([^\s,;]+)"
)
_CHAT_BEARER_SECRET_RE = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+([^\s,;]+)")
_CHAT_SK_SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")


def redact_chat_text(text: Any, *, limit: int = CHAT_TEXT_LIMIT) -> str:
    """Redact obvious credentials before persisting or returning chat text."""
    out = str(text or "")
    out = _CHAT_KEY_VALUE_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", out)
    out = _CHAT_BEARER_SECRET_RE.sub("Authorization: Bearer [REDACTED]", out)
    out = _CHAT_SK_SECRET_RE.sub("sk-[REDACTED]", out)
    return out[:limit]


def sanitize_conversation_id(value: Any) -> str:
    raw = str(value or "control_panel").strip() or "control_panel"
    clean = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw)[:80].strip("._:-")
    return clean or "control_panel"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def legacy_import_marker_path(base_dir: Path) -> Path:
    return Path(base_dir) / LEGACY_IMPORT_MARKER


def is_legacy_control_panel_imported(base_dir: Path) -> bool:
    return legacy_import_marker_path(base_dir).exists()


def count_canonical_conversation_files(base_dir: Path) -> int:
    root = Path(base_dir)
    if not root.is_dir():
        return 0
    return sum(1 for p in root.glob("*.jsonl") if p.is_file())


def describe_legacy_control_panel_chat(legacy_path: Path) -> Dict[str, Any]:
    """Read-only summary of legacy control-panel chat JSON (no mutation)."""
    p = Path(legacy_path)
    out: Dict[str, Any] = {
        "legacy_path": str(p),
        "legacy_exists": p.exists(),
        "session_count": 0,
        "message_count": 0,
    }
    if not p.exists():
        return out
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        out["read_error"] = str(exc)[:200]
        return out
    sessions = raw.get("sessions") if isinstance(raw, dict) else None
    if not isinstance(sessions, dict):
        return out
    out["session_count"] = len(sessions)
    for rows in sessions.values():
        if isinstance(rows, list):
            out["message_count"] += sum(1 for r in rows if isinstance(r, dict))
    return out


def _safe_metadata(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Drop nested structures and known heavy keys (no raw traces)."""
    if not isinstance(meta, dict):
        return {}
    block = frozenset(
        {
            "think_decide_act_trace",
            "raw_trace",
            "trace",
            "transitions",
            "execution",
            "run_context",
            "brain_trace_path",
        }
    )
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if k in block:
            continue
        if isinstance(v, (dict, list)):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)[:64]] = v
    return out


def format_transcript_for_prompt(
    messages: Iterable[Dict[str, Any]],
    *,
    max_messages: int = 20,
    max_chars: int = 8000,
) -> str:
    """Build a single prompt prefix from recent sanitized messages."""
    rows = list(messages)
    if not rows:
        return ""
    lines = [
        "Recent operator conversation (redacted, bounded). Use only when relevant.",
        "Do not invent facts; do not repeat secrets if any slipped through.",
    ]
    used = 0
    for row in rows[-max_messages:]:
        role = str(row.get("role") or "").strip().lower()
        label = "User" if role == "user" else "Assistant"
        chunk = f"{label}: {row.get('content', '')}"
        if used + len(chunk) > max_chars:
            break
        lines.append(chunk)
        used += len(chunk) + 1
    return "\n".join(lines)


def build_recent_transcript(
    messages: Iterable[Dict[str, Any]],
    *,
    max_messages: int = 20,
    max_chars: int = 8000,
) -> str:
    """Alias for :func:`format_transcript_for_prompt` (canonical name for prompt assembly)."""
    return format_transcript_for_prompt(
        messages, max_messages=max_messages, max_chars=max_chars
    )


@dataclass(frozen=True)
class ConversationMessage:
    """One persisted chat row (sanitized content)."""

    message_id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    metadata: Dict[str, Any]


def conversation_message_from_row(row: Dict[str, Any]) -> ConversationMessage:
    """Build :class:`ConversationMessage` from API-shaped dict (e.g. ``list_messages`` row)."""
    return ConversationMessage(
        message_id=str(row.get("message_id") or ""),
        conversation_id=str(row.get("conversation_id") or ""),
        role=str(row.get("role") or ""),
        content=str(row.get("content") or ""),
        created_at=str(row.get("created_at") or ""),
        metadata=dict(row.get("metadata") or {})
        if isinstance(row.get("metadata"), dict)
        else {},
    )


@dataclass
class ConversationStore:
    """Append-only JSONL per conversation under base_dir."""

    base_dir: Path

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, conversation_id: str) -> Path:
        cid = sanitize_conversation_id(conversation_id)
        return self.base_dir / f"{cid}.jsonl"

    def import_legacy_control_panel_json(self, legacy_path: Path) -> int:
        """One-time import from control_panel_chat_history.json into JSONL files.

        Does not modify or delete the legacy JSON file. Writes an import marker under
        ``base_dir`` so subsequent calls are no-ops without re-reading legacy data.
        """
        marker = legacy_import_marker_path(self.base_dir)
        if marker.exists():
            return 0
        legacy = Path(legacy_path)
        try:
            raw = json.loads(legacy.read_text(encoding="utf-8"))
        except FileNotFoundError:
            marker.write_text(_utc_iso(), encoding="utf-8")
            return 0
        except Exception as exc:
            logger.warning("legacy chat import skipped (read error): %s", exc)
            return 0

        sessions = raw.get("sessions") if isinstance(raw, dict) else None
        if not isinstance(sessions, dict):
            marker.write_text(_utc_iso(), encoding="utf-8")
            return 0

        imported = 0
        for sid, rows in sessions.items():
            if not isinstance(rows, list):
                continue
            cid = sanitize_conversation_id(sid)
            path = self._path(cid)
            if path.exists() and path.stat().st_size > 0:
                continue
            valid_rows: List[Dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                role = str(row.get("role") or "").strip().lower()
                if role not in {"user", "assistant", "system", "tool", "metadata"}:
                    continue
                valid_rows.append(row)
            if len(valid_rows) > LEGACY_IMPORT_MAX_MESSAGES:
                valid_rows = valid_rows[-LEGACY_IMPORT_MAX_MESSAGES:]
            for row in valid_rows:
                role = str(row.get("role") or "").strip().lower()
                ts = row.get("created_at") or row.get("timestamp")
                created_at = str(ts).strip()[:64] if ts else None
                self.append_message(
                    cid,
                    role=role,
                    content=str(row.get("content") or ""),
                    metadata={"source": "legacy_import"},
                    created_at=created_at,
                )
                imported += 1
        marker.write_text(_utc_iso(), encoding="utf-8")
        return imported

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        cid = sanitize_conversation_id(conversation_id)
        r = str(role or "").strip().lower()
        if r not in {"user", "assistant", "system", "tool", "metadata"}:
            r = "metadata"
        ts = str(created_at).strip()[:64] if created_at else _utc_iso()
        msg = {
            "message_id": uuid.uuid4().hex,
            "conversation_id": cid,
            "role": r,
            "content": redact_chat_text(content),
            "created_at": ts,
            "metadata": _safe_metadata(metadata),
        }
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        with self._lock:
            path = self._path(cid)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            self._trim_file(path)
        return msg

    def _trim_file(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        if len(lines) <= CHAT_MAX_MESSAGES_PER_CONVERSATION:
            return
        keep = lines[-CHAT_MAX_MESSAGES_PER_CONVERSATION:]
        try:
            path.write_text("\n".join(keep) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("conversation trim failed %s: %s", path, exc)

    def list_messages(
        self,
        conversation_id: str,
        *,
        limit: int = CHAT_LIST_MESSAGES_DEFAULT,
    ) -> List[Dict[str, Any]]:
        cid = sanitize_conversation_id(conversation_id)
        path = self._path(cid)
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            logger.warning("conversation read failed %s: %s", path, exc)
            return []
        out: List[Dict[str, Any]] = []
        for line in lines[-max(1, min(limit, 200)) :]:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            out.append(self.sanitize_message_for_api(obj))
        return out

    def get_messages(
        self,
        conversation_id: str,
        *,
        limit: int = CHAT_LIST_MESSAGES_DEFAULT,
    ) -> List[Dict[str, Any]]:
        """Alias for :meth:`list_messages` (canonical read API)."""
        return self.list_messages(conversation_id, limit=limit)

    def get_recent_context(
        self,
        conversation_id: str,
        *,
        limit: int = CHAT_LIST_MESSAGES_DEFAULT,
    ) -> List[Dict[str, Any]]:
        """Recent messages for LLM context assembly (same as :meth:`get_messages`)."""
        return self.get_messages(conversation_id, limit=limit)

    def sanitize_message_for_api(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "message_id": str(row.get("message_id") or ""),
            "conversation_id": str(row.get("conversation_id") or ""),
            "role": str(row.get("role") or ""),
            "content": redact_chat_text(row.get("content", "")),
            "created_at": str(row.get("created_at") or ""),
            "metadata": _safe_metadata(row.get("metadata") if isinstance(row.get("metadata"), dict) else {}),
        }

    def list_conversations(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        with self._lock:
            for path in sorted(self.base_dir.glob("*.jsonl")):
                cid = path.stem
                try:
                    st = path.stat()
                except OSError:
                    continue
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except Exception:
                    lines = []
                items.append(
                    {
                        "conversation_id": cid,
                        "updated_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "message_count": len([ln for ln in lines if ln.strip()]),
                    }
                )
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return items

    def delete_conversation(self, conversation_id: str) -> bool:
        cid = sanitize_conversation_id(conversation_id)
        path = self._path(cid)
        with self._lock:
            try:
                if path.exists():
                    path.unlink()
                    return True
            except OSError as exc:
                logger.warning("delete conversation failed %s: %s", path, exc)
        return False

    def new_conversation_id(self) -> str:
        return f"conv_{uuid.uuid4().hex[:24]}"


_default_store: Optional[ConversationStore] = None
_default_lock = threading.Lock()


def reset_default_conversation_store_for_tests() -> None:
    global _default_store
    with _default_lock:
        _default_store = None


def get_default_conversation_store(base_dir: Optional[Path] = None) -> ConversationStore:
    global _default_store
    with _default_lock:
        if _default_store is None:
            _default_store = ConversationStore(base_dir or DEFAULT_CONVERSATIONS_DIR)
        return _default_store
