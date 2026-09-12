# project_guardian/planner_readiness.py
"""Planner readiness, Ollama model install verification, latency budget, autonomy gating hints."""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_HTTP_URL_RE = re.compile(r"https?://[^\s<>'\")]+", re.IGNORECASE)

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
# Ollama startup stabilization (second spaced health probe); exposed for [StartupGate] logs
_ollama_startup_probe_passes: int = 0

# Staged planner startup (orthogonal to legacy double-probe passes)
_runtime_alive: bool = False
_planner_model_available: bool = False
_planner_inference_ok: bool = False

_last_runtime_snapshot_log_ts: float = 0.0

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
    "consider_moltbook_direction",
})

# General autonomy: repeated no-op outcomes → temporary strong downrank
_autonomy_noop_streak: Dict[str, int] = {}
_autonomy_noop_suppress_until: Dict[str, float] = {}
_AUTONOMY_NOOP_STREAK_NEED = 3
_AUTONOMY_NOOP_SUPPRESS_SEC = 900.0  # 15m — within 10–20m spec

# Repeated $0 / 0-sales harvest → progressive priority downrank (separate from cooldown suppression)
_harvest_zero_yield_streak: int = 0

AUTONOMY_NOOP_TRACKED_ACTIONS = frozenset(
    {
        "work_on_objective",
        "execute_task",
        "process_queue",
        "harvest_income_report",
        "income_modules_pulse",
        "fractalmind_planning",
    }
)


def execute_task_system_monitoring_priority_factor(
    candidate: Dict[str, Any],
    guardian: Optional[Any],
    recent_actions: Optional[List[str]],
) -> float:
    """
    Downrank execute_task when it would repeatedly target the routine ``system_monitoring`` seed task
    without stronger evidence (other tasks / higher scores).
    """
    if str(candidate.get("action") or "").strip() != "execute_task":
        return 1.0
    meta = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    nm = str(meta.get("name") or "").strip().lower()
    if nm != "system_monitoring":
        return 1.0
    tail = [str(x) for x in (recent_actions or []) if x][-10:]
    ex = sum(1 for x in tail if x == "execute_task")
    mult = 1.0
    if ex >= 5:
        mult = 0.022
    elif ex >= 3:
        mult = 0.06
    elif ex >= 2:
        mult = 0.1
    else:
        mult = 0.32
    if guardian is not None:
        streak = int(getattr(guardian, "_execute_task_monitoring_select_streak", 0) or 0)
        if streak >= 1:
            mult *= 0.42 ** min(streak, 7)
    return max(0.012, min(1.0, mult))


def fractalmind_planning_repeat_priority_factor(
    guardian: Optional[Any],
    recent_actions: Optional[List[str]],
) -> float:
    """Downrank fractalmind_planning when the same artifact streak is building or repetition cooldown is active."""
    if guardian is None:
        return 1.0
    rep_until = getattr(guardian, "_fractalmind_repetition_suppress_until", None)
    if rep_until is not None:
        try:
            if float(rep_until) > time.time():
                return 0.018
        except (TypeError, ValueError):
            pass
    streak = int(getattr(guardian, "_fractalmind_same_artifact_streak", 0) or 0)
    mult = 1.0
    if streak >= 1:
        mult *= max(0.035, 0.38 ** min(streak, 9))
    tail = [str(x) for x in (recent_actions or []) if x][-12:]
    n_f = sum(1 for x in tail if x == "fractalmind_planning")
    if n_f >= 2:
        mult *= max(0.05, 0.52 ** max(0, n_f - 1))
    return max(0.012, min(1.0, mult))


def process_queue_stale_probe_priority_factor(guardian: Optional[Any]) -> float:
    """Strong downrank after consecutive process_queue probes left queue totals unchanged."""
    if guardian is None:
        return 1.0
    until = float(getattr(guardian, "_process_queue_noop_deprioritize_until", 0.0) or 0.0)
    if until > time.time():
        return 0.035
    streak = int(getattr(guardian, "_process_queue_unchanged_streak", 0) or 0)
    if streak >= 1:
        if streak == 1:
            return 0.55
        return max(0.035, 0.26 ** min(streak - 1, 7))
    return 1.0


def income_pulse_duplicate_priority_factor(guardian: Optional[Any], action: str) -> float:
    """Downrank income_modules_pulse when the last pulses were all-zero with an unchanged signature."""
    if guardian is None or str(action or "").strip() != "income_modules_pulse":
        return 1.0
    n = int(getattr(guardian, "_income_pulse_same_zero_sig_streak", 0) or 0)
    if n <= 0:
        return 1.0
    if n == 1:
        m = 0.78
    else:
        m = max(0.04, 0.4 ** min(n, 7))
    return m


def _use_capability_stale_streak(guardian: Any, module_name: str) -> int:
    st = getattr(guardian, "_use_capability_autonomy_fp_state", None)
    if isinstance(st, dict):
        ent = st.get(module_name)
        if isinstance(ent, dict):
            return int(ent.get("streak", 0) or 0)
    if module_name == "income_generator":
        return int(getattr(guardian, "_income_generator_autonomy_cap_streak", 0) or 0)
    return 0


def use_capability_module_stale_factor(guardian: Optional[Any], action: str) -> float:
    """
    Downrank ``use_capability/module/<name>`` when autonomy repeatedly got the same result fingerprint
    for modules listed in ``autonomy.json`` → ``use_capability_stale_fingerprint_modules`` (default: income_generator).
    """
    a = str(action or "").strip()
    if guardian is None:
        return 1.0
    if not a.startswith("use_capability/module/"):
        return 1.0
    parts = a.split("/")
    if len(parts) < 3:
        return 1.0
    mod = str(parts[2] or "").strip()
    targets: List[str] = []
    try:
        if hasattr(guardian, "_load_autonomy_config"):
            raw = guardian._load_autonomy_config().get("use_capability_stale_fingerprint_modules")
            if isinstance(raw, list):
                targets = [str(x).strip() for x in raw if str(x).strip()]
    except Exception:
        targets = []
    if not targets:
        targets = ["income_generator"]
    if mod not in targets:
        return 1.0
    streak = _use_capability_stale_streak(guardian, mod)
    if streak <= 0:
        return 1.0
    return max(0.025, 0.45 ** min(streak, 8))


def income_generator_capability_stale_factor(guardian: Optional[Any], action: str) -> float:
    """Backward-compatible alias for :func:`use_capability_module_stale_factor`."""
    return use_capability_module_stale_factor(guardian, action)


def web_capability_missing_url_priority_factor(candidate: Dict[str, Any]) -> float:
    """Downrank direct web-tool capability picks that do not carry an http(s) URL."""
    act = str((candidate or {}).get("action") or "").strip().lower()
    if act != "use_capability/tool/elysia_builtin_web":
        return 1.0
    parts: List[str] = []
    for key in ("url", "href", "link", "query", "task", "prompt", "text", "objective", "reason"):
        val = candidate.get(key)
        if val is not None:
            parts.append(str(val))
    meta = candidate.get("metadata")
    if isinstance(meta, dict):
        for key in ("url", "href", "link", "query", "task", "prompt", "text", "objective", "reason"):
            val = meta.get(key)
            if val is not None:
                parts.append(str(val))
    return 1.0 if _HTTP_URL_RE.search(" ".join(parts)) else 0.04


def apply_autonomy_loop_load_guards(
    guardian: Optional[Any],
    candidates: List[Dict[str, Any]],
    recent_actions: Optional[List[str]] = None,
) -> None:
    """
    Multiply priority_score in-place (deterministic).
    Queue / monitoring / fractal churn is handled in autonomy_antiloop (single combined pass).
    Here we apply narrow input/no-op dampening and skip execute_self_task.
    """
    if not candidates:
        return
    for c in candidates:
        act = str(c.get("action") or "")
        if act == "execute_self_task":
            continue
        base = float(c.get("priority_score", 0) or 0)
        if base <= 0:
            continue
        m3 = income_pulse_duplicate_priority_factor(guardian, act)
        m4 = web_capability_missing_url_priority_factor(c)
        combined = m3 * m4
        if combined < 0.999:
            new_score = base * combined
            c["priority_score"] = new_score
            c["_autonomy_loop_guard"] = {
                "income_pulse_dup": round(m3, 4),
                "web_missing_url": round(m4, 4),
                "combined": round(combined, 4),
            }
            logger.info(
                "[AutonomySelector] deprioritized action=%s score %.4f→%.4f reason=income_pulse_unchanged_zero mult=%.4f",
                act,
                base,
                new_score,
                combined,
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
    act = equivalent_autonomy_action_key(action)
    if act in BOOT_LOW_VALUE_ACTIONS:
        return 0.1
    return 1.0


def planner_startup_stabilization_required() -> bool:
    """When True, run_startup_planner_probe performs a second Ollama health check after a short gap."""
    v = (os.environ.get("ELYSIA_PLANNER_STARTUP_STABILIZATION") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _stabilization_gap_sec() -> float:
    try:
        return max(2.0, float(os.environ.get("ELYSIA_OLLAMA_STABILIZATION_GAP_SEC", "4")))
    except ValueError:
        return 4.0


_last_gate_bundle_log_ts: float = 0.0
_last_restricted_safe_log_ts: float = 0.0

# Autonomy: strict safe pool when local planner is unhealthy and OpenAI routing is unusable
RESTRICTED_SAFE_AUTONOMY_ACTIONS = frozenset(
    {
        "tool_registry_pulse",
        "income_modules_pulse",
        "continue_monitoring",
        "code_analysis",
        "question_probe",
        "consider_moltbook_direction",
    }
)

# Early boot: suppress repeated low-yield picks (cycles = Mistral decision cycles when enabled)
STARTUP_ANTITHRASH_ACTIONS = frozenset(
    {
        "system_monitoring",
        "fractalmind_planning",
        "generate_revenue_shortlist",
    }
)

# Bounded repair / diagnostic self-task archetypes (allowed when monetization subsystem not ready)
SUBSYSTEM_REPAIR_DIAGNOSTIC_ARCHETYPES = frozenset(
    {
        "validate_tool_registry_snapshot",
        "repair_tool_registry_coverage",
        "api_capability_smoke",
        "post_startup_health_snapshot",
        "finance_idle_pulse",
        "harvest_readonly_snapshot",
        "refresh_objective_snapshot",
    }
)


def _antithrash_max_cycle() -> int:
    try:
        return max(3, int(os.environ.get("ELYSIA_STARTUP_ANTITHRASH_MAX_CYCLES", "10")))
    except ValueError:
        return 10


def is_subsystem_repair_or_diagnostic_archetype(archetype: str) -> bool:
    a = (archetype or "").strip().lower()
    if not a:
        return False
    if a in SUBSYSTEM_REPAIR_DIAGNOSTIC_ARCHETYPES:
        return True
    if "repair_tool" in a or a.startswith("validate_tool_registry"):
        return True
    return False


def is_revenue_monetization_archetype(archetype: str) -> bool:
    a = (archetype or "").lower()
    keys = (
        "revenue_shortlist",
        "generate_revenue",
        "monetization",
        "dry_run_offer",
        "small_dry_run_offer",
        "offer_pack",
        "operator_offer",
        "offer_page",
        "finance_revenue",
        "revenue_creator",
        "idle_capabilities_with_market_value",
        "market_value",
        "evaluate_existing_objectives_for_monetization",
    )
    return any(k in a for k in keys)


def monetization_subsystems_ready(guardian: Any) -> Tuple[bool, Dict[str, bool]]:
    """
    Income path + wallet + financial_manager must be present and expose read-only summary hooks.
    Used to gate revenue shortlist / monetization self-tasks during startup.
    """
    mods = getattr(guardian, "_modules", None) or {}
    ig_mod = mods.get("income_generator")
    w_mod = mods.get("wallet")
    fm_mod = mods.get("financial_manager")
    ig = bool(ig_mod and hasattr(ig_mod, "get_income_summary"))
    wallet = bool(w_mod and hasattr(w_mod, "get_balance"))
    fm = bool(fm_mod and hasattr(fm_mod, "get_financial_status"))
    detail = {
        "income_generator": ig,
        "wallet": wallet,
        "financial_manager": fm,
    }
    return bool(ig and wallet and fm), detail


def monetization_priority_factor(action: str, archetype_hint: str, guardian: Optional[Any]) -> float:
    """Downrank monetization-style work when income/wallet/fm are not all ready."""
    act = (action or "").strip()
    arch = (archetype_hint or "").strip()
    if is_subsystem_repair_or_diagnostic_archetype(arch):
        return 1.0
    is_rev = act == "generate_revenue_shortlist" or (
        act == "execute_self_task" and is_revenue_monetization_archetype(arch)
    )
    if not is_rev:
        return 1.0
    if guardian is None:
        return 1.0
    ok, _ = monetization_subsystems_ready(guardian)
    return 1.0 if ok else 0.07


def staged_runtime_alive() -> bool:
    with _lock:
        return bool(_runtime_alive)


def staged_planner_model_available() -> bool:
    with _lock:
        return bool(_planner_model_available)


def staged_planner_inference_ok() -> bool:
    with _lock:
        return bool(_planner_inference_ok)


def local_planner_provider_ready() -> bool:
    """Local Ollama path: tags reachable, model installed, and (optional) lightweight inference succeeded."""
    with _lock:
        return bool(_runtime_alive and _planner_model_available and _planner_inference_ok)


def local_planner_reasoning_truth_snapshot() -> Dict[str, Any]:
    """
    Local Ollama path: configured vs routable vs usable (no network in this helper).
    - configured: non-empty canonical model from config
    - routable: configured and tags reachable and exact model tag present
    - usable: routable and staged inference succeeded (matches local_planner_provider_ready)
    - autonomy_safe: same as usable (required for normal autonomy capability)
    """
    try:
        from .ollama_model_config import get_canonical_ollama_model

        canon = (get_canonical_ollama_model(log_once=False) or "").strip()
    except Exception:
        canon = ""
    configured = bool(canon)
    alive = staged_runtime_alive()
    model_ok = staged_planner_model_available()
    inf_ok = staged_planner_inference_ok()
    routable = configured and alive and model_ok
    usable = bool(local_planner_provider_ready())
    br: Optional[str] = None
    if usable:
        br = None
    elif not configured:
        br = "not_configured"
    elif not alive:
        br = "not_routable"
    elif not model_ok:
        br = "model_missing"
    elif not inf_ok:
        br = "inference_unverified"
    else:
        br = "not_routable"
    return {
        "configured": configured,
        "routable": routable,
        "usable": usable,
        "autonomy_safe": usable,
        "blocked_reason": br,
    }


def reasoning_provider_capability_snapshot(
    *,
    _cloud_truth: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Per-provider view for autonomy vs routing: local + cloud truth entries include autonomy_safe
    (normal-autonomy capability path). No network I/O.

    Pass _cloud_truth to reuse an existing provider_reasoning_truth_snapshot() dict (avoids duplicate
    key-manager reads in build_runtime_decision_status_dict).
    """
    local_t = local_planner_reasoning_truth_snapshot()
    out: Dict[str, Any] = {"local": dict(local_t)}
    try:
        from .cloud_api_state import provider_reasoning_truth_snapshot

        prov = _cloud_truth if _cloud_truth is not None else provider_reasoning_truth_snapshot()
    except Exception:
        prov = {}
    for k in ("openai", "openrouter", "anthropic"):
        e = prov.get(k)
        if isinstance(e, dict):
            out[k] = dict(e)
        else:
            out[k] = {
                "configured": False,
                "routable": False,
                "usable": False,
                "autonomy_safe": False,
                "blocked_reason": "not_configured",
            }
    return out


def reasoning_provider_autonomy_safe_label(cap: Optional[Dict[str, Any]] = None) -> str:
    """First provider in the same priority order as reasoning_capability_sufficient_for_normal_autonomy."""
    cap = reasoning_provider_capability_snapshot() if cap is None else cap
    if (cap.get("local") or {}).get("autonomy_safe"):
        return "local"
    for k in ("openrouter", "openai", "anthropic"):
        if (cap.get(k) or {}).get("autonomy_safe"):
            return k
    return "none"


_last_autonomy_route_log_key: str = ""
_last_autonomy_route_log_ts: float = 0.0


def log_autonomy_reasoning_route_constrained(
    *,
    selected: str,
    safe_required: bool,
    block_reason: Optional[str] = None,
    router_was: Optional[str] = None,
) -> None:
    """Compact log when autonomy-originated routing is constrained (throttled on identical key)."""
    global _last_autonomy_route_log_key, _last_autonomy_route_log_ts
    if not safe_required:
        return
    key = f"{selected}|{router_was or ''}|{block_reason or ''}"
    now = time.time()
    if key == _last_autonomy_route_log_key and now - _last_autonomy_route_log_ts < 45.0:
        return
    _last_autonomy_route_log_key = key
    _last_autonomy_route_log_ts = now
    if block_reason:
        logger.info(
            "[AutonomyRoute] selected=%s safe_required=yes reason=%s",
            (selected or "")[:24],
            (block_reason or "")[:48],
        )
    elif router_was and str(router_was) != str(selected):
        logger.info(
            "[AutonomyRoute] selected=%s safe_required=yes router_was=%s",
            (selected or "")[:24],
            (str(router_was) or "")[:24],
        )


def select_autonomy_safe_reasoning_route(cap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Autonomy-safe reasoning provider label + availability (no API I/O)."""
    cap = reasoning_provider_capability_snapshot() if cap is None else cap
    lbl = reasoning_provider_autonomy_safe_label(cap)
    if lbl == "none":
        return {"provider": "none", "available": False, "block_reason": "no_safe_provider"}
    return {"provider": lbl, "available": True, "block_reason": None}


def autonomy_safe_reasoning_available(cap: Optional[Dict[str, Any]] = None) -> bool:
    return bool(select_autonomy_safe_reasoning_route(cap)["available"])


def autonomy_safe_cloud_backend_order(cap: Optional[Dict[str, Any]] = None) -> List[str]:
    """openrouter / openai backends that are autonomy_safe (OpenRouter preferred)."""
    cap = reasoning_provider_capability_snapshot() if cap is None else cap
    out: List[str] = []
    if (cap.get("openrouter") or {}).get("autonomy_safe"):
        out.append("openrouter")
    if (cap.get("openai") or {}).get("autonomy_safe"):
        out.append("openai")
    return out


def clamp_api_router_choice_to_autonomy_safe(
    chosen: Optional[str],
    reason: str,
    *,
    router_chosen: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Map select_best_api ``chosen`` to an autonomy-safe provider for reasoning tasks.
    When no autonomy-safe path exists, forces local_mistral (caller/planner gates handle health).
    """
    route = select_autonomy_safe_reasoning_route()
    rw = str(router_chosen if router_chosen is not None else (chosen or ""))

    if not route["available"]:
        if rw not in ("local_mistral", "local", "", "none"):
            log_autonomy_reasoning_route_constrained(
                selected="local_mistral",
                safe_required=True,
                block_reason="no_safe_provider",
                router_was=rw or None,
            )
        return "local_mistral", reason

    safe_lbl = str(route["provider"])
    safe_chosen = "local_mistral" if safe_lbl == "local" else safe_lbl
    ch = chosen or "local_mistral"
    cur_norm = "local" if ch == "local_mistral" else ch
    if cur_norm == safe_lbl:
        return ch, reason
    log_autonomy_reasoning_route_constrained(
        selected=safe_chosen,
        safe_required=True,
        block_reason=None,
        router_was=rw or None,
    )
    return safe_chosen, reason


def reasoning_capability_sufficient_for_normal_autonomy(cap: Optional[Dict[str, Any]] = None) -> bool:
    """
    True if at least one trustworthy reasoning path exists (local staged inference OK, or cloud route
    actually usable — not merely configured). Uses reasoning_provider_capability_snapshot() as the
    single autonomy_safe source of truth.
    """
    try:
        snap = reasoning_provider_capability_snapshot() if cap is None else cap
    except Exception:
        return False
    for k in ("local", "openrouter", "openai", "anthropic"):
        if (snap.get(k) or {}).get("autonomy_safe"):
            return True
    return False


def cloud_reasoning_degraded_flag() -> bool:
    """Any loaded OpenAI key that is currently unusable for routing (quota / cooldown / policy)."""
    try:
        from .cloud_api_state import openai_key_loaded, openai_usable_for_routing

        if not openai_key_loaded():
            return False
        return not openai_usable_for_routing()
    except Exception:
        return False


def reasoning_provider_ready_flag(cap: Optional[Dict[str, Any]] = None) -> bool:
    """Shorthand: at least one cloud or local reasoning path is ready."""
    return reasoning_capability_sufficient_for_normal_autonomy(cap)


def restricted_safe_startup_mode(cap: Optional[Dict[str, Any]] = None) -> bool:
    """
    True when no reasoning/planner path is trustworthy enough for normal autonomy.
    Uses capability signals (local staged inference + cloud keys), not OpenAI-only heuristics.
    """
    if reasoning_capability_sufficient_for_normal_autonomy(cap):
        return False
    return True


def restricted_safe_autonomy_candidate_ok(candidate: Dict[str, Any]) -> bool:
    """Predicate for autonomy candidates allowed under restricted-safe pool."""
    act = str((candidate or {}).get("action") or "")
    if act in RESTRICTED_SAFE_AUTONOMY_ACTIONS:
        return True
    if act == "execute_self_task":
        md = (candidate or {}).get("metadata") if isinstance((candidate or {}).get("metadata"), dict) else {}
        arch = str(md.get("archetype") or md.get("self_task_archetype") or "")
        return is_subsystem_repair_or_diagnostic_archetype(arch)
    return False


def _planner_startup_max_wait_sec() -> float:
    try:
        return max(4.0, float(os.environ.get("ELYSIA_PLANNER_STARTUP_MAX_WAIT_SEC", "28")))
    except ValueError:
        return 28.0


def _planner_startup_retry_interval_sec() -> float:
    try:
        return max(1.0, float(os.environ.get("ELYSIA_PLANNER_STARTUP_RETRY_INTERVAL_SEC", "3")))
    except ValueError:
        return 3.0


def planner_startup_require_inference() -> bool:
    v = (os.environ.get("ELYSIA_PLANNER_STARTUP_REQUIRE_INFERENCE") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def run_staged_planner_startup_inference(base: str, canon: str) -> Tuple[bool, str]:
    """
    Bounded retries: lightweight /api/chat ping until success or max wait.
    Sets _planner_inference_ok (caller sets runtime_alive + model_available on disk).
    """
    global _planner_inference_ok
    from .ollama_health import planner_lightweight_inference_probe

    max_wait = _planner_startup_max_wait_sec()
    interval = _planner_startup_retry_interval_sec()
    require = planner_startup_require_inference()
    t0 = time.time()
    last_detail = "no_attempt"
    _planner_inference_ok = False
    if not require:
        _planner_inference_ok = True
        return True, "inference_not_required"
    while time.time() - t0 < max_wait:
        elapsed = time.time() - t0
        to = min(8.0, max(2.0, max_wait - elapsed))
        ok, det = planner_lightweight_inference_probe(base, canon, timeout=to)
        last_detail = det
        if ok:
            _planner_inference_ok = True
            logger.info(
                "[StartupGate] staged_inference ok after %.1fs detail=%s",
                time.time() - t0,
                det[:80],
            )
            return True, det
        if time.time() - t0 + interval >= max_wait:
            break
        time.sleep(interval)
    _planner_inference_ok = False
    return False, last_detail


def _yn(v: Any) -> str:
    return "yes" if v else "no"


def _br(v: Any) -> str:
    s = (str(v) if v is not None else "") or "none"
    return s[:28] if len(s) > 28 else s


def format_runtime_decision_snapshot_line(status: Dict[str, Any]) -> str:
    """Single-line causal snapshot for operator logs."""
    parts = [
        f"planner_ready={'yes' if status.get('planner_readiness') == 'ready' else 'no'}",
        f"local_cfg={_yn(status.get('local_configured'))}",
        f"local_route={_yn(status.get('local_routable'))}",
        f"local_use={_yn(status.get('local_usable'))}",
        f"local_br={_br(status.get('local_block_reason'))}",
        f"runtime_alive={_yn(status.get('runtime_alive'))}",
        f"planner_model_available={_yn(status.get('planner_model_available'))}",
        f"planner_inference_ok={_yn(status.get('planner_inference_ok'))}",
        f"oa_cfg={_yn(status.get('openai_configured'))}",
        f"oa_route={_yn(status.get('openai_routable'))}",
        f"oa_use={_yn(status.get('openai_usable'))}",
        f"oa_br={_br(status.get('openai_block_reason'))}",
        f"or_cfg={_yn(status.get('openrouter_configured'))}",
        f"or_route={_yn(status.get('openrouter_routable'))}",
        f"or_use={_yn(status.get('openrouter_usable'))}",
        f"or_br={_br(status.get('openrouter_block_reason'))}",
        f"an_cfg={_yn(status.get('anthropic_configured'))}",
        f"an_route={_yn(status.get('anthropic_routable'))}",
        f"an_use={_yn(status.get('anthropic_usable'))}",
        f"an_br={_br(status.get('anthropic_block_reason'))}",
        f"reasoning_sel={status.get('reasoning_provider_selected') or 'n/a'}",
        f"reasoning_safe={status.get('reasoning_provider_autonomy_safe') or 'none'}",
        f"reasoning_cap_ok={_yn(status.get('reasoning_cap_ok'))}",
        f"reasoning_ready={_yn(status.get('reasoning_provider_ready'))}",
        f"openai_reasoning_blocked={_yn(status.get('openai_reasoning_blocked'))}",
        f"restricted_safe={_yn(status.get('restricted_safe_startup'))}",
        f"monetization_ready={_yn(status.get('monetization_subsystems_ready'))}",
        f"blocked_actions={status.get('blocked_actions_summary') or '-'}",
    ]
    return "[RuntimeDecision] " + " ".join(parts)


def build_runtime_decision_status_dict(guardian: Optional[Any] = None) -> Dict[str, Any]:
    """Merge staged planner + capability + monetization for dashboards / log line."""
    lbl = compute_readiness_label()
    try:
        from .openai_degraded import openai_insufficient_quota_reasoning_blocked

        oa_blk = bool(openai_insufficient_quota_reasoning_blocked())
    except Exception:
        oa_blk = False

    local_t = local_planner_reasoning_truth_snapshot()
    try:
        from .cloud_api_state import provider_reasoning_truth_snapshot

        truth = provider_reasoning_truth_snapshot()
    except Exception:
        truth = {}
    cap_snap = reasoning_provider_capability_snapshot(
        _cloud_truth=truth if isinstance(truth, dict) else None,
    )
    oa = truth.get("openai") if isinstance(truth.get("openai"), dict) else {}
    or_ = truth.get("openrouter") if isinstance(truth.get("openrouter"), dict) else {}
    an = truth.get("anthropic") if isinstance(truth.get("anthropic"), dict) else {}

    try:
        from .multi_api_router import reasoning_provider_label_from_api_router

        rp = reasoning_provider_label_from_api_router(registry=None)
    except Exception:
        rp = "local"

    _loc = cap_snap.get("local") if isinstance(cap_snap.get("local"), dict) else {}
    mon = False
    if guardian is not None:
        try:
            mon, _ = monetization_subsystems_ready(guardian)
        except Exception:
            pass
    blocked: List[str] = []
    if not local_planner_provider_ready():
        blocked.append("local_planner")
    if not mon:
        blocked.append("monetization_subsystems")
    if oa_blk:
        blocked.append("openai_quota")
    return {
        "planner_readiness": lbl,
        "runtime_alive": staged_runtime_alive(),
        "planner_model_available": staged_planner_model_available(),
        "planner_inference_ok": staged_planner_inference_ok(),
        "local_configured": bool(local_t.get("configured")),
        "local_routable": bool(local_t.get("routable")),
        "local_usable": bool(local_t.get("usable")),
        "local_block_reason": local_t.get("blocked_reason"),
        "openai_configured": bool(oa.get("configured")),
        "openai_routable": bool(oa.get("routable")),
        "openai_usable": bool(oa.get("usable")),
        "openai_block_reason": oa.get("blocked_reason"),
        "openrouter_configured": bool(or_.get("configured")),
        "openrouter_routable": bool(or_.get("routable")),
        "openrouter_usable": bool(or_.get("usable")),
        "openrouter_block_reason": or_.get("blocked_reason"),
        "anthropic_configured": bool(an.get("configured")),
        "anthropic_routable": bool(an.get("routable")),
        "anthropic_usable": bool(an.get("usable")),
        "anthropic_block_reason": an.get("blocked_reason"),
        "local_autonomy_safe": bool(_loc.get("autonomy_safe")),
        "openai_autonomy_safe": bool((cap_snap.get("openai") or {}).get("autonomy_safe")),
        "openrouter_autonomy_safe": bool((cap_snap.get("openrouter") or {}).get("autonomy_safe")),
        "anthropic_autonomy_safe": bool((cap_snap.get("anthropic") or {}).get("autonomy_safe")),
        "reasoning_provider_ready": reasoning_provider_ready_flag(cap_snap),
        "reasoning_cap_ok": bool(reasoning_capability_sufficient_for_normal_autonomy(cap_snap)),
        # Matches multi_api_router.select_best_api("reasoning", …) / reasoning_provider_label_from_api_router
        "reasoning_provider_selected": rp,
        "reasoning_provider_autonomy_safe": reasoning_provider_autonomy_safe_label(cap_snap),
        "openai_reasoning_blocked": oa_blk,
        "restricted_safe_startup": restricted_safe_startup_mode(cap_snap),
        "monetization_subsystems_ready": mon,
        "blocked_actions_summary": ",".join(blocked) if blocked else "-",
        "cloud_reasoning_degraded": cloud_reasoning_degraded_flag(),
    }


def log_runtime_decision_snapshot_throttled(guardian: Optional[Any] = None) -> None:
    global _last_runtime_snapshot_log_ts
    now = time.time()
    if now - _last_runtime_snapshot_log_ts < 52.0:
        return
    _last_runtime_snapshot_log_ts = now
    try:
        d = build_runtime_decision_status_dict(guardian)
        logger.info("%s", format_runtime_decision_snapshot_line(d))
    except Exception as e:
        logger.debug("runtime snapshot log: %s", e)


def startup_antithrash_priority_factor(
    action: str,
    *,
    decision_cycle: int,
    recent_actions: Optional[List[str]] = None,
) -> float:
    """First N Mistral cycles: penalize rapid repeats of known low-yield startup actions."""
    if decision_cycle > _antithrash_max_cycle():
        return 1.0
    act = (action or "").strip()
    if act not in STARTUP_ANTITHRASH_ACTIONS:
        return 1.0
    tail = [str(x) for x in (recent_actions or []) if x][-4:]
    if len(tail) >= 2 and tail[-1] == act and tail[-2] == act:
        return 0.09
    if tail.count(act) >= 2:
        return 0.12
    return 1.0


def filter_monetization_pending_tasks(
    tasks: List[Dict[str, Any]],
    guardian: Any,
    *,
    log_skip: bool = True,
) -> List[Dict[str, Any]]:
    """
    Drop revenue/monetization *execution* self-tasks until subsystems are ready.
    Always retain bounded repair/diagnostic archetypes (explicit whitelist).
    """
    if not tasks:
        return tasks
    try:
        restricted = restricted_safe_startup_mode()
        ok, detail = monetization_subsystems_ready(guardian)
        out: List[Dict[str, Any]] = []
        dropped = 0
        for t in tasks:
            arch = str(t.get("archetype") or "")
            if is_subsystem_repair_or_diagnostic_archetype(arch):
                out.append(t)
                continue
            if is_revenue_monetization_archetype(arch):
                if ok and not restricted:
                    out.append(t)
                else:
                    dropped += 1
                continue
            out.append(t)
        if log_skip and dropped:
            logger.info(
                "[AutonomyGate] monetization_pending_filtered dropped=%d reason=%s income_generator=%s wallet=%s financial_manager=%s",
                dropped,
                "restricted_safe_startup" if restricted else "subsystem_not_ready",
                detail.get("income_generator"),
                detail.get("wallet"),
                detail.get("financial_manager"),
            )
        return out
    except Exception as e:
        logger.debug("filter_monetization_pending_tasks: %s", e)
        return tasks


def log_startup_provider_autonomy_gates_throttled(
    guardian: Optional[Any],
    *,
    decision_cycle: int,
    planner_ready: bool,
    ollama_passes: int,
) -> None:
    """One bundled line for dashboards (throttled)."""
    global _last_gate_bundle_log_ts
    now = time.time()
    if now - _last_gate_bundle_log_ts < 52.0:
        return
    _last_gate_bundle_log_ts = now
    try:
        from .cloud_api_state import (
            openai_usable_for_routing,
            openrouter_usable_for_reasoning,
        )
        from .openai_degraded import openai_insufficient_quota_reasoning_blocked

        oa_blk = bool(openai_insufficient_quota_reasoning_blocked())
        or_ready = bool(openrouter_usable_for_reasoning())
        oa_use = bool(openai_usable_for_routing())
    except Exception:
        oa_blk, or_ready, oa_use = False, False, False
    sub = {"income_generator": False, "wallet": False, "financial_manager": False}
    mon_ok = False
    if guardian is not None:
        try:
            mon_ok, sub = monetization_subsystems_ready(guardian)
        except Exception:
            pass
    rs = restricted_safe_startup_mode()
    logger.info(
        "[StartupGate] ollama_consecutive_passes=%s planner_ready=%s",
        ollama_passes,
        planner_ready,
    )
    logger.info(
        "[ProviderGate] openai_reasoning_blocked=%s openrouter_usable=%s openai_usable_for_routing=%s",
        oa_blk,
        or_ready,
        oa_use,
    )
    logger.info(
        "[SubsystemReady] income_generator=%s wallet=%s financial_manager=%s monetization_bundle_ok=%s",
        sub.get("income_generator"),
        sub.get("wallet"),
        sub.get("financial_manager"),
        mon_ok,
    )
    if rs:
        logger.info("[DegradedMode] mode=restricted_safe_startup (throttled bundle)")
    try:
        log_runtime_decision_snapshot_throttled(guardian)
    except Exception:
        pass


def autonomy_gate_log(action: str, allowed: bool, reason: str) -> None:
    logger.info("[AutonomyGate] action=%s allowed=%s reason=%s", (action or "")[:80], allowed, (reason or "")[:200])


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


def resolve_installed_ollama_tag(
    canonical: str,
    pool: List[str],
    installed_tags: List[str],
) -> Optional[str]:
    """
    When the configured canonical tag is not installed, pick a usable substitute:

    1. First ``ollama_model_pool`` entry that exists exactly on the host (operator preference).
    2. Else same-base variants of ``canonical`` (see :func:`suggest_close_ollama_tags`): prefer a
       sole ``:latest``, otherwise lexicographic order for stability.

    Returns ``None`` if no substitute is found (caller keeps failing canonical).
    """
    inst_set = {(t or "").strip() for t in installed_tags if (t or "").strip()}
    can = (canonical or "").strip()
    if can and can in inst_set:
        return None
    for p in pool:
        pt = (p or "").strip()
        if pt and pt in inst_set:
            return pt
    suggest = suggest_close_ollama_tags(can, installed_tags)
    if not suggest:
        return None
    if len(suggest) == 1:
        return suggest[0]
    latest = [s for s in suggest if s.endswith(":latest")]
    if len(latest) == 1:
        return latest[0]
    if len(latest) > 1:
        return sorted(latest)[0]
    return sorted(suggest)[0]


def equivalent_autonomy_action_key(action: str) -> str:
    """Collapse alternate action surfaces that produce the same operational outcome."""
    act = (action or "").strip()
    low = act.lower()
    if low in (
        "use_capability/module/harvest_engine",
        "use_capability/module/harvestengine",
        "use_capability/tool/harvest_engine",
        "use_capability/tool/harvestengine",
    ):
        return "harvest_income_report"
    return act


def _autonomy_noop_streak_need(action_key: str) -> int:
    """Harvest no-ops can hit cooldown sooner (env-tunable); other actions use default."""
    key = equivalent_autonomy_action_key(action_key)
    if key == "harvest_income_report":
        try:
            return max(1, int(os.environ.get("ELYSIA_HARVEST_ZERO_AUTONOMY_NOOP_NEED", "1")))
        except ValueError:
            return 1
    if key == "process_queue":
        try:
            return max(2, int(os.environ.get("ELYSIA_PROCESS_QUEUE_AUTONOMY_NOOP_NEED", "2")))
        except ValueError:
            return 2
    if key == "income_modules_pulse":
        try:
            return max(2, int(os.environ.get("ELYSIA_INCOME_PULSE_AUTONOMY_NOOP_NEED", "2")))
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
    act = equivalent_autonomy_action_key(action)
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
    key = equivalent_autonomy_action_key(action_key)
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
    key = equivalent_autonomy_action_key(action_key)
    if not key:
        return
    with _lock:
        _autonomy_noop_streak.pop(key, None)
        _autonomy_noop_suppress_until.pop(key, None)


def autonomy_noop_suppression_factor(action: str) -> float:
    """Strong downrank (×0.06) while action is in no-op suppression cooldown."""
    now = time.time()
    act = equivalent_autonomy_action_key(action)
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
    suppressed_keys = {
        equivalent_autonomy_action_key(str(c.get("action") or ""))
        for c in candidates
        if autonomy_noop_suppression_factor(str(c.get("action") or "")) < 1.0
    }
    if not suppressed_keys:
        return
    ex_set = set(exploratory_actions or [])
    for c in candidates:
        act = str(c.get("action") or "")
        eq_act = equivalent_autonomy_action_key(act)
        if eq_act in AUTONOMY_NOOP_TRACKED_ACTIONS and eq_act in suppressed_keys:
            continue
        if act == "execute_self_task":
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 4.0
            c["_noop_alt_boost"] = True
        elif act == "question_probe":
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 3.2
            c["_noop_alt_boost"] = True
        elif act.startswith("use_capability/"):
            if eq_act in suppressed_keys:
                continue
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 2.8
            c["_noop_alt_boost"] = True
        elif act in ex_set:
            c["priority_score"] = float(c.get("priority_score", 0) or 0) + 1.25
            c["_noop_alt_boost"] = True


def degraded_autonomy_suppression_factor(action: str) -> float:
    """Strong downrank when action is in cooldown after repeated low-value degraded runs."""
    now = time.time()
    act = equivalent_autonomy_action_key(action)
    if not act:
        return 1.0
    if float(_degraded_suppress_until.get(act, 0) or 0) > now:
        return 0.12
    return 1.0


def record_degraded_low_value_signal(action_key: str, *, reason: str) -> None:
    """Increment streak; after N identical low-value signals, cooldown suppresses this action key."""
    global _degraded_low_streak, _degraded_suppress_until
    now = time.time()
    key = equivalent_autonomy_action_key(action_key)
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
    key = equivalent_autonomy_action_key(action_key)
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
    Sync startup: list Ollama tags, verify canonical model is installed, then **staged** readiness:
    ``runtime_alive`` (tags), ``planner_model_available`` (exact tag), bounded lightweight
    ``/api/chat`` inference retries (``planner_inference_ok``), optional legacy second light probe
    when ``ELYSIA_PLANNER_STARTUP_STABILIZATION`` is enabled.
    """
    global _canonical_model, _ollama_reachable, _model_installed, _installed_names
    global _startup_health_ok, _startup_detail, _last_tag_recheck_ts
    global _planner_boot_probe_complete, _ollama_startup_probe_passes
    global _runtime_alive, _planner_model_available, _planner_inference_ok

    from .ollama_health import list_ollama_installed_model_names, normalize_ollama_base
    from .ollama_model_config import get_canonical_ollama_model, get_ollama_model_pool, set_effective_ollama_model_from_planner

    try:
        canon = get_canonical_ollama_model(log_once=False)
        base = normalize_ollama_base(None)
        names, err = list_ollama_installed_model_names(base_url=base)
        now = time.time()
        _last_tag_recheck_ts = now

        env_ollama = bool((os.environ.get("ELYSIA_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL") or "").strip())
        pool = get_ollama_model_pool()
        suggest = suggest_close_ollama_tags(canon, names)
        exact = exact_ollama_tag_installed(canon, names)
        resolved: Optional[str] = None
        if not exact and not env_ollama:
            resolved = resolve_installed_ollama_tag(canon, pool, names)
        if resolved:
            set_effective_ollama_model_from_planner(resolved)
            canon = get_canonical_ollama_model(log_once=False)
            exact = exact_ollama_tag_installed(canon, names)
            logger.info(
                "[Guardian] Resolved Ollama missing canonical to installed tag: %s (pool/suggest; had %d close matches)",
                canon,
                len(suggest),
            )

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
                _runtime_alive = False
                _planner_model_available = False
                _planner_inference_ok = False
            logger.error("[PlannerReadiness] Ollama unreachable (tags): %s", err)
            return snapshot_startup_dict()

        if not _model_installed:
            with _lock:
                _startup_health_ok = False
                _startup_detail = "canonical_model_not_in_ollama_tags"
                _runtime_alive = err is None
                _planner_model_available = False
                _planner_inference_ok = False
            if log_tags_on_fail and names:
                logger.error(
                    "[PlannerReadiness] Canonical model %r not installed; Ollama has: %s",
                    canon,
                    ", ".join(names[:24]) + (" …" if len(names) > 24 else ""),
                )
            elif log_tags_on_fail:
                logger.error("[PlannerReadiness] Canonical model %r not installed; Ollama reports no models", canon)
            return snapshot_startup_dict()

        with _lock:
            _runtime_alive = err is None
            _planner_model_available = bool(exact)

        from .ollama_health import planner_lightweight_inference_probe

        _ollama_startup_probe_passes = 0
        staged_ok, staged_det = run_staged_planner_startup_inference(base, canon)
        if planner_startup_require_inference() and not staged_ok:
            with _lock:
                _startup_health_ok = False
                _startup_detail = (staged_det or "staged_inference_fail")[:300]
                _planner_inference_ok = False
            logger.error("[PlannerReadiness] staged planner inference did not succeed: %s", _startup_detail)
            return snapshot_startup_dict()

        with _lock:
            _startup_health_ok = True
            _startup_detail = (staged_det or "staged_ok")[:300]

        if planner_startup_stabilization_required():
            gap = _stabilization_gap_sec()
            logger.info(
                "[StartupGate] staged_inference_ok running_second_light_probe gap_sec=%.1f",
                gap,
            )
            time.sleep(gap)
            ok2, det2 = planner_lightweight_inference_probe(base, canon, timeout=min(10.0, 8.0 + gap))
            with _lock:
                _startup_health_ok = bool(ok2)
                _startup_detail = (det2 if ok2 else (det2 or "stabilization_second_probe_fail"))[:300]
                if ok2:
                    _planner_inference_ok = True
            if not ok2:
                _ollama_startup_probe_passes = 1
                logger.error(
                    "[PlannerReadiness] Ollama stabilization second light probe failed: %s",
                    _startup_detail,
                )
            else:
                _ollama_startup_probe_passes = 2
                logger.info(
                    "[StartupGate] ollama_consecutive_passes=2 planner_ready=%s",
                    _startup_health_ok,
                )
        else:
            _ollama_startup_probe_passes = 1 if staged_ok else 0
            logger.info(
                "[StartupGate] ollama_consecutive_passes=%s planner_ready=%s (stabilization_disabled)",
                _ollama_startup_probe_passes,
                _startup_health_ok,
            )

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
    from .ollama_model_config import get_canonical_ollama_model, get_ollama_model_pool, set_effective_ollama_model_from_planner

    canon = get_canonical_ollama_model(log_once=False)
    base = normalize_ollama_base(None)
    names, err = list_ollama_installed_model_names(base_url=base)
    need_health = False
    model_ok = False
    if err is None:
        env_ollama = bool((os.environ.get("ELYSIA_OLLAMA_MODEL") or os.environ.get("OLLAMA_MODEL") or "").strip())
        if not exact_ollama_tag_installed(canon, names) and not env_ollama:
            resolved = resolve_installed_ollama_tag(canon, get_ollama_model_pool(), names)
            if resolved:
                set_effective_ollama_model_from_planner(resolved)
                canon = get_canonical_ollama_model(log_once=False)
        model_ok = exact_ollama_tag_installed(canon, names)
    with _lock:
        _last_tag_recheck_ts = now
        _installed_names = list(names)
        _ollama_reachable = err is None
        if err is None:
            _model_installed = model_ok
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
            else:
                _planner_inference_ok = True
                _runtime_alive = True


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
    with _lock:
        ra = _runtime_alive
        pma = _planner_model_available
        pio = _planner_inference_ok
    return {
        "canonical_ollama_model": canon,
        "ollama_reachable": reach,
        "exact_tag_match": exact,
        "model_installed": inst,
        "installed_model_tags": tags_full[:32],
        "suggested_close_tags": suggest,
        "startup_health_ok": health,
        "startup_detail": detail,
        "runtime_alive": ra,
        "planner_model_available": pma,
        "planner_inference_ok": pio,
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


def _autonomy_routine_info_forced_when_ready() -> bool:
    """
    If set, routine autonomy/idle/exploration lines stay at INFO even when planner readiness is ``ready``.

    ``ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY`` is the preferred name; ``ELYSIA_EXPLORATION_INFO_WHEN_READY``
    is kept for backward compatibility (same effect).
    """
    for _key in (
        "ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY",
        "ELYSIA_EXPLORATION_INFO_WHEN_READY",
    ):
        try:
            v = (os.environ.get(_key) or "").strip().lower()
            if v in ("1", "true", "yes", "always", "force"):
                return True
        except Exception:
            pass
    return False


def autonomy_exploration_log_use_debug() -> bool:
    """
    When planner readiness is ``ready``, routine autonomy chatter (``[Exploration]``, ``[Autonomy]``, ``[Idle]``, etc.)
    logs at DEBUG instead of INFO.

    Set ``ELYSIA_AUTONOMY_ROUTINE_INFO_WHEN_READY=1`` (preferred) or ``ELYSIA_EXPLORATION_INFO_WHEN_READY=1``
    to keep INFO level even when ready (operator troubleshooting).
    """
    if _autonomy_routine_info_forced_when_ready():
        return False
    try:
        return compute_readiness_label() == "ready"
    except Exception:
        return False


# Preferred public name (same behavior as :func:`autonomy_exploration_log_use_debug`).
autonomy_routine_log_use_debug = autonomy_exploration_log_use_debug


def log_autonomy_routine(
    log: logging.Logger, fmt: str, *args: Any, **kwargs: Any
) -> None:
    """Routine autonomy chatter: INFO normally; DEBUG when planner readiness is ``ready``."""
    lvl = logging.DEBUG if autonomy_exploration_log_use_debug() else logging.INFO
    log.log(lvl, fmt, *args, **kwargs)


def log_autonomy_exploration_routine(
    log: logging.Logger, fmt: str, *args: Any, **kwargs: Any
) -> None:
    """Same as :func:`log_autonomy_routine` (``[Exploration]`` prefix convention)."""
    log_autonomy_routine(log, fmt, *args, **kwargs)


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
    if restricted_safe_startup_mode():
        global _last_restricted_safe_log_ts
        _now_rs = time.time()
        if _now_rs - _last_restricted_safe_log_ts >= 75.0:
            _last_restricted_safe_log_ts = _now_rs
            logger.warning("[DegradedMode] mode=restricted_safe_startup")
        return False, "restricted_safe_startup", "degraded_autonomy"
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
    if restricted_safe_startup_mode():
        pool = [
            c
            for c in candidates
            if restricted_safe_autonomy_candidate_ok(c) and str(c.get("action") or "") in DEGRADED_AUTONOMY_ACTIONS
        ]
    else:
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
        "planner_startup_stabilization_required": planner_startup_stabilization_required(),
        "ollama_startup_probe_passes": int(_ollama_startup_probe_passes),
        "restricted_safe_startup": restricted_safe_startup_mode(),
        "runtime_decision": build_runtime_decision_status_dict(_guardian_ref_for_gates()),
    }


def planner_context_for_snapshot(decision_cycle: int) -> Dict[str, Any]:
    """Small blob for Mistral guardian_state / metadata."""
    refresh_readiness_log_transition()
    gate_ok, reason, mode = autonomy_planner_gate(decision_cycle)
    lbl = compute_readiness_label()
    try:
        log_startup_provider_autonomy_gates_throttled(
            _guardian_ref_for_gates(),
            decision_cycle=decision_cycle,
            planner_ready=(lbl == "ready" and gate_ok),
            ollama_passes=_ollama_startup_probe_passes,
        )
    except Exception:
        pass
    return {
        "planner_readiness": lbl,
        "autonomy_planner_mode": mode,
        "planner_gate_allow_mistral": gate_ok,
        "planner_gate_reason": reason,
        "latency": recent_planner_latency_summary(),
    }


_guardian_gate_ref: Any = None


def bind_guardian_for_startup_gates(core: Any) -> None:
    """Optional weak ref for [SubsystemReady] logging (set from GuardianCore)."""
    global _guardian_gate_ref
    _guardian_gate_ref = core


def _guardian_ref_for_gates() -> Any:
    return _guardian_gate_ref
