# project_guardian/self_task_value_verification.py
# Post-execution: distinguish success from real value (delta vs mere activity).

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from .self_task_execution_outcome import is_execution_stage_archetype
from .self_task_output_contracts import normalize_payload

logger = logging.getLogger(__name__)


def _infer_value_type(archetype: str) -> str:
    a = (archetype or "").lower()
    if "revenue" in a or "execute_best" in a or "shortlist" in a:
        return "revenue"
    if "harvest" in a or "research" in a or "brief" in a:
        return "information"
    if "repair" in a or "registry" in a or "tool_registry" in a:
        return "capability"
    if "maintenance" in a or "diagnostic" in a or "idle_pulse" in a:
        return "maintenance"
    if "operator" in a or "learning_digest" in a:
        return "operator_support"
    if "improvement" in a or "synthes" in a or "artifact" in a:
        return "capability"
    return "none"


def evaluate_execution_value(
    *,
    archetype: str,
    adv_result: Dict[str, Any],
    exec_result: Dict[str, Any],
    artifact_path: Optional[Path],
    execution_tier: str,
    payload: Any,
) -> Dict[str, Any]:
    """
    value_verified requires measurable delta (Phase 3), not just execution success.
    """
    arch = (archetype or "").lower()
    out: Dict[str, Any] = {
        "value_verified": False,
        "value_score": 0.0,
        "value_reason": "not_applicable",
        "value_type": "none",
    }

    if not is_execution_stage_archetype(arch):
        out["value_reason"] = "not_execution_stage"
        out["value_type"] = _infer_value_type(arch)
        return out

    exo = str(exec_result.get("execution_outcome") or "none").lower()
    obj_adv = bool(adv_result.get("objective_advanced"))
    op_ready = bool(adv_result.get("operator_ready"))
    ex_ready = bool(adv_result.get("execution_ready"))
    reason_adv = str(adv_result.get("advancement_reason") or "")
    dup = "duplicate" in reason_adv.lower()

    tier = (execution_tier or "").lower()
    has_artifact = artifact_path is not None
    p = normalize_payload(payload)
    if not isinstance(p, dict):
        p = {}

    # Delta signals (Phase 3)
    delta_material = obj_adv and not dup
    delta_readiness = op_ready and not dup
    delta_artifact = has_artifact and obj_adv
    ambiguity_down = bool(
        isinstance(p, dict)
        and (p.get("ambiguity_reduced") or (isinstance(p.get("ranked"), list) and len(p.get("ranked", [])) >= 2))
    )

    vt = _infer_value_type(arch)
    out["value_type"] = vt

    # --- Archetype rules (Phase 2) ---
    if arch == "generate_execution_plan" or exo == "readiness_only":
        # Never value on its own unless materially improved best + readiness
        verified = bool(delta_material and op_ready)
        score = 0.55 * float(delta_material) + 0.45 * float(op_ready)
        reason = (
            "plan_improved_best_and_readiness"
            if verified
            else "generate_execution_plan_is_support_only_without_material_delta"
        )
    elif arch == "execute_best_opportunity":
        verified = bool(
            exo in ("succeeded", "partial")
            and (
                delta_material
                or (delta_readiness and (has_artifact or ambiguity_down))
                or (exo == "succeeded" and has_artifact and not dup)
            )
        )
        score = (
            0.35 * float(exo == "succeeded")
            + 0.3 * float(delta_material)
            + 0.2 * float(delta_readiness)
            + 0.15 * float(has_artifact)
        )
        reason = (
            "usable_step_or_ranked_artifact_or_measurable_delta"
            if verified
            else "execution_without_measurable_operator_utility"
        )
    elif "repair" in arch and "registry" in arch:
        unlock = bool(
            isinstance(p, dict)
            and (p.get("registry_updated") or p.get("tools_unlocked") or p.get("unblocked"))
        )
        verified = bool(exo == "succeeded" and (delta_material or unlock or obj_adv))
        score = 0.5 * float(exo == "succeeded") + 0.35 * float(delta_material or unlock) + 0.15 * float(
            op_ready
        )
        reason = "registry_unblocked_or_capability_path" if verified else "repair_without_unblock_or_delta"
        if verified:
            out["blocker_removed"] = True
    elif "artifact_synthesizer" in arch or "synthes" in arch:
        verified = bool(delta_material and (op_ready or ex_ready or not dup))
        score = 0.4 * float(delta_material) + 0.35 * float(op_ready) + 0.25 * float(not dup)
        reason = (
            "synthesis_improved_best_or_reduced_dup_or_readiness"
            if verified
            else "synthesis_without_quality_or_dup_gain"
        )
    else:
        verified = bool(
            exo in ("succeeded", "partial", "readiness_only")
            and (delta_material or (delta_readiness and tier == "strong") or delta_artifact)
        )
        score = (
            0.35 * float(delta_material)
            + 0.3 * float(delta_readiness)
            + 0.2 * float(exo == "succeeded")
            + 0.15 * float(has_artifact)
        )
        reason = "measurable_delta_or_readiness_or_artifact" if verified else "no_verified_delta"

    if exo == "failed":
        verified = False
        score = min(score, 0.15)
        out["value_reason"] = "execution_failed_no_value"
        out["value_score"] = round(max(0.0, min(1.0, score)), 4)
        out["value_verified"] = False
        out["value_type"] = vt
        return out

    out["value_verified"] = bool(verified)
    out["value_score"] = round(max(0.0, min(1.0, score)), 4)
    out["value_reason"] = reason[:300]

    if not verified and exo == "succeeded":
        out["value_reason"] = (reason + ";success_without_value_delta")[:300]

    return out
