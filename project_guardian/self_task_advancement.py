# project_guardian/self_task_advancement.py
# Distinguish structured output from material objective advancement.

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .self_task_output_contracts import normalize_payload
from .self_task_readiness import integrate_readiness_into_advancement

logger = logging.getLogger(__name__)


def _fingerprint(payload: Any) -> str:
    try:
        p = normalize_payload(payload)
        s = json.dumps(p, sort_keys=True, default=str)[:12000]
        return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()[:32]
    except Exception:
        return ""


def _quality_score(archetype: str, payload: Any) -> float:
    """Heuristic 0–1 completeness / actionability."""
    p = normalize_payload(payload)
    if p is None:
        return 0.0
    score = 0.15
    if isinstance(p, dict):
        score += min(0.2, len(p) * 0.02)
        opps = p.get("opportunities")
        if isinstance(opps, list):
            score += min(0.35, len(opps) * 0.04)
            if len(opps) >= 3:
                score += 0.1
        ranked = p.get("ranked")
        if ranked is True or isinstance(p.get("ranked"), list):
            score += 0.08
        rnk = p.get("ranked")
        if isinstance(rnk, list) and len(rnk) >= 1:
            score += min(0.2, len(rnk) * 0.03)
        plan = p.get("execution_plan")
        if isinstance(plan, dict):
            steps = plan.get("steps") or plan.get("phases")
            if isinstance(steps, list) and len(steps) >= 2:
                score += 0.2
            elif plan:
                score += 0.1
        summaries = p.get("summaries")
        if isinstance(summaries, list) and len(summaries) >= 2:
            score += 0.12
        if isinstance(p.get("top_insights"), list) and len(p.get("top_insights", [])) >= 1:
            score += 0.1
        gaps = p.get("gaps")
        if isinstance(gaps, list) and len(gaps) >= 1:
            score += 0.08
    elif isinstance(p, list) and len(p) > 0:
        score += min(0.3, len(p) * 0.05)
    return max(0.0, min(1.0, score))


def evaluate_task_advancement(
    *,
    archetype: str,
    execution_tier: str,
    contract_ok: bool,
    contract_id: Optional[str],
    payload: Any,
    objective_id: Optional[str],
    store: Any,
    guardian: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Returns advancement_score, advancement_reason, objective_advanced,
    operator_ready, execution_ready, handoff (readiness stricter than advancement).
    """
    arch = (archetype or "").lower()
    tier = (execution_tier or "").lower()
    out: Dict[str, Any] = {
        "advancement_score": 0.0,
        "advancement_reason": "no_payload",
        "objective_advanced": False,
        "operator_ready": False,
        "execution_ready": False,
        "readiness_reason": "",
        "execution_ready_reason": "",
        "handoff": None,
        "readiness_extra": {},
    }
    if tier == "failed":
        out["advancement_reason"] = "task_failed"
        return out

    if not objective_id or not str(objective_id).strip():
        out["advancement_reason"] = "no_objective_id"
        return out

    p = normalize_payload(payload)
    if p is None or (isinstance(p, dict) and len(p) == 0):
        out["advancement_reason"] = "empty_payload"
        return out

    fp = _fingerprint(p)
    q = _quality_score(arch, p)
    o = None
    best = None
    if objective_id and hasattr(store, "get"):
        o = store.get(objective_id)
        if o:
            best = o.get("best_artifact")
    best_fp = (best or {}).get("fingerprint") if isinstance(best, dict) else None
    best_q = float((best or {}).get("quality", 0.0) or 0.0) if isinstance(best, dict) else 0.0

    duplicate = bool(best_fp and fp and best_fp == fp)
    improved = q > best_q + 0.04
    first_best = best_fp is None or best_q <= 0.01

    # Archetype-specific gates
    reason_parts: list = []
    score = q * 0.65
    if contract_ok and contract_id:
        score += 0.15
        reason_parts.append("contract_ok")
    if duplicate:
        score = min(score, 0.12)
        reason_parts.append("duplicate_fingerprint")

    if "revenue_shortlist" in arch or arch.endswith("revenue_shortlist") or "generate_revenue" in arch:
        opps = p.get("opportunities") if isinstance(p, dict) else None
        if not isinstance(opps, list) or len(opps) < 3:
            score *= 0.35
            reason_parts.append("shortlist_too_thin")
        elif duplicate:
            reason_parts.append("duplicate_shortlist")
        else:
            reason_parts.append("non_empty_ranked_shortlist")
            score += 0.1

    if "rank" in arch and "opportunit" in arch:
        rnk = p.get("ranked") if isinstance(p, dict) else None
        if isinstance(rnk, list) and len(rnk) >= 2:
            reason_parts.append("ranking_meaningful")
            score += 0.12
        elif isinstance(rnk, list) and len(rnk) <= 1:
            score *= 0.5
            reason_parts.append("ranking_trivial")

    if "execution_plan" in arch or (isinstance(p, dict) and p.get("execution_plan")):
        pl = p.get("execution_plan") if isinstance(p, dict) else None
        if isinstance(pl, dict):
            steps = pl.get("steps") or pl.get("phases") or []
            if isinstance(steps, list) and len(steps) >= 2:
                reason_parts.append("concrete_steps")
                score += 0.15
            else:
                score *= 0.55
                reason_parts.append("vague_plan")

    if "artifact" in arch or "synthes" in arch:
        summ = p.get("summaries") if isinstance(p, dict) else None
        src = p.get("sources") if isinstance(p, dict) else None
        if isinstance(summ, list) and len(summ) >= 2:
            score += 0.1
            reason_parts.append("synthesis_broader")
        if duplicate and isinstance(summ, list):
            score *= 0.45
            reason_parts.append("synthesis_duplicate")

    if not duplicate and (improved or first_best):
        reason_parts.append("improved_or_first_best")
        score += 0.1

    score = max(0.0, min(1.0, score))
    advanced = bool(
        score >= 0.38
        and not duplicate
        and (improved or first_best or (contract_ok and q >= 0.45))
    )
    if duplicate and score < 0.45:
        advanced = False

    out["advancement_score"] = round(score, 4)
    out["advancement_reason"] = "; ".join(reason_parts) if reason_parts else "heuristic_quality"
    out["objective_advanced"] = advanced

    rd = integrate_readiness_into_advancement(
        archetype,
        payload,
        contract_ok=contract_ok,
        objective_advanced=advanced,
        store=store,
        objective_id=objective_id,
        guardian=guardian,
    )
    out["operator_ready"] = bool(rd.get("operator_ready"))
    out["execution_ready"] = bool(rd.get("execution_ready"))
    out["readiness_reason"] = str(rd.get("readiness_reason") or "")
    out["execution_ready_reason"] = str(rd.get("execution_ready_reason") or "")
    out["handoff"] = rd.get("handoff")
    out["readiness_extra"] = rd.get("readiness_extra") or {}
    return out


def merge_best_artifact(
    store: Any,
    objective_id: Optional[str],
    *,
    task_id: str,
    archetype: str,
    payload: Any,
    advancement: Dict[str, Any],
) -> None:
    """Persist best artifact snapshot when material improvement occurred."""
    if not objective_id or not hasattr(store, "get"):
        return
    if not advancement.get("objective_advanced"):
        return
    o = store.get(objective_id)
    if not o:
        return
    p = normalize_payload(payload)
    q = _quality_score(archetype, p)
    fp = _fingerprint(p)
    o["best_artifact"] = {
        "fingerprint": fp,
        "quality": q,
        "task_id": task_id,
        "archetype": archetype,
        "advancement_score": advancement.get("advancement_score"),
        "operator_ready": bool(advancement.get("operator_ready")),
        "execution_ready": bool(advancement.get("execution_ready")),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if advancement.get("handoff"):
        o["best_artifact"]["handoff"] = advancement.get("handoff")
    o["operator_ready"] = bool(advancement.get("operator_ready"))
    o["execution_ready"] = bool(advancement.get("execution_ready"))
    if advancement.get("handoff"):
        o["last_handoff"] = advancement.get("handoff")
    extra = advancement.get("readiness_extra") or {}
    keys = extra.get("shortlist_opp_keys") or extra.get("new_opp_keys")
    if isinstance(keys, list) and keys:
        seen = list(o.get("shortlist_seen_keys") or [])
        for k in keys:
            if k and k not in seen:
                seen.append(str(k))
        o["shortlist_seen_keys"] = seen[-50:]
    if advancement.get("objective_advanced"):
        if advancement.get("operator_ready"):
            o["advanced_without_operator_ready_streak"] = 0
            o["refinement_exhausted"] = False
        else:
            o["advanced_without_operator_ready_streak"] = int(o.get("advanced_without_operator_ready_streak") or 0) + 1
            if int(o.get("advanced_without_operator_ready_streak") or 0) >= 4:
                o["refinement_exhausted"] = True
    if hasattr(store, "_maybe_complete_objective"):
        store._maybe_complete_objective(o)
    if hasattr(store, "_save"):
        store._save()
