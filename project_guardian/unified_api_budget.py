# project_guardian/unified_api_budget.py
"""
Single rolling-period budget for external API usage (token-equivalent units).

All meter channels (LLM transports, Tavily, Brave, etc.) contribute toward one cap that
resets every ``elysia_unified_budget_period_seconds`` (wall clock). Counts successful calls;
when reported usage tokens exist they count toward the budget; otherwise flat per-channel
estimates apply.

When a large fraction of the period budget is still **unused** (\"surplus\"), preflight
estimates for expensive cloud chat are **softened** so secondary / follow-on calls are not
blocked unnecessarily; post-success charging still uses real usage or flats.

Env overrides:
  ELYSIA_UNIFIED_BUDGET_ENABLED=1|0
  ELYSIA_UNIFIED_BUDGET_MAX_UNITS=<float>
  ELYSIA_UNIFIED_BUDGET_PERIOD_SEC=<float>
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_period_start_wall: float = time.time()
_consumed_units: float = 0.0
_cfg_cache: Optional[Dict[str, Any]] = None
_decider_mtime_ns: Optional[int] = None

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DECIDER_PATH = _PROJECT_ROOT / "config" / "mistral_decider.json"

_DEFAULT_FLAT_UNITS: Dict[str, float] = {
    "openai_chat": 2500.0,
    "openrouter_chat": 2500.0,
    "openai_structured": 4000.0,
    "ollama_chat": 0.0,
    "ollama_prompt_packet": 0.0,
    "tavily_search": 1200.0,
    "brave_search": 800.0,
    "huggingface_inference": 1500.0,
    "default": 500.0,
}


def _load_decider_cfg() -> Dict[str, Any]:
    global _cfg_cache, _decider_mtime_ns
    try:
        if not _DECIDER_PATH.is_file():
            return {}
        st = _DECIDER_PATH.stat()
        if _cfg_cache is not None and _decider_mtime_ns == st.st_mtime_ns:
            return dict(_cfg_cache)
        raw = json.loads(_DECIDER_PATH.read_text(encoding="utf-8"))
        _cfg_cache = raw if isinstance(raw, dict) else {}
        _decider_mtime_ns = st.st_mtime_ns
        return dict(_cfg_cache)
    except Exception as e:
        logger.debug("unified_api_budget decider read: %s", e)
        return {}


def enabled() -> bool:
    raw = (os.environ.get("ELYSIA_UNIFIED_BUDGET_ENABLED") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    cfg = _load_decider_cfg()
    return bool(cfg.get("elysia_unified_budget_enabled", False))


def max_units_per_period() -> float:
    raw = (os.environ.get("ELYSIA_UNIFIED_BUDGET_MAX_UNITS") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    cfg = _load_decider_cfg()
    try:
        v = float(cfg.get("elysia_unified_budget_max_units_per_period", 0) or 0)
        return max(0.0, v)
    except (TypeError, ValueError):
        return 0.0


def period_seconds() -> float:
    raw = (os.environ.get("ELYSIA_UNIFIED_BUDGET_PERIOD_SEC") or "").strip()
    if raw:
        try:
            return max(60.0, float(raw))
        except ValueError:
            pass
    cfg = _load_decider_cfg()
    try:
        sec = float(cfg.get("elysia_unified_budget_period_seconds", 86400) or 86400)
        return max(60.0, sec)
    except (TypeError, ValueError):
        return 86400.0


def flat_units_for_channel(channel: str) -> float:
    cfg = _load_decider_cfg()
    overrides = cfg.get("elysia_unified_budget_flat_units")
    ch = str(channel or "default").strip() or "default"
    if isinstance(overrides, dict) and ch in overrides:
        try:
            return max(0.0, float(overrides[ch]))
        except (TypeError, ValueError):
            pass
    return float(_DEFAULT_FLAT_UNITS.get(ch, _DEFAULT_FLAT_UNITS["default"]))


def _units_from_usage_or_flat(channel: str, usage: Optional[Dict[str, Any]]) -> float:
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
    if tt > 0:
        return float(tt)
    return flat_units_for_channel(channel)


def _maybe_reset_period() -> None:
    global _period_start_wall, _consumed_units
    now = time.time()
    window = period_seconds()
    cap = max_units_per_period()
    if cap <= 0 and not enabled():
        return
    if now - _period_start_wall >= window:
        _period_start_wall = now
        _consumed_units = 0.0
        logger.info(
            "[UnifiedBudget] period reset window_sec=%.0f max_units=%.0f",
            window,
            cap,
        )


def remaining_units() -> float:
    """Units left before cap this period (inf if disabled or no cap)."""
    if not enabled():
        return float("inf")
    cap = max_units_per_period()
    if cap <= 0:
        return float("inf")
    with _lock:
        _maybe_reset_period()
        return max(0.0, cap - _consumed_units)


def surplus_opportunistic_enabled() -> bool:
    cfg = _load_decider_cfg()
    return bool(cfg.get("elysia_unified_budget_surplus_opportunistic", True))


def remaining_fraction() -> float:
    """Fraction of period cap still unused (1.0 = full capacity left)."""
    if not enabled():
        return 1.0
    cap = max_units_per_period()
    if cap <= 0:
        return 1.0
    with _lock:
        _maybe_reset_period()
        return max(0.0, min(1.0, (cap - _consumed_units) / cap))


def opportunistic_surplus_available() -> bool:
    """
    True when enough period budget remains that we soften strict LLM preflight (see
    ``effective_cloud_chat_preflight``). Controlled by JSON ``elysia_unified_budget_surplus_*``.
    """
    if not enabled() or not surplus_opportunistic_enabled():
        return False
    cfg = _load_decider_cfg()
    try:
        min_frac = float(cfg.get("elysia_unified_budget_surplus_min_remaining_frac", 0.22))
    except (TypeError, ValueError):
        min_frac = 0.22
    min_frac = max(0.0, min(1.0, min_frac))
    return remaining_fraction() >= min_frac


def effective_cloud_chat_preflight(backend: str, max_tokens: int) -> float:
    """
    Units required for ``can_spend`` before OpenAI/OpenRouter chat. Uses pessimistic envelope
    by default; when ``opportunistic_surplus_available()``, blends down toward flat per-channel
    so leftover budget can be used by secondary calls during the same period.
    """
    ch = "openrouter_chat" if str(backend).lower().strip() == "openrouter" else "openai_chat"
    full = preflight_cloud_chat_estimate(max_tokens)
    if not enabled() or not opportunistic_surplus_available():
        return full
    cfg = _load_decider_cfg()
    try:
        blend = float(cfg.get("elysia_unified_budget_surplus_preflight_blend", 0.38))
    except (TypeError, ValueError):
        blend = 0.38
    blend = max(0.05, min(1.0, blend))
    flat = flat_units_for_channel(ch)
    # Between flat and full: tighten preflight when lots of budget is still unused.
    soft = flat + (full - flat) * blend
    return float(max(flat, min(full, soft)))


def effective_structured_preflight() -> float:
    """Similar to chat but channel ``openai_structured``."""
    full = flat_units_for_channel("openai_structured") * 3.5
    flat = flat_units_for_channel("openai_structured")
    if not enabled() or not opportunistic_surplus_available():
        return float(max(flat, min(full, preflight_cloud_chat_estimate(8192))))
    cfg = _load_decider_cfg()
    try:
        blend = float(cfg.get("elysia_unified_budget_surplus_structured_blend", 0.45))
    except (TypeError, ValueError):
        blend = 0.45
    blend = max(0.05, min(1.0, blend))
    soft = flat + (full - flat) * blend
    return float(max(flat, min(full, soft)))


def surplus_opportunity_hint() -> Dict[str, Any]:
    """
    Signals for autonomy / tooling: leftover budget suggests running low-cost API work.

    Brave/Tavily monthly vendor limits remain separate — this refers to the unified
    token-equivalent period budget only.
    """
    cfg = _load_decider_cfg()
    out: Dict[str, Any] = {
        "unified_budget_enabled": enabled(),
        "surplus_opportunistic": surplus_opportunistic_enabled(),
        "remaining_fraction": round(remaining_fraction(), 4) if enabled() else 1.0,
        "opportunistic_surplus_gate_met": opportunistic_surplus_available(),
        "suggested_actions": [],
    }
    if not enabled():
        return out

    sug: List[str] = []
    try:
        min_frac = float(cfg.get("elysia_unified_budget_surplus_min_remaining_frac", 0.22))
    except (TypeError, ValueError):
        min_frac = 0.22
    if remaining_fraction() >= min_frac:
        sug.append(
            "Period budget headroom remains — eligible for softened preflight on cloud chat "
            "and for search/HF inference; consider tool_registry_pulse, webscout, or enrichment."
        )
    out["suggested_actions"] = sug
    out["remaining_units"] = round(remaining_units(), 2)
    return out


def can_spend(units: float) -> bool:
    """True if spending ``units`` would not exceed the period cap."""
    if not enabled():
        return True
    cap = max_units_per_period()
    if cap <= 0:
        return True
    if units <= 0:
        return True
    with _lock:
        _maybe_reset_period()
        return (_consumed_units + float(units)) <= cap


def charge_successful_call(
    channel: str,
    ok: bool,
    usage: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, float]:
    """
    Add budget units for one completed call. Returns (charged_ok, units_applied).
    Failures do not consume units. If over cap, applies partial remainder or 0.
    """
    global _consumed_units
    if not enabled() or not ok:
        return True, 0.0
    cap = max_units_per_period()
    if cap <= 0:
        # Enabled but no cap configured — treat as unlimited (no charging).
        return True, 0.0
    units = _units_from_usage_or_flat(channel, usage)
    if units <= 0:
        return True, 0.0
    with _lock:
        _maybe_reset_period()
        room = max(0.0, cap - _consumed_units)
        applied = min(units, room)
        if applied <= 0:
            logger.warning(
                "[UnifiedBudget] cap reached; skipped %.0f units from channel=%s",
                units,
                channel,
            )
            return False, 0.0
        _consumed_units += applied
        if applied < units:
            logger.warning(
                "[UnifiedBudget] partial charge %.0f / %.0f for channel=%s (cap)",
                applied,
                units,
                channel,
            )
        return True, applied


def reset_period_state_for_tests() -> None:
    """Reset consumed counter and period start (unit tests only)."""
    global _consumed_units, _period_start_wall
    with _lock:
        _consumed_units = 0.0
        _period_start_wall = time.time()


def snapshot() -> Dict[str, Any]:
    with _lock:
        _maybe_reset_period()
        cap = max_units_per_period()
        cons = _consumed_units
        rem = max(0.0, cap - cons) if cap > 0 else float("inf")
    rf = 1.0
    gate_met = False
    if enabled() and cap > 0:
        rf = max(0.0, min(1.0, (cap - cons) / cap))
        cfg = _load_decider_cfg()
        try:
            min_frac = float(cfg.get("elysia_unified_budget_surplus_min_remaining_frac", 0.22))
        except (TypeError, ValueError):
            min_frac = 0.22
        min_frac = max(0.0, min(1.0, min_frac))
        gate_met = bool(surplus_opportunistic_enabled() and rf >= min_frac)
    return {
        "enabled": enabled(),
        "max_units_per_period": cap,
        "period_seconds": period_seconds(),
        "period_started_wall_epoch": _period_start_wall,
        "consumed_units": round(cons, 4),
        "remaining_units": round(rem, 4) if rem != float("inf") else None,
        "flat_defaults_note": "Flat units used when provider does not return token usage.",
        "surplus_opportunistic": surplus_opportunistic_enabled(),
        "remaining_frac": round(rf, 4),
        "opportunistic_surplus_gate_met": gate_met,
    }


def preflight_cloud_chat_estimate(max_tokens: int) -> float:
    """Conservative token-equivalent bound for one chat completion call."""
    try:
        mt = max(64, min(128000, int(max_tokens)))
    except (TypeError, ValueError):
        mt = 4096
    # Rough prompt+completion envelope for gating (preflight only).
    return float(min(32000, mt * 2 + 512))

