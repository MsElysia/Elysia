# project_guardian/self_task_cycle_priority.py
# Verify whether the chosen self-task was the best available use of the cycle.

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _task_tier_class(archetype: str, task: Dict[str, Any]) -> int:
    """Higher = higher governance priority (Phase 5 ordering proxy)."""
    a = (archetype or "").lower()
    v = str(task.get("value_tier") or "")
    tk = str(task.get("task_kind") or "")
    if "execute_best" in a or "generate_execution_plan" in a or ("rank_top" in a and "opportunit" in a):
        return 4
    if v == "high" or tk in ("generation", "execution"):
        return 3
    if "repair" in a or "validate_tool" in a or "diagnostic" in a or "idle_pulse" in a:
        return 2
    return 1


def _governance_score(row: Dict[str, Any]) -> float:
    cls = float(row.get("tier_class") or 1)
    score = 12.0 * cls
    if row.get("obj_execution_ready"):
        score += 28.0
    if row.get("obj_operator_ready"):
        score += 14.0
    if str(row.get("value_tier") or "") == "high":
        score += 16.0
    ot = str(row.get("obj_type") or "").lower()
    if "maintenance" in ot or ot == "tooling":
        score -= 4.0
    return score


def build_cycle_selection_snapshot(
    pending_sorted: List[Dict[str, Any]],
    objective_store: Any,
    *,
    chosen_task_id: str,
    max_items: int = 12,
) -> List[Dict[str, Any]]:
    """Snapshot top queue candidates at selection time (Phase 2)."""
    out: List[Dict[str, Any]] = []
    for t in pending_sorted[: max(1, int(max_items))]:
        tid = t.get("task_id")
        arch = str(t.get("archetype") or "")
        oid = t.get("objective_id")
        o: Optional[Dict[str, Any]] = None
        if oid and objective_store is not None and hasattr(objective_store, "get"):
            o = objective_store.get(str(oid))
        out.append(
            {
                "task_id": tid,
                "archetype": arch,
                "priority": float(t.get("priority") or 0),
                "value_tier": t.get("value_tier"),
                "task_kind": t.get("task_kind"),
                "objective_id": oid,
                "obj_execution_ready": bool(o and o.get("execution_ready")),
                "obj_operator_ready": bool(o and o.get("operator_ready")),
                "obj_type": (o or {}).get("objective_type") if o else None,
                "tier_class": _task_tier_class(arch, t),
            }
        )
    return out


def evaluate_cycle_priority_choice(
    *,
    chosen_task_id: str,
    chosen_archetype: str,
    chosen_task: Dict[str, Any],
    snapshot: Optional[List[Dict[str, Any]]],
    value_verified: bool,
    objective_advanced: bool,
    execution_outcome: str,
) -> Dict[str, Any]:
    """
    Phase 1 fields. Uses frozen snapshot + completion hints (blocker/value).
    """
    exo = (execution_outcome or "none").lower()
    out: Dict[str, Any] = {
        "cycle_best_choice_verified": True,
        "cycle_choice_score": 1.0,
        "cycle_choice_reason": "no_snapshot",
        "cycle_opportunity_cost": "low",
        "higher_priority_task_skipped": False,
    }
    if not snapshot:
        return out

    chosen_row = next((r for r in snapshot if r.get("task_id") == chosen_task_id), None)
    if not chosen_row:
        out["cycle_best_choice_verified"] = True
        out["cycle_choice_reason"] = "chosen_not_in_snapshot"
        return out

    chosen_g = _governance_score(chosen_row)
    others = [r for r in snapshot if r.get("task_id") != chosen_task_id]
    if not others:
        out["cycle_choice_score"] = 1.0
        out["cycle_choice_reason"] = "only_candidate"
        return out

    other_scores = [_governance_score(r) for r in others]
    max_other = max(other_scores)
    best_other_row = others[other_scores.index(max_other)]

    margin = chosen_g - max_other
    arch_l = (chosen_archetype or "").lower()
    maint_chosen = bool(
        "repair" in arch_l
        or "validate_tool" in arch_l
        or "diagnostic" in arch_l
        or "idle_pulse" in arch_l
        or str(chosen_task.get("task_kind") or "") in ("diagnostic", "monitoring")
    )
    high_tier_other = int(best_other_row.get("tier_class") or 0) >= 4
    exec_ready_other = bool(best_other_row.get("obj_execution_ready"))
    op_ready_other = bool(best_other_row.get("obj_operator_ready"))

    skipped_higher = bool(max_other > chosen_g + 4.0)
    out["higher_priority_task_skipped"] = skipped_higher

    # Phase 3: maintenance that removed blocker / created value is defensible
    if maint_chosen and value_verified and objective_advanced:
        out["cycle_best_choice_verified"] = True
        out["cycle_choice_score"] = 0.88
        out["cycle_choice_reason"] = "maintenance_unblocked_or_enabled_higher_value"
        out["cycle_opportunity_cost"] = "low"
        return out

    if margin >= -2.0:
        out["cycle_best_choice_verified"] = True
        out["cycle_choice_score"] = min(1.0, 0.72 + 0.06 * margin)
        out["cycle_choice_reason"] = "chosen_aligned_with_governance_tie"
        out["cycle_opportunity_cost"] = "low"
        return out

    if maint_chosen and (exec_ready_other or high_tier_other) and not value_verified:
        out["cycle_best_choice_verified"] = False
        out["cycle_choice_score"] = max(0.15, 0.45 + 0.02 * margin)
        out["cycle_choice_reason"] = "low_value_maintenance_while_exec_ready_work_queued"
        out["cycle_opportunity_cost"] = "high"
        return out

    if skipped_higher and op_ready_other and exo == "succeeded" and not value_verified:
        out["cycle_best_choice_verified"] = False
        out["cycle_choice_score"] = max(0.2, 0.5 + 0.015 * margin)
        out["cycle_choice_reason"] = "operator_ready_work_skipped_for_weak_run"
        out["cycle_opportunity_cost"] = "high"
        return out

    if margin < -12.0:
        out["cycle_best_choice_verified"] = False
        out["cycle_choice_score"] = max(0.1, 0.4 + 0.02 * margin)
        out["cycle_choice_reason"] = "clearly_stronger_queued_task_existed"
        out["cycle_opportunity_cost"] = "high"
        return out

    if margin < -5.0:
        out["cycle_best_choice_verified"] = value_verified
        out["cycle_choice_score"] = max(0.25, 0.55 + 0.02 * margin)
        out["cycle_choice_reason"] = "better_alternative_likely_available"
        out["cycle_opportunity_cost"] = "medium"
        return out

    out["cycle_best_choice_verified"] = bool(value_verified or margin >= -3.0)
    out["cycle_choice_score"] = max(0.35, 0.62 + 0.02 * margin)
    out["cycle_choice_reason"] = "marginal_tradeoff"
    out["cycle_opportunity_cost"] = "medium"
    return out
