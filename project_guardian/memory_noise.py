# project_guardian/memory_noise.py
"""Heuristics to skip low-value text before embeddings / optional memory writes."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_NOISE_PATTERNS = (
    r"\bheartbeat\b",
    r"\bheart\s*beat\b",
    r"\bpulse\b",
    r"\bstatus\s*poll\b",
    r"\bpolling\b",
    r"\bkeepalive\b",
    r"\binit(ializ)?ed\b.*\bsystem\b",
    r"^\s*ok\s*\.?\s*$",
    r"^\s*ping\s*\.?\s*$",
    r"^\s*pong\s*\.?\s*$",
    r"\[Autonomy\]\s*income_modules_pulse:\s*no income module data",
)
_COMPILED = [re.compile(p, re.I | re.DOTALL) for p in _NOISE_PATTERNS]


def is_low_value_memory_text(text: Optional[str], *, min_chars_for_substantive: int = 24) -> bool:
    if text is None:
        return True
    s = str(text).strip()
    if len(s) < 4:
        return True
    if len(s) < min_chars_for_substantive and s.lower() in (
        "ok",
        "ping",
        "pong",
        "ready",
        "alive",
        "noop",
        "none",
        "null",
        "initialized",
    ):
        return True
    low = s.lower()
    if "heartbeat" in low or "pulse cycle" in low or "telemetry pulse" in low:
        return True
    for rx in _COMPILED:
        if rx.search(s):
            return True
    return False


def is_trivial_embedding_fragment(text: Optional[str]) -> bool:
    """
    True for tiny / log-token strings that should not trigger sentence-transformers load
    or noisy hash-fallback warnings (autonomy breadcrumbs, split metadata lines).
    """
    if text is None:
        return True
    s = str(text).strip()
    if len(s) < 16:
        return True
    low = s.lower()
    if is_low_value_memory_text(s, min_chars_for_substantive=28):
        return True
    if low in (
        "[autonomy]",
        "artifact:",
        "low_yield=false",
        "low_yield=true",
        "memory_core:",
        "trust decay]",
        "consensus]",
    ):
        return True
    if re.fullmatch(r"count=\d+", low):
        return True
    if re.fullmatch(r"low_yield=(true|false)", low):
        return True
    if re.match(r"^\[autonomy\]\s*$", s, re.I):
        return True
    # Short lines that are mostly log labels / module tags
    if len(s) < 56 and any(
        t in low
        for t in (
            "harvest_income_report:",
            "fractalmind_planning",
            "artifact-ready=",
            "income_modules_pulse:",
            "execute_self_task",
            "execute_task",
            "text_sample=",
            "safety_validation",
            "no-op",
            "noop_suppressed",
            "suppression",
        )
    ):
        return True
    return False


# Substrings that indicate the line should still be embedded / not hard-skipped as noise.
_MEANINGFUL_MEMORY_MARKERS = (
    "failed",
    "failure",
    "error:",
    " error ",
    "exception",
    "critical",
    "traceback",
    "[startup]",
    "unsafe",
    "blocked",
    "approved",
    "mutation",
    "governance",
    "user ",
    "conversation",
)


def thought_indicates_important_memory(text: Optional[str]) -> bool:
    """True → do not hard-skip vectorization or aggressive routine-memory throttles."""
    if not text or not str(text).strip():
        return False
    low = str(text).lower()
    if re.search(r"\berror\b", low) or re.search(r"\bfail(?:ed|ure)?\b", low):
        return True
    if re.search(r"\bexception\b", low) or re.search(r"\bcritical\b", low):
        return True
    return any(m in low for m in _MEANINGFUL_MEMORY_MARKERS)


def is_embedding_entirely_skipped(text: Optional[str]) -> bool:
    """
    True → skip all embedding paths (no OpenAI, no sentence-transformers, no hash fallback).
    Used for log-token / bookkeeping lines that should not touch the vector store at all.
    """
    if text is None:
        return True
    s = str(text).strip()
    if not s:
        return True
    if thought_indicates_important_memory(s):
        return False
    if is_trivial_embedding_fragment(s):
        return True
    low = s.lower()
    if "safety_validation" in low:
        return True
    if re.search(r"\bobjective=[0-9a-f-]{8,}\b", low):
        return True
    if "work_on_objective" in low and len(s) < 220:
        return True
    if re.match(r"^\[autonomy\]", s, re.I) and len(s) < 180:
        return True
    return False


def host_system_memory_fraction() -> Optional[float]:
    """Host RAM usage 0.0–1.0, or None if unavailable."""
    try:
        import psutil

        return float(psutil.virtual_memory().percent) / 100.0
    except Exception:
        return None


_ROUTINE_THROTTLE_LOCK = threading.Lock()
_ROUTINE_THROTTLE_LAST: dict[str, float] = {}
_ROUTINE_THROTTLE_MAX_KEYS = 400


def _routine_throttle_ttl_sec() -> float:
    try:
        return max(30.0, float(os.environ.get("ELYSIA_ROUTINE_REMEMBER_THROTTLE_SEC", "120")))
    except ValueError:
        return 120.0


def _routine_pressure_threshold() -> float:
    try:
        return max(0.5, min(0.99, float(os.environ.get("ELYSIA_HOST_RAM_ROUTINE_THROTTLE_FRAC", "0.78"))))
    except ValueError:
        return 0.78


def _routine_throttle_fingerprint(category: str, thought: str) -> str:
    h = hashlib.sha256(f"{category or ''}\n{thought or ''}".encode("utf-8", errors="replace"))
    return h.hexdigest()[:20]


def routine_autonomy_remember_suppressed(
    category: str,
    priority: float,
    thought: Optional[str],
) -> bool:
    """
    Under high host RAM, suppress duplicate JSON writes for repetitive autonomy bookkeeping
    (no-op / suppression / artifact-ready style lines). First write in a window is kept.
    """
    frac = host_system_memory_fraction()
    if frac is None or frac < _routine_pressure_threshold():
        return False
    cat = (category or "").lower().strip()
    if cat not in ("autonomy", "exploration", "monitoring", "introspection"):
        return False
    pr = float(priority or 0)
    if pr >= 0.74:
        return False
    th = thought or ""
    if thought_indicates_important_memory(th):
        return False
    tl = th.lower()
    repetitive = False
    if tl.startswith("[autonomy]") and len(th) < 200:
        repetitive = True
    markers = (
        "no_op",
        "no-op",
        "noop",
        "suppressed",
        "skipped",
        "artifact-ready",
        "low_yield",
        "harvest_income",
        "income_modules_pulse",
        "artifact:",
        "count=",
        "cooldown",
        "same artifact",
        "low-value repetition",
        "work_on_objective:",
        "safety_validation",
    )
    if any(m in tl for m in markers):
        repetitive = True
    if not repetitive:
        return False
    key = _routine_throttle_fingerprint(cat, th)
    now = time.time()
    ttl = _routine_throttle_ttl_sec()
    with _ROUTINE_THROTTLE_LOCK:
        last = _ROUTINE_THROTTLE_LAST.get(key)
        if last is not None and (now - last) < ttl:
            logger.debug(
                "Memory remember suppressed (host RAM pressure + duplicate routine line, ttl=%ss)",
                int(ttl),
            )
            return True
        _ROUTINE_THROTTLE_LAST[key] = now
        if len(_ROUTINE_THROTTLE_LAST) > _ROUTINE_THROTTLE_MAX_KEYS:
            cutoff = now - ttl
            dead = [k for k, t in _ROUTINE_THROTTLE_LAST.items() if t < cutoff]
            for k in dead[: _ROUTINE_THROTTLE_MAX_KEYS // 2]:
                _ROUTINE_THROTTLE_LAST.pop(k, None)
    return False
