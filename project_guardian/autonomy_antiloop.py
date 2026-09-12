# project_guardian/autonomy_antiloop.py
"""Generic anti-loop multipliers for autonomy candidate scoring (deterministic, tunable)."""
from __future__ import annotations

import logging
import os
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

logger = logging.getLogger(__name__)


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def autonomy_score_debug_enabled() -> bool:
    return (os.environ.get("ELYSIA_AUTONOMY_SCORE_DEBUG") or "").strip().lower() in ("1", "true", "yes")


def action_family(action: str) -> str:
    """Coarse bucket for novelty / loop detection (no external deps)."""
    a = (action or "").strip()
    if not a:
        return "empty"
    if a.startswith("use_capability/"):
        return "capability_use"
    if "harvest" in a or a in ("income_modules_pulse", "finance_idle_pulse"):
        return "income_ops"
    if "fractalmind" in a or "planning" in a:
        return "planning"
    if a == "execute_self_task":
        return "self_task"
    if a in ("execute_task", "process_queue", "work_on_objective"):
        return "work_queue"
    if a in ("tool_registry_pulse", "code_analysis", "question_probe"):
        return "maintenance"
    return "other"


def _fail_counts_map(guardian: Optional[Any]) -> Dict[str, int]:
    if guardian is None or not hasattr(guardian, "_antiloop_fail_counts"):
        return {}
    fc = getattr(guardian, "_antiloop_fail_counts", None)
    if not isinstance(fc, dict):
        return {}
    return {str(k): int(v) for k, v in fc.items() if int(v) > 0}


def _selector_churn_guard_multiplier(
    act: str,
    guardian: Optional[Any],
    recent_actions: Optional[List[str]],
    metadata: Optional[Dict[str, Any]],
) -> float:
    """
    Extra downrank for autonomy churners (monitoring seed task, stale queue probes, unchanged fractal).
    execute_self_task is never dampened here.
    """
    if act == "execute_self_task":
        return 1.0
    try:
        from . import planner_readiness as _pr
    except Exception:
        return 1.0
    if act == "execute_task":
        cand = {"action": "execute_task", "metadata": metadata if isinstance(metadata, dict) else {}}
        return float(_pr.execute_task_system_monitoring_priority_factor(cand, guardian, recent_actions))
    if act == "process_queue":
        return float(_pr.process_queue_stale_probe_priority_factor(guardian))
    if act == "fractalmind_planning":
        return float(_pr.fractalmind_planning_repeat_priority_factor(guardian, recent_actions))
    if act.startswith("use_capability/"):
        return float(_pr.income_generator_capability_stale_factor(guardian, act))
    return 1.0


def compute_antiloop_breakdown_for_action(
    action: str,
    base_score: float,
    *,
    decision_cycle: int,
    recent_actions: Optional[List[str]] = None,
    guardian: Optional[Any] = None,
    legacy_startup_antithrash_fn: Optional[Callable[..., float]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Deterministic penalty breakdown for one action (no mutation).
    final_score = base * product(penalties) * legacy (if any) * selector_churn.
    """
    act = str(action or "").strip()
    fam = action_family(act)
    tail = [str(x) for x in (recent_actions or []) if x][-8:]
    fam_tail = [action_family(x) for x in tail]
    tail_counts = Counter(tail)
    fam_counts = Counter(fam_tail)
    fail_counts = _fail_counts_map(guardian)

    rep_w = _f("ELYSIA_ANTILOOP_REPEAT_WEIGHT", 0.82)
    fam_w = _f("ELYSIA_ANTILOOP_FAMILY_WEIGHT", 0.88)
    fail_w = _f("ELYSIA_ANTILOOP_FAILURE_WEIGHT", 0.72)
    nosc_w = _f("ELYSIA_ANTILOOP_NOCHANGE_WEIGHT", 0.85)
    startup_cycles = _i("ELYSIA_ANTILOOP_STARTUP_CYCLES", 10)
    startup_extra = _f("ELYSIA_ANTILOOP_STARTUP_PENALTY_MULT", 0.9)
    in_startup = decision_cycle <= startup_cycles and startup_cycles > 0

    n_same = tail_counts.get(act, 0)
    repeat_pen = rep_w ** max(0, n_same - 1) if n_same >= 2 else 1.0
    n_fam = fam_counts.get(fam, 0)
    family_pen = fam_w ** max(0, n_fam - 2) if n_fam >= 3 else 1.0
    fails = fail_counts.get(act, 0)
    fail_pen = fail_w ** min(4, max(0, fails)) if fails > 0 else 1.0
    nosc_pen = nosc_w ** min(3, max(0, fails - 1)) if fails >= 2 else 1.0
    core_mult = repeat_pen * family_pen * fail_pen * nosc_pen
    startup_mult = 1.0
    if in_startup and core_mult < 1.0:
        startup_mult = startup_extra
    post_startup = core_mult * startup_mult

    legacy_mult = 1.0
    if legacy_startup_antithrash_fn is not None:
        try:
            legacy_mult = float(legacy_startup_antithrash_fn(act, decision_cycle=decision_cycle, recent_actions=tail))
        except Exception:
            legacy_mult = 1.0
    pre_churn = post_startup * legacy_mult
    selector_churn = _selector_churn_guard_multiplier(act, guardian, recent_actions, metadata)
    combined = pre_churn * selector_churn
    if selector_churn < 0.998 and act and act != "execute_self_task":
        logger.info(
            "[AutonomySelector] antiloop_churn_deprioritized action=%s churn_mult=%.4f "
            "pre_antiloop_churn_combined=%.5f final_combined=%.5f "
            "(system_monitoring|process_queue_stale|fractalmind_repeat|income_generator_capability)",
            act,
            selector_churn,
            pre_churn,
            combined,
        )

    base = float(base_score or 0.0)
    final = base * combined if base > 0 else 0.0
    return {
        "action": act,
        "base": round(base, 4),
        "repeat_penalty": round(repeat_pen, 4),
        "family_repeat_penalty": round(family_pen, 4),
        "recent_failure_penalty": round(fail_pen, 4),
        "no_state_change_penalty": round(nosc_pen, 4),
        "core_multiplier": round(core_mult, 6),
        "startup_penalty_mult": round(startup_mult, 4),
        "startup_window": bool(in_startup),
        "legacy_antithrash_mult": round(legacy_mult, 4),
        "pre_churn_combined": round(pre_churn, 6),
        "selector_churn": round(selector_churn, 6),
        "combined_multiplier": round(combined, 6),
        "final_score": round(final, 4),
    }


def format_antiloop_score_log_line(breakdown: Dict[str, Any]) -> str:
    """Single compact line for operators."""
    a = str(breakdown.get("action") or "")
    return (
        f"[AutonomyScore] action={a} base={breakdown.get('base')} repeat={breakdown.get('repeat_penalty')} "
        f"family={breakdown.get('family_repeat_penalty')} fail={breakdown.get('recent_failure_penalty')} "
        f"nochange={breakdown.get('no_state_change_penalty')} core={breakdown.get('core_multiplier')} "
        f"startup={breakdown.get('startup_penalty_mult')} legacy={breakdown.get('legacy_antithrash_mult')} "
        f"selector_churn={breakdown.get('selector_churn')} combined={breakdown.get('combined_multiplier')} "
        f"final={breakdown.get('final_score')}"
    )


def apply_autonomy_antiloop_factors(
    candidates: List[Dict[str, Any]],
    *,
    decision_cycle: int,
    recent_actions: Optional[List[str]] = None,
    guardian: Optional[Any] = None,
    legacy_startup_antithrash_fn=None,
) -> None:
    """Multiply priority_score in-place; attach full `_antiloop` breakdown per candidate."""
    if not candidates:
        return
    for c in candidates:
        act = str(c.get("action") or "")
        base = float(c.get("priority_score", 0) or 0)
        if base <= 0:
            continue
        meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        bd = compute_antiloop_breakdown_for_action(
            act,
            base,
            decision_cycle=decision_cycle,
            recent_actions=recent_actions,
            guardian=guardian,
            legacy_startup_antithrash_fn=legacy_startup_antithrash_fn,
            metadata=cast(Dict[str, Any], meta),
        )
        c["priority_score"] = float(bd.get("final_score", base))
        c["_antiloop"] = bd


def log_autonomy_antiloop_selection(best: Dict[str, Any], candidates: List[Dict[str, Any]]) -> None:
    """
    Log compact score line for the chosen action when breakdown exists and either debug is on
    or the action was actually penalized (avoids per-cycle noise when multipliers are all 1).
    In debug mode, also log a few most-penalized other candidates.
    """
    if not best:
        return
    act = str(best.get("action") or "")
    bd = best.get("_antiloop")
    dbg = autonomy_score_debug_enabled()
    if isinstance(bd, dict) and bd.get("action") == act:
        combined = float(bd.get("combined_multiplier") or 1.0)
        if dbg or combined < 0.999:
            logger.info("%s", format_antiloop_score_log_line(bd))
    if dbg and candidates:
        scored: List[Tuple[float, str, Dict[str, Any]]] = []
        for c in candidates[:24]:
            b = c.get("_antiloop")
            if isinstance(b, dict):
                scored.append((float(b.get("combined_multiplier", 1.0)), str(c.get("action") or ""), b))
        scored.sort(key=lambda x: x[0])
        for mult, _a, bdict in scored[:3]:
            if mult < 0.999:
                logger.info("[AutonomyScoreDebug] %s", format_antiloop_score_log_line(bdict))


def compute_selection_override(
    scored_action: str,
    final_best: Optional[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    """
    When post-scoring steps replace the winning candidate (e.g. self-task augment), return a compact
    record for logs and API payloads. Returns None if there was no prior scored action or no change.
    """
    s = (scored_action or "").strip()
    if not s or not final_best:
        return None
    to = str(final_best.get("action") or "").strip()
    if not to or s == to:
        return None
    src = str(final_best.get("source") or "")
    reason = "self_task_priority" if src == "self_tasking" else "post_scoring_replacement"
    return {"from": s, "to": to, "reason": reason}


def log_autonomy_pick_override(override: Dict[str, str]) -> None:
    logger.info(
        "[AutonomyPickOverride] scored=%s final=%s reason=%s",
        override.get("from"),
        override.get("to"),
        override.get("reason"),
    )


def record_autonomy_action_outcome_for_antiloop(guardian: Any, action: str, meaningful: bool) -> None:
    """Track per-action failure streaks for anti-loop (best-effort)."""
    if guardian is None or not action:
        return
    if not hasattr(guardian, "_antiloop_fail_counts"):
        guardian._antiloop_fail_counts = {}
    d: Dict[str, int] = guardian._antiloop_fail_counts
    key = str(action).strip()
    if not key:
        return
    if meaningful:
        d.pop(key, None)
    else:
        d[key] = int(d.get(key, 0) or 0) + 1
