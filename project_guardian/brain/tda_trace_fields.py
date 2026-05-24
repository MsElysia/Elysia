# project_guardian/brain/tda_trace_fields.py
"""Canonical Think–Decide–Act trace field names and read/write helpers."""

from __future__ import annotations

from typing import Any, Dict, MutableMapping, Optional

# Canonical persisted / in-memory detailed trace payload
CANONICAL_TDA_TRACE_KEY = "think_decide_act_trace"
# Backwards-compatible alias (same object reference when written)
ALIAS_TDA_TRACE_KEY = "tda_trace"
# Compact boolean for APIs / dashboards (derived, not a second trace blob)
TDA_TRACE_PRESENT_KEY = "think_decide_act_trace_present"
# User-friendly summary flag (API only; not a duplicate trace store)
TDA_USED_SUMMARY_KEY = "tda_used"


def get_think_decide_act_trace(trace: Any) -> Optional[Dict[str, Any]]:
    """Return the detailed TDA trace dict from a trace object or persisted JSON dict."""
    if trace is None:
        return None
    if isinstance(trace, dict):
        canonical = trace.get(CANONICAL_TDA_TRACE_KEY)
        if canonical is not None:
            return canonical if isinstance(canonical, dict) else None
        alias = trace.get(ALIAS_TDA_TRACE_KEY)
        return alias if isinstance(alias, dict) else None
    canonical = getattr(trace, CANONICAL_TDA_TRACE_KEY, None)
    if canonical is not None:
        return canonical if isinstance(canonical, dict) else None
    alias = getattr(trace, ALIAS_TDA_TRACE_KEY, None)
    return alias if isinstance(alias, dict) else None


def has_think_decide_act_trace(trace: Any) -> bool:
    return get_think_decide_act_trace(trace) is not None


def think_decide_act_trace_present(trace_dict: Dict[str, Any]) -> bool:
    """Whether TDA ran, from explicit flag or presence of trace payload."""
    if not isinstance(trace_dict, dict):
        return False
    if TDA_TRACE_PRESENT_KEY in trace_dict:
        return bool(trace_dict.get(TDA_TRACE_PRESENT_KEY))
    return has_think_decide_act_trace(trace_dict)


def apply_persisted_tda_fields(payload: MutableMapping[str, Any], trace: Any) -> None:
    """Write canonical + alias keys into a JSON-serializable trace document."""
    detailed = get_think_decide_act_trace(trace)
    if detailed is None and hasattr(trace, CANONICAL_TDA_TRACE_KEY):
        raw = getattr(trace, CANONICAL_TDA_TRACE_KEY, None)
        detailed = raw if isinstance(raw, dict) else None
    present = detailed is not None
    payload[TDA_TRACE_PRESENT_KEY] = present
    if present:
        payload[CANONICAL_TDA_TRACE_KEY] = detailed
        payload[ALIAS_TDA_TRACE_KEY] = detailed
    else:
        payload.pop(CANONICAL_TDA_TRACE_KEY, None)
        payload.pop(ALIAS_TDA_TRACE_KEY, None)
