# project_guardian/planner_readiness.py
"""Planner readiness, Ollama model install verification, latency budget, autonomy gating hints."""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# Startup probe (set once at boot; optionally refreshed on recheck)
_canonical_model: str = ""
_ollama_reachable: bool = False
_model_installed: bool = False
_installed_names: List[str] = []
_startup_health_ok: bool = False
_startup_detail: str = ""
_last_tag_recheck_ts: float = 0.0
# After first run_startup_planner_probe return (success or fail)
_planner_boot_probe_complete: bool = False
_OLLAMA_BAD_TAG_SKIP_LOGGED: bool = False

# Latency budget
_lat_ring: Deque[Tuple[float, float, bool]] = deque(maxlen=12)  # (ts, ms, success)
_latency_degraded: bool = False
_last_readiness: str = "unknown"
_last_transition_log_ts: float = 0.0

# Env
def _slow_ms() -> float:
    try:
        return max(5000.0, float(os.environ.get("PLANNER_LATENCY_DEGRADED_MS", "45000")))
    except ValueError:
        return 45000.0


def _slow_hits_needed() -> int:
    try:
        return max(1, int(os.environ.get("PLANNER_LATENCY_SLOW_HITS", "2")))
    except ValueError:
        return 2


def _tag_recheck_sec() -> float:
    try:
        return max(30.0, float(os.environ.get("PLANNER_MODEL_RECHECK_SEC", "120")))
    except ValueError:
        return 120.0


def _degraded_timeout_scale() -> float:
    try:
        return max(0.35, min(1.0, float(os.environ.get("PLANNER_DEGRADED_TIMEOUT_SCALE", "0.55"))))
    except ValueError:
        return 0.55


DEGRADED_AUTONOMY_ACTIONS = frozenset({
    "execute_self_task",
    "tool_registry_pulse",
    "code_analysis",
    "income_modules_pulse",
    "continue_monitoring",
    "harvest_income_report",
    "question_probe",
})

# General autonomy: repeated no-op outcomes → temporary strong downrank
_autonomy_noop_streak: Dict[str, int] = {}
_autonomy_noop_suppress_until: Dict[str, float] = {}
_AUTONOMY_NOOP_STREAK_NEED = 3
_AUTONOMY_NOOP_SUPPRESS_SEC = 900.0  # 15m — within 10–20m spec

# Repeated $0 / 0-sales harvest → progressive priority downrank (separate from cooldown suppression)
_harvest_zero_yield_streak: int = 0

AUTONOMY_NOOP_TRACKED_ACTIONS = frozenset(
    {"work_on_objective", "execute_task", "process_queue", "harvest_income_report"}
)

# During early_runtime_budget (startup-age window), downrank noisy/low-yield autonomy picks
BOOT_LOW_VALUE_ACTIONS = frozenset(
    {
        "harvest_income_report",
        "work_on_objective",
        "execute_task",
        "process_queue",
        "tool_registry_pulse",
    }
)


def boot_low_value_action_factor(action: str) -> float:
    """Strong downrank for known low-value actions while early_runtime_budget is active."""
    try:
        from .startup_runtime_guard import early_runtime_budget_active

        if not early_runtime_budget_active():
            return 1.0
    except Exception:
        return 1.0
    act = (action or "").strip()
    if act in BOOT_LOW_VALUE_ACTIONS:
        return 0.1
    return 1.0

# Low-value degraded autonomy loop suppression
_degraded_low_streak: Dict[str, int] = {}
_degraded_suppress_until: Dict[str, float] = {}
_DEGRADED_SUPPRESS_SEC = 900.0
_DEGRADED_STREAK_NEED = 3


def _model_base_tag(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    return n.split(":", 1)[0].lower()


def exact_ollama_tag_installed(canonical: str, installed_tags: List[str]) -> bool:
    """True only if an installed tag equals the canonical string exactly (Ollama tag semantics)."""
    can = (canonical or "").strip()
    if not can:
        return False
    for t in installed_tags:
        if (t or "").strip() == can:
            return True
    return False


def suggest_close_ollama_tags(canonical: str, installed_tags: List[str]) -> List[str]:
    """Tags that share the same base name as canonical but are not an exact match (hints only)."""
    can = (canonical or "").strip()
    if not can:
        return []
    base = _model_base_tag(can)
    out: List[str] = []
    for t in installed_tags:
        ts = (t or "").strip()
        if not ts or ts == can:
            continue
        if _model_base_tag(ts) == base:
            out.append(ts)
    return out[:8]


def _autonomy_noop_streak_need(action_key: str) -> int:
    """Harvest no-ops can hit cooldown sooner (env-tunable); other actions use default."""
    key = (action_key or "").strip()
    if key == "harvest_income_report":
        try:
            return max(1, int(os.environ.get("ELYSIA_HARVEST_ZERO_AUTONOMY_NOOP_NEED", "2")))
        except ValueError:
            return 2
    return _AUTONOMY_NOOP_STREAK_NEED


def record_harvest_zero_yield_outcome(nonzero: bool) -> None:
    """Track consecutive zero-yield harvest runs for soft downranking; clear on any positive signal."""
    global _harvest_zero_yield_streak
    with _lock:
        if nonzero:
            _harvest_zero_yield_streak = 0
        else:
            _harvest_zero_yield_streak = min(30, _harvest_zero_yield_streak + 1)


def harvest_zero_yield_priority_factor(action: str) -> float:
    """Multiply priority_score for harvest after repeated $0 / zero-sales outcomes."""
    act = (action or "").strip()
    if act != "harvest_income_report":
        return 1.0
    with _lock:
        n = _harvest_zero_yield_streak
    if n <= 0:
        return 1.0
    if n == 1:
        return 0.52
    if n == 2:
        return 0.28
    return 0.14


def record_autonomy_noop_outcome(action_key: str, *, reason: str) -> None:
    """Count a no-op autonomy outcome; after N streak, suppress action selection for a cooldown."""
    global _autonomy_noop_streak, _autonomy_noop_suppress_until
    now = time.time()
    key = (action_key or "").strip()
    if not key or key not in AUTONOMY_NOOP_TRACKED_ACTIONS:
        return
    need = _autonomy_noop_streak_need(key)
    with _lock:
        n = int(_autonomy_noop_streak.get(key, 0) or 0) + 1
        _autonomy_noop_streak[key] = n
        if n >= need:
            _autonomy_noop_suppress_until[key] = now + _AUTONOMY_NOOP_SUPPRESS_SEC
            _autonomy_noop_streak[key] = 0
            logger.warning(
                "[AutonomyNoop] Suppressing action=%s for %.0fs after %d× no-op in window (%s)",
                key,
                _AUTONOMY_NOOP_SUPPRESS_SEC,
                need,
                reason,
            )


def clear_autonomy_noop_streak(action_key: str) -> None:
    key = (action_key or "").strip()
    if not key:
        return
    with _lock:
        _autonomy_noop_streak.pop(key, None)
        _autonomy_noop_suppress_until.pop(key, None)


def autonomy_noop_suppression_factor(action: str) -> float:
    """Strong downrank (×0.06) while action is in no-op suppression cooldown."""
    now = time.time()
    act = (action or "").strip()
    if not act:
        return 1.0
    if float(_autonomy_noop_suppress_until.get(act, 0) or 0) > now:
        return 0.06
    return 1.0


def boost_alternatives_when_autonomy_noop_suppressed(
    candidates: List[Dict[str, Any]],
    exploratory_actions: List[str],
) -> None:
    """When tracked actions are suppressed, nudge toward probes / bounded self-tasks / capabilities."""
    if not candidates:
        return
    if not any(autonomy_noop_suppression_factor(str(c.get("action") or "")) < 1.0 for c in candidates):
        return
    ex_set = set(exploratory_actions or [])
    for c in candidates:
        act = str(c.get("action") or "")
        if act in AUTONOMY_NOOP_TRACKED_ACTIONS:
            continue
        if act == "execute_self_task":
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 4.0
            c["_noop_alt_boost"] = True
        elif act == "question_probe":
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 3.2
            c["_noop_alt_boost"] = True
        elif act.startswith("use_capability/"):
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 2.8
            c["_noop_alt_boost"] = True
        elif act in ex_set:
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 1.25
            c["_noop_alt_boost"] = True


def degraded_autonomy_suppression_factor(action: str) -> float:
    """Strong downrank when action is in cooldown after repeated low-value degraded runs."""
    now = time.time()
    act = (action or "").strip()
    if not act:
        return 1.0
    if float(_degraded_suppress_until.get(act, 0) or 0) > now:
        return 0.12
    return 1.0


def record_degraded_low_value_signal(action_key: str, *, reason: str) -> None:
    """Increment streak; after N identical low-value signals, cooldown suppresses this action key."""
    global _degraded_low_streak, _degraded_suppress_until
    now = time.time()
    key = (action_key or "").strip()
    if not key:
        return
    with _lock:
        n = int(_degraded_low_streak.get(key, 0) or 0) + 1
        _degraded_low_streak[key] = n
        if n >= _DEGRADED_STREAK_NEED:
            _degraded_suppress_until[key] = now + _DEGRADED_SUPPRESS_SEC
            _degraded_low_streak[key] = 0
            logger.warning(
                "[DegradedAutonomy] Suppressing action=%s for %.0fs (%d× low-value: %s)",
                key,
                _DEGRADED_SUPPRESS_SEC,
                _DEGRADED_STREAK_NEED,
                reason,
            )


def should_short_circuit_verify_ollama_for_bad_tag(model: str) -> Tuple[bool, str]:
    """
    After startup probe: Ollama is reachable but configured canonical tag is not installed exactly.
    Avoid repeated /api/chat probes with a model name Ollama will reject.
    """
    global _OLLAMA_BAD_TAG_SKIP_LOGGED
    if not _planner_boot_probe_complete:
        return False, ""
    try:
        from .ollama_model_config import get_canonical_ollama_model

        canon = (get_canonical_ollama_model(log_once=False) or "").strip()
    except Exception:
        canon = ""
    cm = (model or "").strip()
    if canon and cm and cm != canon:
        return False, ""
    with _lock:
        reachable = _ollama_reachable
        installed = _model_installed
    if not reachable or installed:
        return False, ""
    if not _OLLAMA_BAD_TAG_SKIP_LOGGED:
        _OLLAMA_BAD_TAG_SKIP_LOGGED = True
        logger.warning(
            "[Ollama] Skipping local chat/generate probes for canonical %r (not an exact installed tag; fix ELYSIA_OLLAMA_MODEL or mistral_decider.json)",
            canon,
        )
    return True, "canonical_ollama_tag_not_installed_exact"


def clear_degraded_low_value_streak(action_key: str) -> None:
    """Call when a run produced meaningful state / non-zero signal to avoid false suppression."""
    key = (action_key or "").strip()
    if not key:
        return
    with _lock:
        _degraded_low_streak.pop(key, None)
        _degraded_suppress_until.pop(key, None)


def note_degraded_execute_self_task_outcome(
    *,
    tier: str,
    useful: bool,
    objective_advanced: bool,
    archetype: str,
) -> None:
    if (tier or "").lower() == "strong" and useful and not objective_advanced:
        record_degraded_low_value_signal(
            "execute_self_task",
            reason=f"strong_useful_nonadv archetype={archetype}",
        )
    elif objective_advanced:
        clear_degraded_low_value_streak("execute_self_task")


def run_startup_planner_probe(*, log_tags_on_fail: bool = True) -> Dict[str, Any]:
    """
    Sync startup: list Ollama tags, verify canonical model is installed, then runtime health probe.
    Sets module state; logs [Ollama] canonical_model=… installed=….
    """
    global _canonical_model, _ollama_reachable, _model_installed, _installed_names
    global _startup_health_ok, _startup_detail, _last_tag_recheck_ts
    global _planner_boot_probe_complete

    from .ollama_health import list_ollama_installed_model_names, normalize_ollama_base, verify_ollama_runtime
    from .ollama_model_config import get_canonical_ollama_model, set_effective_ollama_model_from_planner

    try:
        canon = get_canonical_ollama_model(log_once=False)
        base = normalize_ollama_base(None)
        names, err = list_ollama_installed_model_names(base_url=base)
        now = time.time()
        _last_tag_recheck_ts = now

        env_ollama = bool((os.environ.get("ELYSIA_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL") or "").strip())
        suggest = suggest_close_ollama_tags(canon, names)
        exact = exact_ollama_tag_installed(canon, names)
        if not exact and not env_ollama and len(suggest) == 1:
            set_effective_ollama_model_from_planner(suggest[0])
            canon = get_canonical_ollama_model(log_once=False)
            exact = exact_ollama_tag_installed(canon, names)
            logger.info("[Guardian] Resolved Ollama to single installed variant: %s", canon)

        with _lock:
            _canonical_model = canon
            _installed_names = list(names)
            _ollama_reachable = err is None
            _model_installed = exact

        logger.info(
            "[Guardian] canonical_ollama_effective=%s exact_tag_match=%s installed_tags=%s suggested_close=%s",
            canon,
            exact,
            list(names[:24]),
            suggest if suggest else [],
        )
        if suggest and not exact:
            logger.info(
                "[Ollama] hint: set ELYSIA_OLLAMA_MODEL or mistral_decider_model to an exact installed tag "
                "(e.g. %s) if that is the model you intend",
                suggest[0],
            )

        if err:
            with _lock:
                _startup_health_ok = False
                _startup_detail = err
            logger.error("[PlannerReadiness] Ollama unreachable (tags): %s", err)
            return snapshot_startup_dict()

        if not _model_installed:
            with _lock:
                _startup_health_ok = False
                _startup_detail = "canonical_model_not_in_ollama_tags"
            if log_tags_on_fail and names:
                logger.error(
                    "[PlannerReadiness] Canonical model %r not installed; Ollama has: %s",
                    canon,
                    ", ".join(names[:24]) + (" …" if len(names) > 24 else ""),
                )
            elif log_tags_on_fail:
                logger.error("[PlannerReadiness] Canonical model %r not installed; Ollama reports no models", canon)
            return snapshot_startup_dict()

        h = verify_ollama_runtime(base, canon, timeout=14.0)
        with _lock:
            _startup_health_ok = bool(h.ok)
            _startup_detail = h.detail if h.ok else (h.detail or "health_fail")

        if not h.ok:
            logger.error("[PlannerReadiness] Ollama health probe failed after model install check: %s", _startup_detail)

        return snapshot_startup_dict()
    finally:
        _planner_boot_probe_complete = True


def maybe_refresh_model_install_if_stale() -> None:
    """If we previously had missing/wrong model, periodically re-list tags (light GET)."""
    global _model_installed, _installed_names, _ollama_reachable, _last_tag_recheck_ts
    global _startup_health_ok

    if _model_installed and _startup_health_ok:
        return
    now = time.time()
    if now - _last_tag_recheck_ts < _tag_recheck_sec():
        return

    from .ollama_health import list_ollama_installed_model_names, normalize_ollama_base
    from .ollama_model_config import get_canonical_ollama_model

    canon = get_canonical_ollama_model(log_once=False)
    base = normalize_ollama_base(None)
    names, err = list_ollama_installed_model_names(base_url=base)
    need_health = False
    with _lock:
        _last_tag_recheck_ts = now
        _installed_names = list(names)
        _ollama_reachable = err is None
        if err is None:
            _model_installed = exact_ollama_tag_installed(canon, names)
        if _model_installed and not _startup_health_ok:
            need_health = True
    if need_health:
        logger.info("[PlannerReadiness] Re-verifying Ollama health (model in tags, startup health was not ok)")
        from .ollama_health import verify_ollama_runtime

        h = verify_ollama_runtime(base, canon, timeout=12.0)
        with _lock:
            _startup_health_ok = bool(h.ok)
            if not h.ok:
                _startup_detail = (h.detail or "recheck_health_fail")[:300]


def snapshot_startup_dict() -> Dict[str, Any]:
    with _lock:
        canon = _canonical_model
        tags_full = list(_installed_names)
        inst = _model_installed
        reach = _ollama_reachable
        detail = (_startup_detail or "")[:300]
        health = _startup_health_ok
    suggest = suggest_close_ollama_tags(canon, tags_full) if canon else []
    exact = exact_ollama_tag_installed(canon, tags_full) if canon else inst
    return {
        "canonical_ollama_model": canon,
        "ollama_reachable": reach,
        "exact_tag_match": exact,
        "model_installed": inst,
        "installed_model_tags": tags_full[:32],
        "suggested_close_tags": suggest,
        "startup_health_ok": health,
        "startup_detail": detail,
    }


def record_planner_latency_ms(millis: float, *, success: bool) -> None:
    global _latency_degraded, _last_transition_log_ts
    thr = _slow_ms()
    need = _slow_hits_needed()
    now = time.time()
    with _lock:
        _lat_ring.append((now, float(millis), success))
        recent = list(_lat_ring)
        slow_success = [m for _ts, m, ok in recent[-8:] if ok and m >= thr]
        if len(slow_success) >= need:
            if not _latency_degraded:
                _latency_degraded = True
                if now - _last_transition_log_ts > 20.0:
                    _last_transition_log_ts = now
                    logger.warning(
                        "[PlannerReadiness] Latency budget → DEGRADED (%d planner calls ≥%.0fms in recent window)",
                        len(slow_success),
                        thr,
                    )
        # recover: last 2 successful runs both under half threshold
        ok_recent = [(m, ok) for _ts, m, ok in recent[-4:] if ok]
        if len(ok_recent) >= 2 and ok_recent[-1][0] < thr * 0.5 and ok_recent[-2][0] < thr * 0.5:
            if _latency_degraded:
                _latency_degraded = False
                if now - _last_transition_log_ts > 20.0:
                    _last_transition_log_ts = now
                    logger.info("[PlannerReadiness] Latency budget recovered → cleared planner latency DEGRADED")


def effective_planner_http_timeout_sec(default_sec: float) -> float:
    """Shorter timeouts when planner is latency-degraded."""
    base = max(12.0, float(default_sec))
    if _latency_degraded:
        return max(12.0, base * _degraded_timeout_scale())
    return base


def _circuit_open() -> bool:
    try:
        from .local_planner_breaker import is_planner_circuit_open

        return is_planner_circuit_open()
    except Exception:
        return False


def compute_readiness_label() -> str:
    """
    ready: model installed, ollama reachable, startup health ok, circuit closed, not latency-degraded.
    degraded: can probe with limits (installed but slow/soft failure path).
    unavailable: no model, unreachable, circuit open, or startup health failed hard.
    """
    maybe_refresh_model_install_if_stale()

    with _lock:
        reachable = _ollama_reachable
        installed = _model_installed
        health0 = _startup_health_ok
    circ = _circuit_open()
    lat_deg = _latency_degraded

    if not reachable or not installed:
        return "unavailable"
    if circ:
        return "unavailable"
    if not health0:
        return "unavailable"
    if lat_deg:
        return "degraded"
    return "ready"


def refresh_readiness_log_transition() -> str:
    global _last_readiness, _last_transition_log_ts
    label = compute_readiness_label()
    with _lock:
        prev = _last_readiness
        _last_readiness = label
    if prev != label:
        now = time.time()
        if now - _last_transition_log_ts > 5.0:
            _last_transition_log_ts = now
            logger.info("[PlannerReadiness] readiness transition %s → %s", prev, label)
    return label


def autonomy_planner_gate(decision_cycle: int) -> Tuple[bool, str, str]:
    """
    Returns (allow_mistral_planner, block_reason, autonomy_planner_mode).
    autonomy_planner_mode: normal | limited_planner | degraded_autonomy
    """
    lbl = refresh_readiness_log_transition()
    if lbl == "unavailable":
        return False, "planner_unavailable", "degraded_autonomy"
    if lbl == "degraded":
        # Alternate cycles to cap load when latency-degraded
        if decision_cycle % 2 == 0:
            return False, "planner_degraded_throttle", "degraded_autonomy"
        return True, "", "limited_planner"
    return True, "", "normal"


def pick_degraded_autonomy_candidate(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    pool = [c for c in candidates if (c.get("action") or "") in DEGRADED_AUTONOMY_ACTIONS]
    if not pool:
        return None
    return max(
        pool,
        key=lambda c: float(c.get("priority_score", 0) or 0)
        * degraded_autonomy_suppression_factor(str(c.get("action") or ""))
        * autonomy_noop_suppression_factor(str(c.get("action") or ""))
        * harvest_zero_yield_priority_factor(str(c.get("action") or ""))
        * boot_low_value_action_factor(str(c.get("action") or "")),
    )


def recent_planner_latency_summary() -> Dict[str, Any]:
    with _lock:
        rows = [(m, ok) for _ts, m, ok in list(_lat_ring)[-6:]]
    if not rows:
        return {"samples": 0, "last_ms": None, "avg_ms": None}
    ms_vals = [m for m, _ in rows]
    return {
        "samples": len(rows),
        "last_ms": round(ms_vals[-1], 1),
        "avg_ms": round(sum(ms_vals) / len(ms_vals), 1),
        "latency_degraded_flag": _latency_degraded,
        "slow_threshold_ms": round(_slow_ms(), 1),
    }


def compact_runtime_status() -> Dict[str, Any]:
    """Single compact dict for dashboards / API (Fix 5)."""
    from .cloud_api_state import (
        any_llm_cloud_key_loaded,
        cloud_credentials_snapshot,
        human_openai_routing_message,
        openai_routing_block_reason,
        openai_usable_for_routing,
        usable_cloud_routing_snapshot,
    )

    try:
        from .local_planner_breaker import circuit_breaker_snapshot
    except Exception:
        circuit_breaker_snapshot = lambda: {}  # type: ignore

    oa_deg = False
    try:
        from .openai_degraded import is_openai_degraded_active

        oa_deg = bool(is_openai_degraded_active())
    except Exception:
        pass

    snap = snapshot_startup_dict()
    lbl = compute_readiness_label()
    cc = cloud_credentials_snapshot()
    ucloud = usable_cloud_routing_snapshot()
    mode = "degraded_autonomy" if lbl == "unavailable" else ("limited_planner" if lbl == "degraded" else "normal")
    startup_thin = False
    early_budget = False
    startup_age = None
    emb_fb = False
    try:
        from .startup_runtime_guard import (
            early_runtime_budget_active,
            embedding_fallback_loaded_status,
            startup_age_sec,
            startup_memory_thin_mode_active,
        )

        startup_thin = bool(startup_memory_thin_mode_active())
        early_budget = bool(early_runtime_budget_active())
        _sag = startup_age_sec()
        startup_age = round(float(_sag), 1) if _sag is not None else None
        emb_fb = bool(embedding_fallback_loaded_status())
    except Exception:
        pass
    return {
        "canonical_ollama_model": snap.get("canonical_ollama_model"),
        "ollama_exact_tag_match": snap.get("exact_tag_match"),
        "ollama_installed_match": snap.get("model_installed"),
        "ollama_suggested_close_tags": snap.get("suggested_close_tags"),
        "ollama_reachable": snap.get("ollama_reachable"),
        "installed_model_tags_sample": snap.get("installed_model_tags"),
        "planner_readiness": lbl,
        "autonomy_planner_mode": mode,
        "degraded_planner_alternate_cycles": lbl == "degraded",
        "planner_circuit": circuit_breaker_snapshot(),
        "planner_latency": recent_planner_latency_summary(),
        "cloud_any_llm_key": any_llm_cloud_key_loaded(),
        "cloud_openai_usable": openai_usable_for_routing(),
        "cloud_openai_block_reason": openai_routing_block_reason(),
        "cloud_openai_block_message": human_openai_routing_message(openai_routing_block_reason()),
        "openai_degraded_active": oa_deg,
        "usable_cloud_routing": ucloud,
        "cloud_keys_snapshot": {
            "openai": bool(cc.get("openai")),
            "openrouter": bool(cc.get("openrouter")),
            "anthropic": bool(cc.get("anthropic")),
        },
        "startup_thin_mode": startup_thin,
        "early_runtime_budget": early_budget,
        "startup_age_sec": startup_age,
        "embedding_fallback_loaded": emb_fb,
    }


def planner_context_for_snapshot(decision_cycle: int) -> Dict[str, Any]:
    """Small blob for Mistral guardian_state / metadata."""
    refresh_readiness_log_transition()
    gate_ok, reason, mode = autonomy_planner_gate(decision_cycle)
    return {
        "planner_readiness": compute_readiness_label(),
        "autonomy_planner_mode": mode,
        "planner_gate_allow_mistral": gate_ok,
        "planner_gate_reason": reason,
        "latency": recent_planner_latency_summary(),
    }
