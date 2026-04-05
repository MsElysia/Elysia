# project_guardian/self_task_output_contracts.py
# Required output shapes for high-value self-tasks (strong tier only if satisfied).

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Maps archetype prefix/suffix patterns to contract ids (longest match wins in lookup).
ARCHETYPE_TO_CONTRACT: Dict[str, str] = {
    "generate_revenue_shortlist": "revenue_shortlist",
    "finance_revenue_shortlist": "revenue_shortlist",
    "evaluate_existing_objectives_for_monetization": "revenue_shortlist",
    "identify_idle_capabilities_with_market_value": "revenue_shortlist",
    "create_small_dry_run_offer_ideas": "revenue_shortlist",
    "summarize_monetizable_directions_from_learning": "learned_digest",
    "harvest_research_brief": "research_brief",
    "harvest_metrics_summarize": "research_brief",
    "summarize_recent_learning_operator": "learned_digest",
    "identify_capability_gaps": "capability_gap_report",
    "generate_system_improvement_brief": "system_improvement_proposal",
    "compare_underused_modules_value": "research_brief",
    "learning_operator_digest": "learned_digest",
    "learning_recent_digest": "learned_digest",
}


def contract_id_for_archetype(archetype: str) -> Optional[str]:
    a = (archetype or "").strip()
    if a in ARCHETYPE_TO_CONTRACT:
        return ARCHETYPE_TO_CONTRACT[a]
    for k, v in ARCHETYPE_TO_CONTRACT.items():
        if k in a:
            return v
    return None


def normalize_payload(raw: Any) -> Any:
    """Unwrap common module envelopes."""
    cur: Any = raw
    for _ in range(4):
        if cur is None:
            return None
        if isinstance(cur, dict):
            if "result" in cur and len(cur) <= 5:
                cur = cur["result"]
                continue
            if "data" in cur and isinstance(cur.get("data"), (dict, list)):
                cur = cur["data"]
                continue
        break
    return cur


def _is_nonempty_str(x: Any) -> bool:
    return isinstance(x, str) and len(x.strip()) > 0


def _coerce_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (int, float)):
        return str(x)
    return str(x).strip()


def validate_contract(contract_id: str, payload: Any) -> Tuple[bool, str]:
    p = normalize_payload(payload)
    if p is None:
        return False, "empty_payload"

    if contract_id == "revenue_shortlist":
        if not isinstance(p, dict):
            return False, "expected_object"
        opps = p.get("opportunities")
        if not isinstance(opps, list):
            return False, "missing_opportunities"
        n = len(opps)
        if n < 3 or n > 12:
            return False, f"opportunities_count_{n}"
        for i, o in enumerate(opps[:12]):
            if not isinstance(o, dict):
                return False, f"opp_{i}_not_object"
            for k in ("title", "rationale", "required_capability", "difficulty"):
                if not _is_nonempty_str(_coerce_str(o.get(k))):
                    return False, f"opp_{i}_missing_{k}"
            ev = o.get("expected_value")
            if ev is None or (isinstance(ev, str) and not ev.strip()):
                return False, f"opp_{i}_missing_expected_value"
        return True, "ok"

    if contract_id == "research_brief":
        if not isinstance(p, dict):
            return False, "expected_object"
        if not _is_nonempty_str(p.get("topic")):
            return False, "missing_topic"
        fn = p.get("findings")
        if isinstance(fn, list):
            if len(fn) < 1:
                return False, "missing_findings"
        elif not _is_nonempty_str(fn):
            return False, "missing_findings"
        if not _is_nonempty_str(p.get("sources_or_origin")) and not _is_nonempty_str(
            p.get("sources_used")
        ):
            return False, "missing_sources"
        nxt = p.get("recommended_next_actions")
        if isinstance(nxt, list):
            if len(nxt) < 1:
                return False, "missing_next_actions"
        elif not _is_nonempty_str(nxt):
            return False, "missing_next_actions"
        return True, "ok"

    if contract_id == "system_improvement_proposal":
        if not isinstance(p, dict):
            return False, "expected_object"
        for k in ("weakness", "proposed_fix", "expected_impact", "risk"):
            if not _is_nonempty_str(p.get(k)):
                return False, f"missing_{k}"
        fmod = p.get("files_or_modules") or p.get("files_modules_affected")
        if not _is_nonempty_str(fmod) and not isinstance(fmod, list):
            return False, "missing_files_or_modules"
        return True, "ok"

    if contract_id == "learned_digest":
        if not isinstance(p, dict):
            return False, "expected_object"
        ins = p.get("top_insights")
        if not isinstance(ins, list) or len(ins) < 1:
            return False, "missing_top_insights"
        if not _is_nonempty_str(p.get("why_they_matter")):
            return False, "missing_why"
        fol = p.get("recommended_followup_tasks")
        if isinstance(fol, list):
            if len(fol) < 1:
                return False, "missing_followups"
        elif not _is_nonempty_str(fol):
            return False, "missing_followups"
        return True, "ok"

    if contract_id == "capability_gap_report":
        if not isinstance(p, dict):
            return False, "expected_object"
        gaps = p.get("gaps")
        if not isinstance(gaps, list) or len(gaps) < 1:
            return False, "missing_gaps"
        for i, g in enumerate(gaps[:20]):
            if isinstance(g, dict):
                if not _is_nonempty_str(g.get("description") or g.get("gap")):
                    return False, f"gap_{i}_incomplete"
            elif not _is_nonempty_str(g):
                return False, f"gap_{i}_empty"
        sa = p.get("suggested_actions")
        if isinstance(sa, list):
            if len(sa) < 1:
                return False, "missing_suggested_actions"
        elif not _is_nonempty_str(sa):
            return False, "missing_suggested_actions"
        return True, "ok"

    return False, "unknown_contract"


def build_revenue_shortlist_from_summary(summary: Any) -> Dict[str, Any]:
    """Deterministic structured opportunities from income summary dict (local only)."""
    s = summary if isinstance(summary, dict) else {}
    lines: List[str] = []
    for k, v in s.items():
        lines.append(f"{k}: {v}")
    blob = " | ".join(lines)[:1200] or "insufficient local financial data"
    seeds = re.split(r"[\n;|]", blob)
    seeds = [x.strip() for x in seeds if len(x.strip()) > 8][:8]
    if len(seeds) < 3:
        seeds = [
            "Review income summary for recurring patterns",
            "Cross-check wallet vs harvest totals",
            "Identify one automation candidate from idle modules",
        ]
    opps: List[Dict[str, Any]] = []
    for i, text in enumerate(seeds[:10]):
        opps.append(
            {
                "title": (text[:80] + ("…" if len(text) > 80 else "")),
                "rationale": f"Derived from local summary field analysis (item {i + 1}).",
                "required_capability": "module:income_generator",
                "difficulty": "low" if i < 2 else "medium",
                "expected_value": "visibility" if i == 0 else "medium",
            }
        )
    while len(opps) < 3:
        opps.append(
            {
                "title": "Expand data collection for revenue modeling",
                "rationale": "Thin local data; add metrics before scaling.",
                "required_capability": "module:harvest_engine",
                "difficulty": "medium",
                "expected_value": "low",
            }
        )
    return {
        "opportunities": opps[:10],
        "sources_or_origin": ["get_income_summary", "local_guardian"],
        "ranked": True,
    }


def build_capability_gap_report_from_tools(tools: Any) -> Dict[str, Any]:
    """Shape a gap report from tool registry list."""
    known = {"llm", "web", "exec", "tool", "api"}
    tlist = tools if isinstance(tools, list) else []
    names = [str(getattr(x, "id", x) if not isinstance(x, dict) else x.get("id", x)) for x in tlist[:40]]
    gaps = []
    for exp in sorted(known):
        if not any(exp.lower() in n.lower() for n in names):
            gaps.append(
                {
                    "description": f"No obvious {exp} surface in registry snapshot",
                    "severity": "medium",
                }
            )
    if not gaps:
        gaps = [{"description": "Registry populated; review coverage vs product roadmap", "severity": "low"}]
    return {
        "gaps": gaps[:12],
        "suggested_actions": [
            "Compare registry entries to autonomy allowed_actions",
            "Add one missing integration behind trust gate",
        ],
        "sources_or_origin": "tool_registry.list_tools",
    }


def build_research_brief_shell(topic: str, findings: str, origin: str) -> Dict[str, Any]:
    return {
        "topic": topic[:300],
        "findings": findings[:4000],
        "sources_or_origin": origin[:500],
        "recommended_next_actions": ["Review brief", "Schedule follow-up task if gaps remain"],
    }


def build_system_improvement_shell(
    weakness: str, fix: str, modules: str, impact: str, risk: str
) -> Dict[str, Any]:
    return {
        "weakness": weakness[:800],
        "proposed_fix": fix[:800],
        "files_or_modules": modules[:500],
        "expected_impact": impact[:500],
        "risk": risk[:500],
    }


def build_market_value_opportunities_from_tools(tools: Any) -> Dict[str, Any]:
    tlist = tools if isinstance(tools, list) else []
    names: List[str] = []
    for x in tlist[:24]:
        if isinstance(x, dict):
            names.append(str(x.get("id") or x.get("name") or "tool"))
        else:
            names.append(str(x))
    opps: List[Dict[str, Any]] = []
    for i, n in enumerate(names[:8] if names else ["tool_registry"]):
        opps.append(
            {
                "title": f"Monetizable packaging for {n[:60]}",
                "rationale": "Exposed local capability may support API tier, bundles, or operator-facing add-ons.",
                "required_capability": f"tool:{n[:40]}",
                "difficulty": "medium",
                "expected_value": "medium",
            }
        )
    base = build_revenue_shortlist_from_summary({"tool_surfaces": ", ".join(names[:12])})
    if opps:
        base["opportunities"] = opps[:10]
    return base


def build_monetization_from_planner_objectives(seq: List[Any]) -> Dict[str, Any]:
    opps: List[Dict[str, Any]] = []
    for i, o in enumerate(seq[:10]):
        if isinstance(o, dict):
            title = str(o.get("name") or o.get("title") or f"objective_{i}")[:120]
            desc = str(o.get("description") or o.get("goal") or title)[:400]
        else:
            title = str(getattr(o, "name", None) or getattr(o, "title", None) or f"objective_{i}")
            desc = title
        opps.append(
            {
                "title": f"Revenue angle: {title}",
                "rationale": desc,
                "required_capability": "module:longterm_planner",
                "difficulty": "medium",
                "expected_value": "uncertain",
            }
        )
    while len(opps) < 3:
        opps.append(
            {
                "title": "Define measurable monetization KPI",
                "rationale": "Planner objectives exist; tie each to a revenue or savings metric.",
                "required_capability": "module:longterm_planner",
                "difficulty": "low",
                "expected_value": "high",
            }
        )
    return {"opportunities": opps[:10], "sources_or_origin": ["longterm_planner.objectives"]}


def build_compare_underused_modules_research(modules: List[str]) -> Dict[str, Any]:
    ms = [str(m) for m in modules[:12] if m]
    topic = "Underused modules value comparison"
    findings = (
        "Compared idle modules: "
        + ", ".join(ms)
        + ". Prioritize modules that close operator blind spots or unlock revenue surfaces."
    )
    return build_research_brief_shell(
        topic,
        findings,
        "self_task.compare_underused_modules_value",
    )


def build_system_improvement_from_gaps(gap_report: Dict[str, Any]) -> Dict[str, Any]:
    gaps = gap_report.get("gaps") if isinstance(gap_report, dict) else []
    g0 = gaps[0] if gaps else {}
    desc = (
        str(g0.get("description") or g0)[:400]
        if isinstance(g0, dict)
        else str(g0)[:400]
    )
    return build_system_improvement_shell(
        weakness=desc or "Capability coverage unclear vs autonomy needs",
        proposed_fix="Add one bounded integration or registry entry per gap; re-run validation.",
        modules="project_guardian tool_registry, capability_registry",
        impact="Fewer routing failures; clearer operator visibility",
        risk="Low if changes are read-only or behind trust gates",
    )


def build_small_offer_ideas() -> Dict[str, Any]:
    opps = [
        {
            "title": "Time-boxed audit micro-offer",
            "rationale": "Sell a short structured review using existing harvest + planner outputs only.",
            "required_capability": "module:harvest_engine",
            "difficulty": "low",
            "expected_value": "medium",
        },
        {
            "title": "Operator dashboard export",
            "rationale": "Package JSON briefs from generated_reports as a weekly digest product.",
            "required_capability": "filesystem",
            "difficulty": "low",
            "expected_value": "medium",
        },
        {
            "title": "Capability gap remediation sprint",
            "rationale": "Fixed-scope fix for top gap report item.",
            "required_capability": "module:tool_registry",
            "difficulty": "medium",
            "expected_value": "high",
        },
    ]
    return {"opportunities": opps, "sources_or_origin": ["template_local"]}
