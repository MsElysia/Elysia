# project_guardian/self_task_generator.py
# Bounded self-task proposals from system state, opportunities, and gaps.

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .module_activity import activity_age_minutes
from .self_task_queue import SelfTaskQueue

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset(
    {"learning", "planning", "tooling", "finance", "maintenance", "research"}
)


def new_task_dict(
    *,
    archetype: str,
    title: str,
    goal: str,
    category: str,
    reason: str,
    priority: float,
    recommended_capabilities: List[str],
    success_criteria: str,
    dedupe_key: str,
    objective_id: Optional[str] = None,
    task_kind: str = "snapshot",
    output_contract_id: Optional[str] = None,
    unlocks_task_kind: Optional[str] = None,
    value_tier: str = "internal",
    underused_modules: Optional[List[str]] = None,
) -> Dict[str, Any]:
    cat = category if category in VALID_CATEGORIES else "maintenance"
    out: Dict[str, Any] = {
        "task_id": "",
        "title": (title or "")[:200],
        "goal": (goal or "")[:800],
        "category": cat,
        "reason": (reason or "")[:400],
        "priority": max(0.0, min(1.0, float(priority))),
        "bounded": True,
        "reversible": True,
        "recommended_capabilities": list(recommended_capabilities)[:6],
        "success_criteria": (success_criteria or "")[:300],
        "status": "pending",
        "archetype": archetype,
        "dedupe_key": dedupe_key,
        "objective_id": objective_id,
        "task_kind": (task_kind or "snapshot")[:32],
        "value_tier": (value_tier or "internal")[:16],
    }
    if output_contract_id:
        out["output_contract_id"] = output_contract_id[:64]
        out["produces_artifact"] = True
    if unlocks_task_kind:
        out["unlocks_task_kind"] = unlocks_task_kind[:64]
    if underused_modules:
        out["underused_modules"] = list(underused_modules)[:12]
    return out


def pick_objective_for_task(
    store: Any,
    guardian: Any,
    category: str,
    archetype: str,
) -> str:
    """Prefer typed high-value objectives; planner/finance; else default active."""
    from .self_task_objectives import ObjectiveStore

    if not isinstance(store, ObjectiveStore):
        store = ObjectiveStore()
    oid0 = store.ensure_minimum_active(guardian)
    store.sync_from_longterm_planner(guardian)
    a = (archetype or "").lower()
    if any(
        x in a
        for x in (
            "revenue",
            "monetiz",
            "shortlist",
            "offer_ideas",
            "finance_revenue",
            "finance_idle",
        )
    ):
        return store.ensure_typed_objective(
            "revenue_generation",
            title="Revenue & monetization",
            goal="Structured opportunities and dry-run plans for the operator (no external posting).",
            priority=0.72,
        )
    if any(
        x in a
        for x in (
            "research_brief",
            "harvest_research",
            "harvest_metrics",
            "compare_underused",
            "refresh_objective",
        )
    ):
        return store.ensure_typed_objective(
            "research_and_intelligence",
            title="Research & intelligence",
            goal="Briefs, comparisons, and harvest-derived insight for decisions.",
            priority=0.68,
        )
    if any(x in a for x in ("capability_gap", "system_improvement_brief", "improvement_brief")):
        return store.ensure_typed_objective(
            "system_improvement",
            title="System improvement",
            goal="Actionable fixes and gap reports with impact and risk.",
            priority=0.66,
        )
    if category == "learning" or any(x in a for x in ("digest", "learning_operator", "summarize_recent_learning")):
        return store.ensure_typed_objective(
            "operator_support",
            title="Operator support & learning",
            goal="Insights and follow-ups from consolidated learning.",
            priority=0.64,
        )
    if category == "planning":
        for o in store.list_all():
            if o.get("status") == "active" and o.get("source") == "longterm_planner":
                return str(o["objective_id"])
    if category == "finance":
        for o in store.list_all():
            if o.get("status") == "active" and (
                "financ" in (o.get("title") or "").lower() or "revenue" in (o.get("goal") or "").lower()
            ):
                return str(o["objective_id"])
        return store.create_lightweight(
            title="Financial visibility",
            goal="Bounded read-only financial insight and opportunity notes.",
            priority=0.55,
            objective_type="revenue_generation",
        )
    if archetype in ("validate_tool_registry_snapshot", "repair_tool_registry_coverage", "api_capability_smoke"):
        for o in store.list_all():
            if o.get("status") == "active" and "coherence" in (o.get("title") or "").lower():
                return str(o["objective_id"])
    return oid0


def archetype_to_task_kind(archetype: str) -> str:
    a = (archetype or "").lower()
    if any(
        x in a
        for x in (
            "summarize",
            "shortlist",
            "digest",
            "idea",
            "metrics",
            "research_brief",
            "monetiz",
            "revenue_shortlist",
        )
    ):
        return "generation"
    if any(x in a for x in ("repair", "improve", "gap", "improvement_brief")):
        return "improvement"
    if any(x in a for x in ("validate", "snapshot", "pulse", "smoke", "diagnostic", "idle")):
        return "snapshot"
    return "execution"


def enrich_task_metadata(t: Dict[str, Any]) -> None:
    from .self_task_output_contracts import contract_id_for_archetype

    arch = str(t.get("archetype") or "")
    cid = t.get("output_contract_id") or contract_id_for_archetype(arch)
    if cid:
        t["output_contract_id"] = cid
        t["produces_artifact"] = True
        t["value_tier"] = "high"
    elif t.get("unlocks_task_kind"):
        t.setdefault("value_tier", "internal")
    else:
        t.setdefault("value_tier", "internal")


def _is_monetization_like_archetype(archetype: str) -> bool:
    a = str(archetype or "").lower()
    return any(
        token in a
        for token in (
            "revenue",
            "monetiz",
            "income",
            "harvest",
            "offer_ideas",
            "offer_pack",
            "operator_offer",
            "offer_page",
            "finance_idle",
            "shortlist",
            "market_value",
        )
    )


def _task_repeat_suppression_reason(task: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[str]:
    arch = str(task.get("archetype") or "").strip()
    if not arch:
        return None
    stale = {str(x) for x in (ctx.get("stale_self_task_archetypes") or []) if str(x).strip()}
    if arch in stale:
        return "recent_stale_self_task_repeat"
    if bool(ctx.get("stale_monetization_loop")) and _is_monetization_like_archetype(arch):
        return "recent_stale_monetization_loop"
    return None


def _append_task_if_fresh(tasks: List[Dict[str, Any]], task: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
    reason = _task_repeat_suppression_reason(task, ctx)
    if reason:
        logger.info(
            "[SelfTaskGenerator] suppressed archetype=%s reason=%s",
            str(task.get("archetype") or "")[:64],
            reason,
        )
        return False
    tasks.append(task)
    return True


def attach_objectives_to_tasks(
    guardian: Any,
    tasks: List[Dict[str, Any]],
    store: Optional[Any] = None,
) -> None:
    from .self_task_objectives import ObjectiveStore

    st = store if isinstance(store, ObjectiveStore) else ObjectiveStore()
    for t in tasks:
        cat = str(t.get("category") or "maintenance")
        arch = str(t.get("archetype") or "")
        if not t.get("objective_id"):
            t["objective_id"] = pick_objective_for_task(st, guardian, cat, arch)
        t["task_kind"] = archetype_to_task_kind(arch)
        enrich_task_metadata(t)


class SelfTaskGenerator:
    """Produces structured tasks; queue handles persistence and dedupe."""

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg

    def should_generate(self, ctx: Dict[str, Any], queue: SelfTaskQueue) -> bool:
        if not ctx.get("enabled", True):
            return False
        if ctx.get("force"):
            return True
        if ctx.get("low_confidence_streak", 0) >= int(
            self.cfg.get("low_confidence_streak_trigger", 2)
        ):
            return True
        if ctx.get("repeated_action_streak", 0) >= int(
            self.cfg.get("repeated_action_streak_trigger", 3)
        ):
            return True
        if ctx.get("idle_no_candidates"):
            return True
        if ctx.get("startup_issue"):
            return True
        if ctx.get("tool_registry_weak"):
            return True
        if ctx.get("financial_idle"):
            return True
        if ctx.get("module_underuse"):
            return True
        if ctx.get("weak_decision"):
            return True
        if len(queue.list_pending_sorted()) < 2 and (
            ctx.get("low_confidence_streak", 0) >= 1 or ctx.get("weak_decision")
        ):
            return True
        return False

    def _add_operator_value_tasks(
        self,
        guardian: Any,
        ctx: Dict[str, Any],
        tasks: List[Dict[str, Any]],
        has,
    ) -> None:
        """Bounded high-value tasks (prepended before maintenance-heavy generators)."""
        max_hv = int(self.cfg.get("max_operator_value_tasks_per_cycle", 4))
        n = 0
        hour = int(time.time() // 3600)

        def push(t: Dict[str, Any]) -> None:
            nonlocal n
            if n >= max_hv:
                return
            if _append_task_if_fresh(tasks, t, ctx):
                n += 1

        if has("income_generator"):
            push(
                new_task_dict(
                    archetype="generate_revenue_shortlist",
                    title="Generate ranked revenue shortlist (local)",
                    goal="Use local income summary only. Output JSON matching revenue_shortlist contract (ranked opportunities). No outbound posts or transactions.",
                    category="finance",
                    reason="Operator-facing monetization ideas from wired financial modules.",
                    priority=0.88,
                    recommended_capabilities=["module:income_generator"],
                    success_criteria="Structured revenue_shortlist JSON.",
                    dedupe_key=f"generate_revenue_shortlist_{hour}",
                    output_contract_id="revenue_shortlist",
                    value_tier="high",
                )
            )
            if has("tool_registry"):
                push(
                    new_task_dict(
                        archetype="package_operator_offer_pack",
                        title="Package operator offer page",
                        goal="Turn the strongest local opportunity and recent artifacts into an offer_pack JSON with deliverables, pricing options, validation prompt, and listing markdown.",
                        category="finance",
                        reason="Elysia needs one concrete thing it can try to sell before optimizing distribution.",
                        priority=0.87,
                        recommended_capabilities=["tool:artifact_synthesizer"],
                        success_criteria="Structured offer_pack JSON with listing_markdown.",
                        dedupe_key=f"package_operator_offer_pack_{hour // 6}",
                        output_contract_id="offer_pack",
                        value_tier="high",
                    )
                )
            push(
                new_task_dict(
                    archetype="create_small_dry_run_offer_ideas",
                    title="Small dry-run offer ideas (local)",
                    goal="Produce 3+ concrete offer shapes that could be tested without external posting.",
                    category="finance",
                    reason="Translate capabilities into bounded commercial hypotheses.",
                    priority=0.84,
                    recommended_capabilities=["module:income_generator"],
                    success_criteria="Structured revenue_shortlist-style opportunities.",
                    dedupe_key=f"create_small_dry_run_offer_ideas_{hour // 6}",
                    output_contract_id="revenue_shortlist",
                    value_tier="high",
                )
            )
            push(
                new_task_dict(
                    archetype="summarize_monetizable_directions_from_learning",
                    title="Monetizable directions from learning + income snapshot",
                    goal="Combine local income keys with learning heuristics; output learned_digest contract.",
                    category="learning",
                    reason="Connect introspection signals to revenue-facing next steps.",
                    priority=0.82,
                    recommended_capabilities=["module:income_generator"],
                    success_criteria="learned_digest JSON.",
                    dedupe_key=f"summarize_monetizable_directions_{hour // 4}",
                    output_contract_id="learned_digest",
                    value_tier="high",
                )
            )
        if has("longterm_planner"):
            push(
                new_task_dict(
                    archetype="evaluate_existing_objectives_for_monetization",
                    title="Evaluate planner objectives for monetization angles",
                    goal="Read active objectives; output revenue_shortlist-style opportunities tied to each.",
                    category="planning",
                    reason="External value: align long-term work with revenue or savings.",
                    priority=0.85,
                    recommended_capabilities=["module:longterm_planner"],
                    success_criteria="Structured opportunities list from planner objectives.",
                    dedupe_key=f"evaluate_objectives_monetization_{hour // 2}",
                    output_contract_id="revenue_shortlist",
                    value_tier="high",
                )
            )
        if has("tool_registry"):
            push(
                new_task_dict(
                    archetype="identify_capability_gaps",
                    title="Capability gap report (registry)",
                    goal="Compare tool registry snapshot to autonomy needs; output capability_gap_report JSON.",
                    category="maintenance",
                    reason="Operator-visible blind spots and suggested actions.",
                    priority=0.83,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="Structured gap report JSON.",
                    dedupe_key=f"identify_capability_gaps_{hour}",
                    output_contract_id="capability_gap_report",
                    value_tier="high",
                )
            )
            push(
                new_task_dict(
                    archetype="identify_idle_capabilities_with_market_value",
                    title="Idle capabilities with market value (local)",
                    goal="From registry surfaces, list monetization hypotheses as ranked opportunities JSON.",
                    category="research",
                    reason="Turn installed surfaces into operator-facing ideas.",
                    priority=0.82,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="revenue_shortlist JSON.",
                    dedupe_key=f"idle_capabilities_market_{hour // 3}",
                    output_contract_id="revenue_shortlist",
                    value_tier="high",
                )
            )
            push(
                new_task_dict(
                    archetype="generate_system_improvement_brief",
                    title="System improvement brief (registry-based)",
                    goal="From gaps, emit system_improvement_proposal JSON (weakness, fix, modules, impact, risk).",
                    category="maintenance",
                    reason="Actionable improvement artifact for the operator.",
                    priority=0.84,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="system_improvement_proposal JSON.",
                    dedupe_key=f"system_improvement_brief_{hour // 2}",
                    output_contract_id="system_improvement_proposal",
                    value_tier="high",
                )
            )
        um = list(ctx.get("underused_modules") or [])
        if um and has("tool_registry"):
            push(
                new_task_dict(
                    archetype="compare_underused_modules_value",
                    title="Compare underused modules for likely operator value",
                    goal="Rank idle modules by likely value; research_brief JSON.",
                    category="research",
                    reason="Reduce operator blind spots about dormant capabilities.",
                    priority=0.8,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="research_brief JSON.",
                    dedupe_key=f"compare_underused_{hour // 4}",
                    output_contract_id="research_brief",
                    value_tier="high",
                    underused_modules=um[:12],
                )
            )
        if ctx.get("learning_digest_worthy") and getattr(guardian, "memory", None):
            push(
                new_task_dict(
                    archetype="summarize_recent_learning_operator",
                    title="Operator learning digest (structured)",
                    goal="Recall recent memories; emit learned_digest JSON (insights, why they matter, follow-up tasks).",
                    category="learning",
                    reason="Usable guidance from learned material, not log dumps.",
                    priority=0.81,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="learned_digest JSON (handled in executor).",
                    dedupe_key=f"summarize_recent_learning_operator_{hour // 2}",
                    output_contract_id="learned_digest",
                    value_tier="high",
                )
            )
            push(
                new_task_dict(
                    archetype="learning_operator_digest",
                    title="Learning operator digest (structured)",
                    goal="Same as summarize_recent_learning_operator; alternate dedupe slot.",
                    category="learning",
                    reason="Redundant path for scheduling; structured digest only.",
                    priority=0.79,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="learned_digest JSON.",
                    dedupe_key=f"learning_operator_digest_{hour // 3}",
                    output_contract_id="learned_digest",
                    value_tier="high",
                )
            )
        if has("harvest_engine") and (ctx.get("financial_idle") or ctx.get("module_underuse")):
            push(
                new_task_dict(
                    archetype="harvest_research_brief",
                    title="Harvest → research brief (read-only)",
                    goal="Run read-only harvest report; emit research_brief JSON (topic, findings, sources, next actions).",
                    category="research",
                    reason="External-facing research artifact from financial harvest data.",
                    priority=0.86,
                    recommended_capabilities=["module:harvest_engine"],
                    success_criteria="research_brief JSON.",
                    dedupe_key=f"harvest_research_brief_{hour // 2}",
                    output_contract_id="research_brief",
                    value_tier="high",
                )
            )

    def build(self, guardian: Any, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []
        mods = getattr(guardian, "_modules", None) or {}

        def has(mod: str) -> bool:
            return mod in mods

        self._add_operator_value_tasks(guardian, ctx, tasks, has)

        # 1–2: low confidence / fallback loops → inspect capabilities (read-only)
        if ctx.get("low_confidence_streak", 0) >= 1 or ctx.get("repeated_action_streak", 0) >= 2:
            if has("tool_registry"):
                _append_task_if_fresh(
                    tasks,
                    new_task_dict(
                        archetype="validate_tool_registry_snapshot",
                        title="Validate tool registry snapshot",
                        goal="List registered tools and confirm builtin llm/web/exec surfaces exist.",
                        category="tooling",
                        reason="Decision engine confidence was low or actions repeated; refresh capability picture.",
                        priority=0.62,
                        recommended_capabilities=["module:tool_registry"],
                        success_criteria="Non-empty tool list returned; response includes structured tool ids or count ≥ 1.",
                        dedupe_key="validate_tool_registry_snapshot",
                        unlocks_task_kind="repair_tool_registry_coverage",
                    ),
                    ctx,
                )

        if ctx.get("repeated_action_streak", 0) >= int(
            self.cfg.get("repeated_action_streak_trigger", 3)
        ):
            if has("longterm_planner"):
                _append_task_if_fresh(
                    tasks,
                    new_task_dict(
                        archetype="refresh_objective_snapshot",
                        title="Refresh planner objective snapshot",
                        goal="Read active objectives count and names without modifying them.",
                        category="planning",
                        reason="Same autonomy action repeated; re-anchor on current objectives.",
                        priority=0.68,
                        recommended_capabilities=["module:longterm_planner"],
                        success_criteria="Returns objective count or list preview without error.",
                        dedupe_key="refresh_objective_snapshot",
                    ),
                    ctx,
                )

        # 3: underused modules
        if ctx.get("underused_modules"):
            for um in ctx["underused_modules"][:2]:
                if um == "longterm_planner" and has("longterm_planner"):
                    _append_task_if_fresh(
                        tasks,
                        new_task_dict(
                            archetype=f"exercise_module_{um}",
                            title=f"Exercise module: {um}",
                            goal="Read-only snapshot of planner objectives.",
                            category="planning",
                            reason="Module has been unused longer than configured threshold.",
                            priority=0.55,
                            recommended_capabilities=["module:longterm_planner"],
                            success_criteria="Structured planner data returned.",
                            dedupe_key=f"exercise_{um}_{int(time.time() // 3600)}",
                        ),
                        ctx,
                    )
                if um == "harvest_engine" and has("harvest_engine"):
                    _append_task_if_fresh(
                        tasks,
                        new_task_dict(
                            archetype="harvest_readonly_snapshot",
                            title="Harvest income snapshot (read-only)",
                            goal="Generate local income report for review only; no outbound posts.",
                            category="finance",
                            reason="Harvest module underused; bounded financial visibility.",
                            priority=0.52,
                            recommended_capabilities=["module:harvest_engine"],
                            success_criteria="Report dict returned with totals or explicit empty state.",
                            dedupe_key="harvest_readonly_snapshot",
                            unlocks_task_kind="harvest_research_brief",
                        ),
                        ctx,
                    )
                if um == "tool_registry" and has("tool_registry"):
                    _append_task_if_fresh(
                        tasks,
                        new_task_dict(
                            archetype="validate_tool_registry_snapshot",
                            title="Exercise module: tool_registry",
                            goal="List registered tools and confirm builtin llm/web/exec surfaces exist.",
                            category="tooling",
                            reason="Tool registry has been unused longer than configured threshold.",
                            priority=0.54,
                            recommended_capabilities=["module:tool_registry"],
                            success_criteria="Non-empty tool list returned or explicit structured empty-state.",
                            dedupe_key="exercise_tool_registry_snapshot",
                        ),
                        ctx,
                    )
                if um == "income_generator" and has("income_generator"):
                    _append_task_if_fresh(
                        tasks,
                        new_task_dict(
                            archetype="generate_revenue_shortlist",
                            title="Exercise module: income bundle",
                            goal="Generate a local ranked revenue shortlist from current income and wallet context.",
                            category="finance",
                            reason="Income modules have been unused longer than configured threshold.",
                            priority=0.53,
                            recommended_capabilities=["module:income_generator"],
                            success_criteria="Structured shortlist or explicit empty-state returned.",
                            dedupe_key=f"exercise_income_bundle_{int(time.time() // 3600)}",
                        ),
                        ctx,
                    )

        # 4: tool registry weak / empty
        if ctx.get("tool_registry_weak") and has("tool_registry"):
            _append_task_if_fresh(
                tasks,
                new_task_dict(
                    archetype="repair_tool_registry_coverage",
                    title="Repair tool registry coverage",
                    goal="Ensure minimal builtin tools exist and list final registry entries.",
                    category="tooling",
                    reason="Registry missing llm/web/exec class tools or mismatched expectations.",
                    priority=0.78,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="list_tools shows at least three entries including builtin stubs or equivalents.",
                    dedupe_key="repair_tool_registry_coverage",
                ),
                ctx,
            )

        # 5: API available (heuristic: env keys) — bounded routing awareness
        if ctx.get("api_unused_hint") and has("tool_registry"):
            _append_task_if_fresh(
                tasks,
                new_task_dict(
                    archetype="api_capability_smoke",
                    title="API capability inventory (local)",
                    goal="Confirm tool registry lists surfaces that could back API-backed tools; no external calls.",
                    category="maintenance",
                    reason="Cloud API keys present; verify local registry exposes matching tool entries.",
                    priority=0.5,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="Tool list retrieved; at least one tool metadata inspected locally.",
                    dedupe_key="api_capability_smoke",
                ),
                ctx,
            )

        # 6: startup / health warnings
        if ctx.get("startup_issue"):
            if has("tool_registry"):
                _append_task_if_fresh(
                    tasks,
                    new_task_dict(
                        archetype="post_startup_health_snapshot",
                        title="Post-startup health snapshot",
                        goal="Capture tool registry state after startup warning to aid diagnosis.",
                        category="maintenance",
                        reason="Startup operational state reported warnings or incomplete init.",
                        priority=0.8,
                        recommended_capabilities=["module:tool_registry"],
                        success_criteria="Tool list or error captured for logs.",
                        dedupe_key="post_startup_health_snapshot",
                    ),
                    ctx,
                )

        # 7: learning — memory recall summary (no raw log paste as goal text)
        if ctx.get("learning_digest_worthy") and getattr(guardian, "memory", None):
            _append_task_if_fresh(
                tasks,
                new_task_dict(
                    archetype="learning_recent_digest",
                    title="Digest recent autonomy memories",
                    goal="Recall last few autonomy-tagged memories and summarize themes internally.",
                    category="learning",
                    reason="Recent learning or autonomy activity should be consolidated.",
                    priority=0.52,
                    recommended_capabilities=["module:tool_registry"],
                    success_criteria="Executor records a short structured summary to memory (handled in core).",
                    dedupe_key="learning_recent_digest",
                ),
                ctx,
            )

        # 8: financial idle
        if ctx.get("financial_idle"):
            cap: List[str] = []
            if has("income_generator"):
                cap.append("module:income_generator")
            if has("wallet"):
                cap.append("module:wallet")
            if has("financial_manager"):
                cap.append("module:financial_manager")
            if cap:
                _append_task_if_fresh(
                    tasks,
                    new_task_dict(
                        archetype="finance_idle_pulse",
                        title="Financial modules dry-read",
                        goal="Read-only summary of income, wallet, or financial status; no transfers.",
                        category="finance",
                        reason="Financial modules available but idle beyond threshold.",
                        priority=0.54,
                        recommended_capabilities=cap[:2],
                        success_criteria="At least one module returns a dict summary.",
                        dedupe_key="finance_idle_pulse",
                        unlocks_task_kind="finance_revenue_shortlist",
                    ),
                    ctx,
                )

        from .self_task_objectives import ObjectiveStore

        store = ObjectiveStore()
        attach_objectives_to_tasks(guardian, tasks, store)
        max_n = int(self.cfg.get("max_generate_per_cycle", 5))
        return tasks[:max_n]


def build_context_for_guardian(
    guardian: Any,
    *,
    candidates_empty: bool,
    mistral_decision: Optional[Dict[str, Any]],
    override_reason: Optional[str],
    decider_cfg: Dict[str, Any],
    self_task_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble a safe, structured context dict (no log dumps)."""
    ctx: Dict[str, Any] = {
        "enabled": bool(self_task_cfg.get("enabled", True)),
        "idle_no_candidates": candidates_empty,
        "weak_decision": False,
        "low_confidence_streak": int(getattr(guardian, "_self_task_low_confidence_streak", 0) or 0),
        "repeated_action_streak": int(getattr(guardian, "_mistral_repeated_action_count", 0) or 0),
        "stale_self_task_archetypes": [],
        "stale_monetization_loop": False,
    }
    thr = float(decider_cfg.get("mistral_decision_confidence_threshold", 0.5))
    if mistral_decision is not None:
        conf = float(mistral_decision.get("confidence", 1.0) or 1.0)
        if conf < thr or (override_reason or "") in (
            "low_confidence",
            "invalid_action",
            "low_confidence_force_capability",
        ):
            ctx["weak_decision"] = True
    try:
        op = guardian.get_startup_operational_state()
        ctx["startup_issue"] = bool(
            op.get("deferred_init_failed")
            or op.get("vector_degraded")
            or op.get("vector_rebuild_pending")
            or op.get("deferred_init_state") in ("failed", "inconsistent")
        )
    except Exception:
        ctx["startup_issue"] = False

    tr = (getattr(guardian, "_modules", None) or {}).get("tool_registry")
    try:
        if tr and hasattr(tr, "ensure_minimal_builtin_tools"):
            tr.ensure_minimal_builtin_tools()
    except Exception:
        pass
    ctx["tool_registry_weak"] = False
    try:
        if tr:
            ctx["tool_registry_weak"] = not bool(guardian._tool_registry_minimal_capabilities_ok(tr))
    except Exception:
        ctx["tool_registry_weak"] = True

    try:
        from .cloud_api_state import any_llm_cloud_key_loaded

        ctx["api_unused_hint"] = bool(any_llm_cloud_key_loaded())
    except Exception:
        import os

        ctx["api_unused_hint"] = bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))

    hours = float(self_task_cfg.get("underuse_module_hours", 2.0))
    ctx["underused_modules"] = _underused_modules(guardian, hours)
    ctx["module_underuse"] = len(ctx["underused_modules"]) > 0

    ctx["financial_idle"] = _financial_idle(guardian, min_idle_sec=45 * 60)

    ctx["learning_digest_worthy"] = bool(getattr(guardian, "_last_introspection_result", None))

    try:
        from .mission_autonomy import MissionAutonomyStore

        store = MissionAutonomyStore()
        stale_arches: List[str] = []
        stale_monetization = False
        seen: List[str] = []
        for rec in store.recent_artifacts(limit=8):
            arch = str(rec.get("archetype") or "").strip()
            if arch and arch not in seen:
                seen.append(arch)
        for arch in seen:
            sig = store.recent_archetype_signal(arch, limit=8)
            if int(sig.get("non_adv_useful_streak", 0) or 0) < 2:
                continue
            stale_arches.append(arch)
            if _is_monetization_like_archetype(arch):
                stale_monetization = True
        ctx["stale_self_task_archetypes"] = stale_arches[:8]
        ctx["stale_monetization_loop"] = stale_monetization
    except Exception:
        pass

    return ctx


def _underused_modules(guardian: Any, min_hours: float) -> List[str]:
    mods = getattr(guardian, "_modules", None) or {}
    candidates = [
        "longterm_planner",
        "harvest_engine",
        "fractalmind",
        "income_generator",
        "tool_registry",
    ]
    out: List[str] = []
    used = getattr(guardian, "_module_last_invoked", {}) or {}
    for m in candidates:
        if m not in mods:
            continue
        age_min = activity_age_minutes(used, m, now=datetime.now(timezone.utc))
        if age_min is None:
            out.append(m)
            continue
        if age_min > min_hours * 60:
            out.append(m)
    return out


def _financial_idle(guardian: Any, min_idle_sec: float) -> bool:
    mods = getattr(guardian, "_modules", None) or {}
    if not any(k in mods for k in ("income_generator", "wallet", "financial_manager")):
        return False
    used = getattr(guardian, "_module_last_invoked", {}) or {}
    age_min = activity_age_minutes(used, "income_modules", now=datetime.now(timezone.utc))
    if age_min is None:
        return True
    return age_min * 60 > min_idle_sec


def maybe_fork_objective_for_repeated_archetype(
    store: Any,
    queue: SelfTaskQueue,
    task: Dict[str, Any],
) -> None:
    """If two+ pending tasks share this archetype, assign a fresh lightweight objective."""
    from .self_task_objectives import ObjectiveStore

    if not isinstance(store, ObjectiveStore):
        return
    arch = str(task.get("archetype") or "")
    if not arch:
        return
    pend = [
        x
        for x in queue._data.get("tasks", [])
        if x.get("status") == "pending" and str(x.get("archetype") or "") == arch
    ]
    if len(pend) < 2:
        return
    oid = store.create_lightweight(
        title=f"Repeated pattern: {arch[:48]}",
        goal=f"Convert repeated {arch} work into concrete forward progress.",
        priority=0.52,
        objective_type="operator_support",
    )
    task["objective_id"] = oid


def enqueue_generated(
    queue: SelfTaskQueue,
    tasks: List[Dict[str, Any]],
    cooldown_sec: float,
    guardian: Optional[Any] = None,
    objective_store: Optional[Any] = None,
) -> int:
    from .self_task_objectives import ObjectiveStore

    st: Optional[ObjectiveStore] = None
    if objective_store is not None and isinstance(objective_store, ObjectiveStore):
        st = objective_store
    elif guardian is not None or any(t.get("objective_id") for t in tasks):
        st = ObjectiveStore()
    if guardian is not None and st is not None:
        attach_objectives_to_tasks(guardian, tasks, st)
    n = 0
    for t in tasks:
        if st is not None:
            maybe_fork_objective_for_repeated_archetype(st, queue, t)
        dk = t.get("dedupe_key") or t.get("archetype", "unknown")
        if queue.enqueue(t, dedupe_key=str(dk), cooldown_sec=cooldown_sec):
            n += 1
            oid = t.get("objective_id")
            tid = t.get("task_id")
            if st is not None and oid and tid:
                st.link_task(str(oid), str(tid))
    return n
