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
    "package_operator_offer_pack": "offer_pack",
    "package_operator_offer_page": "offer_pack",
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

    if contract_id == "offer_pack":
        if not isinstance(p, dict):
            return False, "expected_object"
        for k in (
            "product_name",
            "one_liner",
            "target_customer",
            "problem",
            "why_buy_now",
            "validation_prompt",
            "listing_markdown",
        ):
            if not _is_nonempty_str(p.get(k)):
                return False, f"missing_{k}"
        deliverables = p.get("deliverables")
        if not isinstance(deliverables, list) or len(deliverables) < 3:
            return False, "missing_deliverables"
        for i, item in enumerate(deliverables[:12]):
            if not _is_nonempty_str(item):
                return False, f"deliverable_{i}_empty"
        pricing = p.get("pricing_options")
        if not isinstance(pricing, list) or len(pricing) < 2:
            return False, "missing_pricing_options"
        for i, option in enumerate(pricing[:6]):
            if not isinstance(option, dict):
                return False, f"pricing_{i}_not_object"
            for key in ("name", "price"):
                if not _is_nonempty_str(option.get(key)):
                    return False, f"pricing_{i}_missing_{key}"
            includes = option.get("includes")
            if not isinstance(includes, list) or len(includes) < 1:
                return False, f"pricing_{i}_missing_includes"
        sources = p.get("source_artifacts") or p.get("sources_or_origin")
        if isinstance(sources, list):
            if len(sources) < 1:
                return False, "missing_sources"
        elif not _is_nonempty_str(sources):
            return False, "missing_sources"
        return True, "ok"

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


def _first_nonempty_str(*values: Any) -> str:
    for value in values:
        if _is_nonempty_str(value):
            return _coerce_str(value)
    return ""


def _clean_offer_name(seed: str) -> str:
    name = _coerce_str(seed)
    if not name:
        return "Elysia Opportunity Sprint"
    name = re.sub(r"^(launch|create|generate|package)\s+", "", name, flags=re.IGNORECASE).strip(" -:.")
    if name.lower().startswith("revenue angle:"):
        name = name.split(":", 1)[1].strip()
    if not name:
        name = "Elysia Opportunity"
    if not any(token in name.lower() for token in ("pack", "sprint", "service", "audit", "brief", "studio")):
        name = f"{name} Sprint"
    return name[:80]


def build_offer_pack_from_artifacts(
    *,
    revenue_payload: Optional[Dict[str, Any]] = None,
    digest_payload: Optional[Dict[str, Any]] = None,
    improvement_payload: Optional[Dict[str, Any]] = None,
    source_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    revenue = revenue_payload if isinstance(revenue_payload, dict) else {}
    digest = digest_payload if isinstance(digest_payload, dict) else {}
    improvement = improvement_payload if isinstance(improvement_payload, dict) else {}

    opportunities = revenue.get("opportunities")
    if not isinstance(opportunities, list) or not opportunities:
        opportunities = build_small_offer_ideas().get("opportunities") or []
    top = opportunities[0] if opportunities and isinstance(opportunities[0], dict) else {}

    top_title = _first_nonempty_str(top.get("title"), "Elysia Opportunity")
    rationale = _first_nonempty_str(top.get("rationale"), top.get("reason"))
    capability = _first_nonempty_str(top.get("required_capability"), top.get("capability"), "existing Elysia modules")
    difficulty = _coerce_str(top.get("difficulty")).lower() or "medium"
    expected_value = _first_nonempty_str(top.get("expected_value"), "medium")

    insights = digest.get("top_insights") if isinstance(digest.get("top_insights"), list) else []
    top_insight = _first_nonempty_str(insights[0] if insights else "")
    why_matter = _first_nonempty_str(digest.get("why_they_matter"))

    improvement_notes = []
    for key in ("recommendations", "gaps", "recommended_followup_tasks"):
        value = improvement.get(key)
        if isinstance(value, list):
            improvement_notes = [_coerce_str(item) for item in value if _is_nonempty_str(item)]
            if improvement_notes:
                break
    improvement_summary = _first_nonempty_str(
        improvement.get("summary"),
        improvement.get("weakness"),
        improvement.get("topic"),
        improvement_notes[0] if improvement_notes else "",
    )

    product_name = _clean_offer_name(top_title)
    target_customer = _first_nonempty_str(
        revenue.get("target_customer"),
        "solo operators, founders, and builders who need one clear next-step offer",
    )
    problem = _first_nonempty_str(
        rationale,
        why_matter,
        improvement_summary,
        "There is useful capability inside Elysia, but nothing packaged clearly enough for a buyer to say yes to it quickly.",
    )
    one_liner = (
        f"A fixed-scope offer that turns '{top_title}' into a buyer-ready brief, scoped deliverables, and a concrete next-step plan."
    )[:240]
    why_buy_now = _first_nonempty_str(
        why_matter,
        top_insight,
        "Elysia already produces useful internal artifacts; packaging one focused offer is the fastest way to test real demand.",
    )

    deliverables = [
        f"Focused offer brief for '{top_title}' with scope tied to {capability}.",
        "Buyer-facing listing copy with one clear promise and qualification criteria.",
        "Two pricing tiers with defined deliverables and a validation question.",
    ]
    if top_insight:
        deliverables.append(f"Recent learning angle to strengthen positioning: {top_insight}")
    if improvement_summary:
        deliverables.append(f"Improvement-led differentiator: {improvement_summary}")
    deliverables = deliverables[:5]

    starter_price = "$39" if difficulty == "low" else "$79" if difficulty == "medium" else "$149"
    premium_price = "$99" if difficulty == "low" else "$199" if difficulty == "medium" else "$349"

    pricing_options = [
        {
            "name": "Signal Test",
            "price": starter_price,
            "includes": [
                "Offer brief",
                "One deliverable outline",
                "Validation prompt for early buyers",
            ],
        },
        {
            "name": "Operator Sprint",
            "price": premium_price,
            "includes": [
                "Everything in Signal Test",
                "Expanded deliverables and buyer-facing copy",
                "One concrete next-step execution plan",
            ],
        },
    ]

    source_list = [str(item) for item in (source_names or []) if _is_nonempty_str(item)]
    if not source_list:
        source_list = ["template_local"]

    validation_prompt = (
        f"If {product_name} existed today for {starter_price}, would you want it? "
        "What outcome would make it worth paying for this week?"
    )
    recommended_next_step = (
        "Show this offer to three potential buyers or operators and record which promise, price, and deliverable they react to."
    )

    listing_markdown = "\n".join(
        [
            f"# {product_name}",
            "",
            one_liner,
            "",
            "## Who It's For",
            target_customer,
            "",
            "## Problem",
            problem,
            "",
            "## Deliverables",
            *(f"- {item}" for item in deliverables),
            "",
            "## Pricing",
            *(f"- {option['name']}: {option['price']} — {', '.join(option['includes'])}" for option in pricing_options),
            "",
            "## Why Buy Now",
            why_buy_now,
            "",
            "## Validation Prompt",
            validation_prompt,
        ]
    )

    return {
        "title": product_name,
        "product_name": product_name,
        "summary": one_liner,
        "one_liner": one_liner,
        "target_customer": target_customer,
        "problem": problem,
        "deliverables": deliverables,
        "pricing_options": pricing_options,
        "why_buy_now": why_buy_now,
        "validation_prompt": validation_prompt,
        "listing_markdown": listing_markdown,
        "recommended_next_step": recommended_next_step,
        "expected_value_signal": expected_value,
        "required_capability": capability,
        "source_artifacts": source_list[:8],
        "sources_or_origin": source_list[:8],
    }
