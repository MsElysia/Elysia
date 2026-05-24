# project_guardian/governance/live_execution_audit.py
"""Append-only audit for live-execution guard decisions (redacted; no prompts/traces)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_PATH = _REPO_ROOT / "data" / "runtime" / "live_execution_guard_audit.jsonl"

_SENSITIVE_KEYS = frozenset(
    {
        "message",
        "text",
        "prompt",
        "content",
        "observation",
        "raw_input",
        "trace",
        "think_decide_act_trace",
        "evidence",
    }
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_audit_value(key: str, value: Any, *, depth: int = 0) -> Any:
    """Redact sensitive fields; bound size. No raw prompts or full traces."""
    if depth > 4:
        return "[truncated]"
    k = str(key or "").lower()
    if k in _SENSITIVE_KEYS:
        if value is None:
            return None
        if isinstance(value, str):
            return f"[redacted:{len(value)}chars]"
        return "[redacted]"
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, Mapping):
        return {
            str(sk): sanitize_audit_value(str(sk), sv, depth=depth + 1)
            for sk, sv in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_audit_value(k, item, depth=depth + 1) for item in list(value)[:20]]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:300]


def sanitize_audit_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"recorded_at": _iso_now()}
    for key, val in record.items():
        if key == "recorded_at":
            continue
        out[str(key)] = sanitize_audit_value(str(key), val)
    return out


def append_live_execution_guard_audit(
    record: Mapping[str, Any],
    *,
    audit_path: Optional[Path] = None,
) -> bool:
    """
    Append one JSONL audit row. Returns True on success.

    On failure, logs and returns False (caller should fail closed).
    """
    path = audit_path or DEFAULT_AUDIT_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        row = sanitize_audit_record(record)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, default=str) + "\n")
        return True
    except Exception as exc:
        logger.warning("live_execution_guard audit append failed: %s", exc)
        return False
