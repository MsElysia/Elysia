# project_guardian/self_task_readiness.py
# Stricter operator_ready / execution_ready than objective_advanced; handoff summaries.

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from .self_task_output_contracts import normalize_payload

logger = logging.getLogger(__name__)


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    return str(v).strip()


def _opp_key(opp: Any) -> str:
    if not isinstance(opp, dict):
        return hashlib.sha256(_s(opp).encode()).hexdigest()[:16]
    parts = [
        _s(opp.get("id")),
        _s(opp.get("opportunity_id")),
        _s(opp.get("title")),
        _s(opp.get("name")),
    ]
    raw = "|".join(x for x in parts if x) or json.dumps(opp, sort_keys=True, default=str)[:800]
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]


def _past_shortlist_keys(store: Any, objective_id: Optional[str]) -> Set[str]:
    if not objective_id or not hasattr(store, "get"):
        return set()
    o = store.get(objective_id)
    if not o:
        return set()
    keys = o.get("shortlist_seen_keys") or []
    if isinstance(keys, list):
        return {str(x) for x in keys}
    return set()


def _shortlist_opportunity_complete(opp: Any) -> bool:
    if not isinstance(opp, dict):
        return False
    rationale = _s(opp.get("rationale") or opp.get("reason") or opp.get("why"))
    cap = _s(opp.get("required_capability") or opp.get("capability") or opp.get("tool"))
    diff = opp.get("difficulty")
    diff_ok = diff is not None and _s(diff) != ""
    ev = opp.get("expected_value")
    ev_ok = ev is not None and _s(ev) != ""
    return bool(rationale and cap and diff_ok and ev_ok)


def _readiness_revenue_shortlist(
    p: Dict[str, Any],
    *,
    contract_ok: bool,
    objective_advanced: bool,
    store: Any,
    objective_id: Optional[str],
) -> Tuple[bool, str, Dict[str, Any]]:
    opps = p.get("opportunities")
    if not isinstance(opps, list) or len(opps) < 3:
        return False, "shortlist_lt3", {}
    has_ranks = all(
        isinstance(o, dict) and bool(_s(o.get("rank")) or _s(o.get("order")))
        for o in opps[:3]
    )
    ranked_ok = bool(p.get("ranked")) or has_ranks
    if not ranked_ok:
        return False, "not_ranked", {}

    incomplete = [i for i, o in enumerate(opps[: max(8, len(opps))]) if not _shortlist_opportunity_complete(o)]
    if incomplete:
        return False, f"opp_incomplete_fields:{incomplete[:5]}", {}

    past = _past_shortlist_keys(store, objective_id)
    keys = [_opp_key(o) for o in opps if isinstance(o, dict)]
    new_keys = [k for k in keys if k and k not in past]
    if past and not new_keys:
        return False, "all_opps_duplicate_vs_past_shortlist", {}

    extra = {"shortlist_opp_keys": keys[:24], "new_opp_keys": new_keys[:24]}
    ok = bool(objective_advanced and contract_ok)
    return ok, "revenue_shortlist_ready" if ok else "shortlist_gate_failed", extra


def _readiness_rank_opportunities(
    p: Dict[str, Any], *, contract_ok: bool, objective_advanced: bool
) -> Tuple[bool, str, Dict[str, Any]]:
    rnk = p.get("ranked")
    if not isinstance(rnk, list) or len(rnk) < 2:
        return False, "rank_lt2", {}
    top = rnk[0] if rnk else None
    top_id = _s(top) if not isinstance(top, dict) else _s(top.get("id") or top.get("title") or top.get("name"))
    rationale = _s(p.get("ranking_rationale") or p.get("rationale") or p.get("reason"))
    if isinstance(top, dict):
        rationale = rationale or _s(top.get("rationale") or top.get("reason"))
    if not top_id:
        return False, "no_top_choice", {}
    if not rationale:
        return False, "no_ranking_rationale", {}
    if not (bool(p.get("ambiguity_reduced")) or len(rnk) >= 2):
        return False, "ambiguity_not_reduced", {}
    ok = bool(objective_advanced and contract_ok and rationale)
    return ok, "rank_ready" if ok else "rank_gate_failed", {"top_choice": top_id[:120]}


def _readiness_execution_plan_arch(
    p: Dict[str, Any], *, contract_ok: bool, objective_advanced: bool
) -> Tuple[bool, str, Dict[str, Any]]:
    pl = p.get("execution_plan")
    if not isinstance(pl, dict):
        return False, "no_execution_plan", {}
    opp_tie = _s(pl.get("opportunity_id") or pl.get("opportunity") or pl.get("for_opportunity") or p.get("opportunity_id"))
    steps = pl.get("steps") or pl.get("phases") or []
    if not isinstance(steps, list) or len(steps) < 2:
        return False, "steps_lt2", {}
    prereq = pl.get("prerequisites") if "prerequisites" in pl else pl.get("prerequisite")
    blockers = pl.get("blockers") if "blockers" in pl else None
    expected = pl.get("expected_outcome") or pl.get("outcome") or p.get("expected_outcome")
    if prereq is None or blockers is None:
        return False, "missing_prereq_or_blockers_field", {}
    if expected is None or _s(expected) == "":
        return False, "missing_expected_outcome", {}
    if not opp_tie:
        return False, "plan_not_tied_to_opportunity", {}
    ok = bool(objective_advanced and contract_ok)
    return ok, "execution_plan_ready" if ok else "plan_gate_failed", {}


def _readiness_system_improvement(
    p: Dict[str, Any], *, contract_ok: bool, objective_advanced: bool
) -> Tuple[bool, str, Dict[str, Any]]:
    w = _s(p.get("weakness") or p.get("issue") or p.get("problem"))
    fix = _s(p.get("fix") or p.get("proposal") or p.get("proposed_fix"))
    targets = p.get("target_files") or p.get("modules") or p.get("target_modules")
    if isinstance(targets, str):
        targets = [targets]
    impact = _s(p.get("impact"))
    risk = _s(p.get("risk") or p.get("risks"))
    if not w or not fix:
        return False, "weakness_or_fix_missing", {}
    if not isinstance(targets, list) or len(targets) < 1:
        if not _s(p.get("target")):
            return False, "no_targets", {}
    if not impact or not risk:
        return False, "impact_or_risk_missing", {}
    ok = bool(objective_advanced and contract_ok)
    return ok, "improvement_proposal_ready" if ok else "improvement_gate_failed", {}


def _readiness_default(
    p: Dict[str, Any], *, contract_ok: bool, objective_advanced: bool
) -> Tuple[bool, str, Dict[str, Any]]:
    if not objective_advanced or not contract_ok:
        return False, "default_need_advance_and_contract", {}
    if isinstance(p, dict) and len(p) >= 2:
        return True, "default_dict_nonempty", {}
    return False, "default_insufficient", {}


def compute_operator_readiness(
    archetype: str,
    payload: Any,
    *,
    contract_ok: bool,
    objective_advanced: bool,
    store: Any,
    objective_id: Optional[str],
) -> Tuple[bool, str, Dict[str, Any]]:
    """Hard gates per archetype; stricter than objective_advanced."""
    arch = (archetype or "").lower()
    p = normalize_payload(payload)
    if not objective_advanced:
        return False, "not_objective_advanced", {}
    if not contract_ok:
        return False, "contract_not_ok", {}
    if not isinstance(p, dict):
        return False, "payload_not_dict", {}

    if "revenue_shortlist" in arch or "generate_revenue" in arch or "dry_run_offer" in arch:
        return _readiness_revenue_shortlist(
            p, contract_ok=contract_ok, objective_advanced=objective_advanced, store=store, objective_id=objective_id
        )
    if "rank" in arch and "opportunit" in arch:
        return _readiness_rank_opportunities(p, contract_ok=contract_ok, objective_advanced=objective_advanced)
    if "execution_plan" in arch or arch == "execute_best_opportunity":
        return _readiness_execution_plan_arch(p, contract_ok=contract_ok, objective_advanced=objective_advanced)
    if "improvement" in arch and "proposal" in arch:
        return _readiness_system_improvement(p, contract_ok=contract_ok, objective_advanced=objective_advanced)

    return _readiness_default(p, contract_ok=contract_ok, objective_advanced=objective_advanced)


def _guardian_capability_available(guardian: Any, cap: str) -> bool:
    if not cap or ":" not in cap:
        return False
    kind, _, name = cap.partition(":")
    kind = kind.strip().lower()
    name = name.strip()
    mods = getattr(guardian, "_modules", None) or {}
    if kind == "module":
        return name in mods
    if kind == "tool":
        tr = mods.get("tool_registry")
        if tr is None:
            return False
        if hasattr(tr, "has_tool"):
            try:
                return bool(tr.has_tool(name))
            except Exception:
                pass
        return False
    return False


def compute_execution_readiness(
    archetype: str,
    payload: Any,
    *,
    operator_ready: bool,
    guardian: Optional[Any],
) -> Tuple[bool, str]:
    if not operator_ready:
        return False, "not_operator_ready"
    p = normalize_payload(payload)
    if not isinstance(p, dict):
        return False, "no_dict_payload", {}

    pl = p.get("execution_plan")
    arch_l = (archetype or "").lower()

    if isinstance(pl, dict):
        steps = pl.get("steps") or pl.get("phases") or []
        if not isinstance(steps, list) or len(steps) < 1:
            return False, "no_steps_for_execution"
        first = steps[0]
        concrete = _s(first if not isinstance(first, dict) else first.get("action") or first.get("step") or first.get("description"))
        if len(concrete) < 8:
            return False, "next_step_not_concrete"
        prereq = pl.get("prerequisites") or pl.get("prerequisite")
        if isinstance(prereq, list) and len(prereq) > 0:
            return False, "blocking_prerequisites_remain"
        if isinstance(prereq, str) and prereq.strip():
            return False, "blocking_prerequisites_remain"
        bl = pl.get("blockers")
        if isinstance(bl, list) and any(_s(x) for x in bl):
            return False, "plan_blockers_remain"
        cap = _s(pl.get("required_capability") or pl.get("capability") or "")
        if cap and ":" in cap and guardian is not None and not _guardian_capability_available(guardian, cap):
            return False, "required_capability_missing"
        return True, "execution_ready"

    # No nested plan: shortlist / rank outputs — require callable capability on top item
    if "revenue_shortlist" in arch_l or "generate_revenue" in arch_l or "dry_run_offer" in arch_l:
        opps = p.get("opportunities")
        cap = ""
        if isinstance(opps, list) and opps:
            o0 = opps[0]
            if isinstance(o0, dict):
                cap = _s(o0.get("required_capability") or o0.get("capability") or o0.get("tool"))
        if not cap or ":" not in cap:
            return False, "no_concrete_capability_for_execution"
        if guardian is not None and not _guardian_capability_available(guardian, cap):
            return False, "required_capability_missing"
        block = p.get("blocking_prerequisites") or p.get("blockers")
        if isinstance(block, list) and len(block) > 0:
            return False, "blockers_remain"
        return True, "execution_ready"

    if "rank" in arch_l and "opportunit" in arch_l:
        rnk = p.get("ranked")
        cap = ""
        if isinstance(rnk, list) and rnk:
            t0 = rnk[0]
            if isinstance(t0, dict):
                cap = _s(t0.get("required_capability") or t0.get("capability") or t0.get("tool"))
        if not cap or ":" not in cap:
            return False, "no_concrete_capability_for_execution"
        if guardian is not None and not _guardian_capability_available(guardian, cap):
            return False, "required_capability_missing"
        return True, "execution_ready"

    block = p.get("blocking_prerequisites") or p.get("blockers")
    if isinstance(block, list) and len(block) > 0:
        return False, "blockers_remain"

    if "improvement" in arch_l and "proposal" in arch_l:
        nxt = _s(p.get("recommended_next_step") or p.get("next_step"))
        if len(nxt) < 12:
            return False, "improvement_next_step_vague"
        return True, "execution_ready"

    return False, "execution_not_applicable_without_plan_or_capability"


def build_handoff_summary(
    archetype: str,
    payload: Any,
    *,
    operator_ready: bool,
    execution_ready: bool,
) -> Optional[Dict[str, Any]]:
    if not operator_ready:
        return None
    p = normalize_payload(payload)
    arch = (archetype or "").lower()
    summary = ""
    why = ""
    nxt = ""

    if isinstance(p, dict):
        summary = _s(p.get("summary") or p.get("overview") or p.get("title"))[:400]
        why = _s(p.get("why_it_matters") or p.get("impact") or p.get("rationale"))[:400]
        nxt = _s(p.get("recommended_next_step") or p.get("next_action") or p.get("next_step"))[:400]
        pl = p.get("execution_plan")
        if isinstance(pl, dict) and not nxt:
            steps = pl.get("steps") or pl.get("phases") or []
            if isinstance(steps, list) and steps:
                nxt = _s(steps[0])[:400]
        opps = p.get("opportunities")
        if not summary and isinstance(opps, list) and opps:
            summary = f"Shortlist of {len(opps)} opportunities (ranked)."
        if not why and isinstance(opps, list) and opps:
            why = "Prioritized revenue paths with rationale and expected value for operator decision."
        rnk = p.get("ranked")
        if not summary and isinstance(rnk, list):
            summary = f"Ranked {len(rnk)} opportunities; top choice identified."
        if not why and isinstance(rnk, list):
            why = "Reduces ambiguity by ordering options with rationale."

    if not summary:
        summary = f"Completed {archetype} output ready for operator review."
    if not why:
        why = "Consolidates structured work into an actionable view."
    if not nxt:
        nxt = "Review the artifact and confirm the next action in your environment." if not execution_ready else "Proceed with the first execution step or delegate."

    return {
        "summary": summary[:800],
        "why_it_matters": why[:800],
        "recommended_next_step": nxt[:800],
        "execution_ready": bool(execution_ready),
    }


def integrate_readiness_into_advancement(
    archetype: str,
    payload: Any,
    *,
    contract_ok: bool,
    objective_advanced: bool,
    store: Any,
    objective_id: Optional[str],
    guardian: Optional[Any],
) -> Dict[str, Any]:
    """Returns operator_ready, execution_ready, readiness_reason, execution_reason, handoff."""
    op_r, op_reason, extra = compute_operator_readiness(
        archetype,
        payload,
        contract_ok=contract_ok,
        objective_advanced=objective_advanced,
        store=store,
        objective_id=objective_id,
    )
    ex_r, ex_reason = compute_execution_readiness(
        archetype, payload, operator_ready=op_r, guardian=guardian
    )
    handoff = build_handoff_summary(
        archetype, payload, operator_ready=op_r, execution_ready=ex_r
    )
    return {
        "operator_ready": op_r,
        "execution_ready": ex_r,
        "readiness_reason": op_reason,
        "execution_ready_reason": ex_reason,
        "readiness_extra": extra,
        "handoff": handoff,
    }
