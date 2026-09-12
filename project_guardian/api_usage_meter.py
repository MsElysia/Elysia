# project_guardian/api_usage_meter.py
"""In-process counters for LLM/API transport and routing — operator \"gas meter\" (no external deps)."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
_started_monotonic = time.monotonic()
_started_wall = time.time()

# channel -> stats
_transport: Dict[str, Dict[str, Any]] = {}
_router_counts: Dict[str, int] = {}


def _ensure_channel(ch: str) -> Dict[str, Any]:
    if ch not in _transport:
        _transport[ch] = {
            "calls_ok": 0,
            "calls_fail": 0,
            "last_ok_ts": None,
            "last_fail_ts": None,
            "last_detail": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    return _transport[ch]


def record_transport(
    channel: str,
    ok: bool,
    *,
    detail: Optional[str] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record one outbound provider call (chat completion, structured OpenAI, Ollama generation).

    ``usage`` may include prompt_tokens, completion_tokens, total_tokens (OpenAI-style).
    """
    ch = str(channel or "unknown").strip() or "unknown"
    now = time.time()
    pt = ct = tt = 0
    if isinstance(usage, dict):
        try:
            pt = int(usage.get("prompt_tokens") or 0)
        except (TypeError, ValueError):
            pt = 0
        try:
            ct = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            ct = 0
        try:
            tt = int(usage.get("total_tokens") or 0)
        except (TypeError, ValueError):
            tt = 0
        if tt <= 0 and (pt > 0 or ct > 0):
            tt = pt + ct

    with _lock:
        row = _ensure_channel(ch)
        if ok:
            row["calls_ok"] = int(row["calls_ok"]) + 1
            row["last_ok_ts"] = now
        else:
            row["calls_fail"] = int(row["calls_fail"]) + 1
            row["last_fail_ts"] = now
            if detail:
                row["last_detail"] = str(detail)[:400]
        if tt > 0 or pt > 0 or ct > 0:
            row["prompt_tokens"] = int(row["prompt_tokens"]) + pt
            row["completion_tokens"] = int(row["completion_tokens"]) + ct
            row["total_tokens"] = int(row["total_tokens"]) + (tt if tt > 0 else pt + ct)

    try:
        from .unified_api_budget import charge_successful_call

        charge_successful_call(ch, ok, usage)
    except Exception:
        pass


def record_router_choice(chosen: str, *, task_type: str = "") -> None:
    """Count API-router decisions (select_best_api), not heuristic probes."""
    key = str(chosen or "unknown").strip() or "unknown"
    with _lock:
        _router_counts[key] = int(_router_counts.get(key, 0)) + 1


def reset_session() -> None:
    """Clear all counters (tests / explicit operator reset)."""
    global _started_monotonic, _started_wall
    with _lock:
        _transport.clear()
        _router_counts.clear()
        _started_monotonic = time.monotonic()
        _started_wall = time.time()


def snapshot_transport_rows() -> List[Dict[str, Any]]:
    """Sorted rows for UI / JSON."""
    with _lock:
        rows: List[Dict[str, Any]] = []
        for name in sorted(_transport.keys()):
            r = dict(_transport[name])
            r["channel"] = name
            rows.append(r)
        return rows


def snapshot_router_counts() -> Dict[str, int]:
    with _lock:
        return dict(sorted(_router_counts.items(), key=lambda kv: (-kv[1], kv[0])))


def session_uptime_sec() -> float:
    return max(0.0, time.monotonic() - _started_monotonic)


def snapshot() -> Dict[str, Any]:
    """Full meter payload for Insights / scripts."""
    with _lock:
        upt = max(0.0, time.monotonic() - _started_monotonic)
        transport = {k: dict(v) for k, v in _transport.items()}
        router = dict(sorted(_router_counts.items(), key=lambda kv: (-kv[1], kv[0])))
    tot_ok = sum(int(v.get("calls_ok") or 0) for v in transport.values())
    tot_fail = sum(int(v.get("calls_fail") or 0) for v in transport.values())
    tok = sum(int(v.get("total_tokens") or 0) for v in transport.values())
    return {
        "session_started_wall_epoch": _started_wall,
        "uptime_sec": round(upt, 2),
        "transport": transport,
        "transport_totals": {"calls_ok": tot_ok, "calls_fail": tot_fail, "total_tokens_reported": tok},
        "router_choices": router,
    }


def format_gas_meter_text(snapshot_payload: Dict[str, Any], *, max_lines: int = 24) -> str:
    """Human-readable block for Control Panel."""
    lines: List[str] = []
    upt = snapshot_payload.get("uptime_sec")
    lines.append(f"uptime_sec≈{upt}")
    tt = snapshot_payload.get("transport_totals") or {}
    lines.append(
        f"calls OK={tt.get('calls_ok', 0)} FAIL={tt.get('calls_fail', 0)} "
        f"tokens_reported≈{tt.get('total_tokens_reported', 0)}"
    )
    tr = snapshot_payload.get("transport") or {}
    for name in sorted(tr.keys())[: max_lines - 4]:
        r = tr[name]
        lines.append(
            f"{name}: ok={r.get('calls_ok', 0)} fail={r.get('calls_fail', 0)} "
            f"tok≈{r.get('total_tokens', 0)}"
        )
    rc = snapshot_payload.get("router_choices") or {}
    if rc:
        bits = [f"{k}={v}" for k, v in list(rc.items())[:12]]
        lines.append("router: " + " ".join(bits))
    return "\n".join(lines[:max_lines])
