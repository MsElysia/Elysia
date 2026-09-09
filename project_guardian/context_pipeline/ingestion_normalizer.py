# project_guardian/context_pipeline/ingestion_normalizer.py
"""Normalize heterogeneous inputs into IngestedRecordDict rows."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import IngestedRecordDict, SourceType

logger = logging.getLogger(__name__)


def _rid(prefix: str, text: str) -> str:
    h = hashlib.sha256(f"{prefix}|{text[:4000]}".encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{prefix}_{h}"


def make_record(
    *,
    source_type: SourceType,
    raw_text: str,
    session_id: str,
    trust_score: float = 0.72,
    initial_importance: float = 0.5,
    tags: Optional[List[str]] = None,
    timestamp: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    record_id: Optional[str] = None,
) -> IngestedRecordDict:
    ts = float(timestamp if timestamp is not None else time.time())
    text = (raw_text or "").strip()
    rid = record_id or _rid(str(source_type), f"{session_id}|{ts}|{text}")
    return {
        "id": rid,
        "source_type": str(source_type),
        "timestamp": ts,
        "raw_text": text[:24000],
        "tags": list(tags or []),
        "session_id": str(session_id),
        "trust_score": float(max(0.0, min(1.0, trust_score))),
        "initial_importance": float(max(0.0, min(1.0, initial_importance))),
        "metadata": dict(metadata or {}),
    }


def normalize_user_input(text: str, session_id: str) -> List[IngestedRecordDict]:
    if not (text or "").strip():
        return []
    rec = make_record(
        source_type="user_input",
        raw_text=text,
        session_id=session_id,
        trust_score=0.95,
        initial_importance=0.85,
        tags=["user"],
    )
    logger.info("[Ingest] source=user_input chars=%s id=%s", len(rec["raw_text"]), rec["id"][:24])
    return [rec]


def normalize_memory_entries(entries: List[Dict[str, Any]], session_id: str) -> List[IngestedRecordDict]:
    out: List[IngestedRecordDict] = []
    for i, e in enumerate(entries or []):
        if not isinstance(e, dict):
            continue
        body = str(e.get("content") or e.get("text") or e.get("memory") or "")[:12000]
        if not body.strip():
            continue
        cat = str(e.get("category") or e.get("type") or "memory")
        pr = e.get("priority")
        imp = float(pr) if isinstance(pr, (int, float)) else 0.55
        out.append(
            make_record(
                source_type="memory",
                raw_text=body,
                session_id=session_id,
                trust_score=0.78,
                initial_importance=imp,
                tags=["memory", cat[:40]],
                metadata={"category": cat, "index": i},
                record_id=str(e.get("id") or "") or None,
            )
        )
    if out:
        logger.info("[Ingest] source=memory rows=%s", len(out))
    return out


def normalize_chat_history_lines(lines: List[str], session_id: str, *, max_lines: int = 80) -> List[IngestedRecordDict]:
    out: List[IngestedRecordDict] = []
    for ln in (lines or [])[-max_lines:]:
        s = str(ln).strip()
        if len(s) < 8:
            continue
        out.append(
            make_record(
                source_type="chat_history",
                raw_text=s[:8000],
                session_id=session_id,
                trust_score=0.7,
                initial_importance=0.48,
                tags=["chat_export"],
            )
        )
    if out:
        logger.info("[Ingest] source=chat_history rows=%s", len(out))
    return out


def normalize_log_tail(text: str, session_id: str, *, max_chars: int = 12000) -> List[IngestedRecordDict]:
    blob = (text or "").strip()[-max_chars:]
    if not blob:
        return []
    rec = make_record(
        source_type="log",
        raw_text=blob,
        session_id=session_id,
        trust_score=0.62,
        initial_importance=0.42,
        tags=["log"],
        metadata={"kind": "tail"},
    )
    logger.info("[Ingest] source=log chars=%s", len(blob))
    return [rec]


def json_dumps_safe(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def normalize_browser_findings(items: List[Any], session_id: str) -> List[IngestedRecordDict]:
    out: List[IngestedRecordDict] = []
    for i, it in enumerate(items or []):
        if isinstance(it, dict):
            txt = str(it.get("text") or it.get("finding") or it.get("summary") or json_dumps_safe(it)[:4000])
            url = str(it.get("url") or "")
        else:
            txt = str(it)[:4000]
            url = ""
        if not txt.strip():
            continue
        out.append(
            make_record(
                source_type="browser_finding",
                raw_text=txt,
                session_id=session_id,
                trust_score=0.68,
                initial_importance=0.52,
                tags=["browser", url[:80]],
                metadata={"url": url, "index": i},
            )
        )
    if out:
        logger.info("[Ingest] source=browser_finding rows=%s", len(out))
    return out


def normalize_task_snapshot(blob: Dict[str, Any], session_id: str, label: str = "task_snapshot") -> List[IngestedRecordDict]:
    if not isinstance(blob, dict) or not blob:
        return []
    st: SourceType = "task_snapshot" if label == "task_snapshot" else "monitor_snapshot"
    if "planner" in label.lower():
        st = "planner_snapshot"
    txt = json_dumps_safe(blob)[:10000]
    rec = make_record(
        source_type=st,
        raw_text=txt,
        session_id=session_id,
        trust_score=0.74,
        initial_importance=0.58,
        tags=[label],
    )
    logger.info("[Ingest] source=%s keys=%s", st, len(blob))
    return [rec]


def load_text_file_tail(path: Path, max_bytes: int = 24000) -> str:
    if not path.is_file():
        return ""
    try:
        raw = path.read_bytes()[-max_bytes:]
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def read_chat_export_paths(paths: List[str], max_lines_per_file: int = 120) -> List[str]:
    lines: List[str] = []
    for p in paths:
        fp = Path(p)
        if not fp.is_file():
            continue
        try:
            for i, ln in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines()):
                if i >= max_lines_per_file:
                    break
                lines.append(ln)
        except Exception:
            continue
    return lines
