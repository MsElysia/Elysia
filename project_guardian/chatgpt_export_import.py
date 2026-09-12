# project_guardian/chatgpt_export_import.py
"""Import OpenAI ChatGPT data exports into Elysia chatlogs (.md) for auto_learning ingest."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

_CONVERSATIONS_JSON_RE = re.compile(r"^conversations-\d+\.json$", re.IGNORECASE)


def _text_from_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        parts = content.get("parts") or []
        chunks: List[str] = []
        for p in parts:
            if isinstance(p, str) and p.strip():
                chunks.append(p.strip())
        return " ".join(chunks).strip()
    return ""


def extract_messages_ordered(conv: Dict[str, Any]) -> List[Tuple[str, str, float]]:
    """
    Return (role, text, create_time) in conversation order.
    Prefer the parent chain from current_node (correct for branched mappings).
    """
    mapping = conv.get("mapping") or {}
    if not isinstance(mapping, dict) or not mapping:
        return []

    current = conv.get("current_node")
    if current and isinstance(current, str) and current in mapping:
        chain: List[str] = []
        node_id: Optional[str] = current
        while node_id:
            chain.append(node_id)
            node = mapping.get(node_id) or {}
            node_id = node.get("parent")
        chain.reverse()
        out: List[Tuple[str, str, float]] = []
        for nid in chain:
            node = mapping.get(nid) or {}
            msg = node.get("message")
            if not isinstance(msg, dict):
                continue
            author = msg.get("author") or {}
            role = str((author.get("role") or "")).lower()
            if role not in ("user", "assistant", "tool"):
                continue
            text = _text_from_message_content(msg.get("content"))
            if not text:
                continue
            try:
                ts = float(msg.get("create_time") or 0.0)
            except (TypeError, ValueError):
                ts = 0.0
            out.append((role, text, ts))
        if out:
            return out

    # Fallback: all nodes sorted by time (legacy / odd exports)
    flat: List[Tuple[str, str, float]] = []
    for _nid, node in mapping.items():
        if not isinstance(node, dict):
            continue
        msg = node.get("message")
        if not isinstance(msg, dict):
            continue
        author = msg.get("author") or {}
        role = str((author.get("role") or "")).lower()
        if role not in ("user", "assistant", "tool"):
            continue
        text = _text_from_message_content(msg.get("content"))
        if not text:
            continue
        try:
            ts = float(msg.get("create_time") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        flat.append((role, text, ts))
    flat.sort(key=lambda x: x[2])
    return flat


def conversation_to_markdown(conv: Dict[str, Any], messages: List[Tuple[str, str, float]]) -> str:
    title = str(conv.get("title") or "ChatGPT conversation").strip() or "ChatGPT conversation"
    cid = str(conv.get("conversation_id") or conv.get("id") or "").strip()
    header_lines = [f"# {title}", ""]
    if cid:
        header_lines.append(f"conversation_id: `{cid}`")
        header_lines.append("")
    body: List[str] = []
    for role, text, _ts in messages:
        if role == "user":
            body.append("## User\n\n" + text + "\n")
        elif role == "assistant":
            body.append("## Assistant\n\n" + text + "\n")
        else:
            body.append("## Tool\n\n" + text + "\n")
    return "\n".join(header_lines + body)


def _conversation_id(conv: Dict[str, Any]) -> str:
    cid = conv.get("conversation_id") or conv.get("id") or ""
    return str(cid).strip()


def iter_conversations_from_json_list(data: Any) -> Iterator[Dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
    elif isinstance(data, dict):
        yield data


def iter_conversations_from_dir(src: Path) -> Iterator[Dict[str, Any]]:
    paths = sorted(src.glob("conversations-*.json"))
    if not paths and (src / "conversations.json").exists():
        paths = [src / "conversations.json"]
    for path in paths:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue
        yield from iter_conversations_from_json_list(data)


def iter_conversations_from_zip(src: Path) -> Iterator[Dict[str, Any]]:
    with zipfile.ZipFile(src, "r") as zf:
        names = sorted(
            n
            for n in zf.namelist()
            if len(Path(n).parts) == 1 and _CONVERSATIONS_JSON_RE.match(Path(n).name)
        )
        if not names:
            for n in zf.namelist():
                if len(Path(n).parts) != 1:
                    continue
                if Path(n).name.lower() == "conversations.json":
                    names = [n]
                    break
        for name in names:
            try:
                data = json.loads(zf.read(name).decode("utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError, UnicodeError):
                continue
            yield from iter_conversations_from_json_list(data)


def iter_conversations_source(src: Path) -> Iterator[Dict[str, Any]]:
    if src.is_file() and src.suffix.lower() == ".zip":
        yield from iter_conversations_from_zip(src)
    elif src.is_dir():
        yield from iter_conversations_from_dir(src)
    else:
        return


@dataclass
class ImportStats:
    written: int = 0
    skipped_existing: int = 0
    skipped_empty: int = 0
    errors: int = 0
    error_messages: List[str] = field(default_factory=list)


def import_conversations_to_chatlogs(
    conversations: Iterable[Dict[str, Any]],
    out_dir: Path,
    *,
    limit: Optional[int] = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> ImportStats:
    """
    Write one ``elysia_chatgpt_<conversation_id>.md`` per conversation.
    Filenames are stable so re-imports skip unless force=True.
    """
    stats = ImportStats()
    out_dir.mkdir(parents=True, exist_ok=True)
    skip_existing = skip_existing and not force
    for conv in conversations:
        if limit is not None and stats.written >= limit:
            break
        cid = _conversation_id(conv)
        if not cid:
            stats.skipped_empty += 1
            continue
        safe = re.sub(r"[^\w\-]", "_", cid)[:80]
        out_path = out_dir / f"elysia_chatgpt_{safe}.md"
        if skip_existing and out_path.exists():
            stats.skipped_existing += 1
            continue
        try:
            messages = extract_messages_ordered(conv)
        except Exception as e:
            stats.errors += 1
            stats.error_messages.append(f"{cid}: {e}")
            continue
        if not messages:
            stats.skipped_empty += 1
            continue
        md = conversation_to_markdown(conv, messages)
        if dry_run:
            stats.written += 1
            continue
        try:
            out_path.write_text(md, encoding="utf-8")
            stats.written += 1
        except OSError as e:
            stats.errors += 1
            stats.error_messages.append(f"{cid}: {e}")
    return stats


def import_chatgpt_export(
    src: Path,
    out_dir: Path,
    *,
    limit: Optional[int] = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> ImportStats:
    if not src.exists():
        raise FileNotFoundError(str(src))
    return import_conversations_to_chatlogs(
        iter_conversations_source(src),
        out_dir,
        limit=limit,
        dry_run=dry_run,
        skip_existing=skip_existing,
        force=force,
    )
