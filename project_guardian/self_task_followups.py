# project_guardian/self_task_followups.py
# Chained follow-up tasks after self-task completion (bounded).

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .self_task_generator import enrich_task_metadata, new_task_dict
from .self_task_queue import SelfTaskQueue
from .self_task_execution_outcome import is_execution_stage_archetype

logger = logging.getLogger(__name__)


def _arch_failures(queue: SelfTaskQueue, archetype: str) -> int:
    data = getattr(queue, "_data", {}) or {}
    return int(data.get("archetype_failures", {}).get(archetype, 0) or 0)


def _record_arch_failure(queue: SelfTaskQueue, archetype: str) -> None:
    data = queue._data.setdefault("archetype_failures", {})
    data[archetype] = int(data.get(archetype, 0) or 0) + 1
    queue._save()


def maybe_enqueue_followups(
    guardian: Any,
    completed_task: Dict[str, Any],
    *,
    execution_tier: str,
    useful: bool,
    objective_advanced: bool = False,
    operator_ready: bool = False,
    execution_ready: bool = False,
    queue: SelfTaskQueue,
    objective_store: Any,
    st_cfg: Dict[str, Any],
    cooldown_sec: float,
) -> int:
    """Enqueue at most one follow-up success task or one diagnostic on failure."""
    arch = str(completed_task.get("archetype") or "")
    oid = completed_task.get("objective_id")
    mods = getattr(guardian, "_modules", None) or {}

    def has(m: str) -> bool:
        return m in mods

    n = 0
    max_retry = int(st_cfg.get("followup_max_retries_per_archetype", 2))

    if execution_tier == "failed" or (execution_tier == "weak" and not useful):
        if _arch_failures(queue, arch) >= max_retry:
            return 0
        _record_arch_failure(queue, arch)
        if arch and has("tool_registry"):
            t = new_task_dict(
                archetype=f"{arch}_diagnostic_retry",
                title=f"Diagnostic: {arch}",
                goal="Re-run a minimal read-only tool registry list after prior failure.",
                category="maintenance",
                reason="Prior self-task failed or weak; bounded diagnostic.",
                priority=0.45,
                recommended_capabilities=["module:tool_registry"],
                success_criteria="Non-empty tool list or explicit error captured.",
                dedupe_key=f"diag_{arch}_{int(time.time() // 7200)}",
            )
            t["task_kind"] = "diagnostic"
            t["follows_task_id"] = completed_task.get("task_id")
            t["objective_id"] = oid
            if queue.enqueue(t, dedupe_key=t["dedupe_key"], cooldown_sec=cooldown_sec):
                n += 1
                if oid:
                    objective_store.link_task(oid, t["task_id"])
        return n

    if execution_tier != "strong" or not useful:
        return 0

    if not objective_advanced:
        return 0

    exo_chk = str(completed_task.get("execution_outcome") or "none").lower()
    vv_chk = bool(completed_task.get("value_verified"))
    if is_execution_stage_archetype(arch) and exo_chk == "succeeded" and not vv_chk:
        return 0

    if operator_ready:
        return 0

    revenue_chain = (
        "generate_revenue_shortlist",
        "finance_revenue_shortlist",
        "create_small_dry_run_offer_ideas",
    )
    if arch in revenue_chain:
        chain_tasks = [
            new_task_dict(
                archetype="rank_top_opportunities",
                title="Rank opportunities (post-shortlist)",
                goal="Rank opportunities from latest briefs; tool:opportunity_ranker.",
                category="finance",
                reason="Revenue chain: order by expected value.",
                priority=0.81,
                recommended_capabilities=["tool:opportunity_ranker"],
                success_criteria="Ranked dict.",
                dedupe_key=f"rank_top_opportunities_chain_{arch}",
            ),
            new_task_dict(
                archetype="execute_best_opportunity",
                title="Plan best opportunity",
                goal="Emit execution plan for top item; tool:revenue_executor.",
                category="finance",
                reason="Revenue chain: action plan.",
                priority=0.8,
                recommended_capabilities=["tool:revenue_executor"],
                success_criteria="execution_plan dict.",
                dedupe_key=f"execute_best_opportunity_chain_{arch}",
            ),
            new_task_dict(
                archetype="generate_execution_plan",
                title="Generate execution plan",
                goal="Structured multi-phase plan (local only).",
                category="finance",
                reason="Revenue chain: finalize plan.",
                priority=0.79,
                recommended_capabilities=["tool:revenue_executor"],
                success_criteria="execution_plan JSON.",
                dedupe_key=f"generate_execution_plan_chain_{arch}",
            ),
        ]
        for f in chain_tasks:
            f["objective_id"] = oid
            f["follows_task_id"] = completed_task.get("task_id")
            enrich_task_metadata(f)
            if queue.enqueue(f, dedupe_key=f.get("dedupe_key", ""), cooldown_sec=cooldown_sec):
                n += 1
                if oid:
                    objective_store.link_task(oid, f["task_id"])
                logger.info("[SelfTask] revenue chain enqueued %s -> %s", arch, f.get("archetype"))
        if n > 0:
            return n

    follow: Optional[Dict[str, Any]] = None

    if arch == "validate_tool_registry_snapshot" and has("tool_registry"):
        follow = new_task_dict(
            archetype="repair_tool_registry_coverage",
            title="Repair tool registry coverage",
            goal="Ensure minimal builtin tools exist and list final registry entries.",
            category="tooling",
            reason="Follow-up: validation succeeded; reinforce registry coverage.",
            priority=0.74,
            recommended_capabilities=["module:tool_registry"],
            success_criteria="list_tools shows at least three entries including builtin stubs or equivalents.",
            dedupe_key="repair_tool_registry_coverage",
        )
        follow["task_kind"] = "improvement"

    elif arch == "harvest_readonly_snapshot" and has("harvest_engine"):
        follow = new_task_dict(
            archetype="harvest_research_brief",
            title="Harvest → research brief (read-only)",
            goal="Emit research_brief JSON from harvest report (topic, findings, sources, next actions).",
            category="research",
            reason="Follow-up: harvest snapshot succeeded; operator-facing brief.",
            priority=0.78,
            recommended_capabilities=["module:harvest_engine"],
            success_criteria="research_brief contract JSON.",
            dedupe_key="harvest_research_brief_followup",
            output_contract_id="research_brief",
            value_tier="high",
        )
        follow["task_kind"] = "generation"

    elif arch == "finance_idle_pulse":
        caps = []
        if has("income_generator"):
            caps.append("module:income_generator")
        if caps:
            follow = new_task_dict(
                archetype="finance_revenue_shortlist",
                title="Revenue opportunity shortlist (local)",
                goal="Structured revenue_shortlist JSON from income summary; no outbound sends.",
                category="finance",
                reason="Follow-up: financial idle pulse; ranked opportunities for operator.",
                priority=0.72,
                recommended_capabilities=caps[:1],
                success_criteria="revenue_shortlist contract JSON.",
                dedupe_key="finance_revenue_shortlist",
                output_contract_id="revenue_shortlist",
                value_tier="high",
            )
            follow["task_kind"] = "generation"

    if follow:
        follow["objective_id"] = oid
        follow["follows_task_id"] = completed_task.get("task_id")
        follow.setdefault("task_kind", "transform")
        enrich_task_metadata(follow)
        if queue.enqueue(follow, dedupe_key=follow.get("dedupe_key", ""), cooldown_sec=cooldown_sec):
            n += 1
            if oid:
                objective_store.link_task(oid, follow["task_id"])
            logger.info("[SelfTask] follow-up enqueued %s -> %s", arch, follow.get("archetype"))

    return n


def maybe_enqueue_execution_outcome_followups(
    guardian: Any,
    completed_task: Dict[str, Any],
    *,
    queue: SelfTaskQueue,
    objective_store: Any,
    st_cfg: Dict[str, Any],
    cooldown_sec: float,
) -> int:
    """Bounded follow-ups after execution outcome (uses existing archetypes only)."""
    arch = str(completed_task.get("archetype") or "")
    if not is_execution_stage_archetype(arch):
        return 0
    exo = str(completed_task.get("execution_outcome") or "none").lower()
    need = bool(completed_task.get("execution_followup_needed"))
    oid = completed_task.get("objective_id")
    mods = getattr(guardian, "_modules", None) or {}

    if exo in ("succeeded", "none", "readiness_only"):
        return 0

    n = 0
    if exo == "failed" and need:
        reason = str(completed_task.get("execution_reason") or "").strip()
        if len(reason) < 8:
            return 0
        if "tool_registry" not in mods:
            return 0
        t = new_task_dict(
            archetype=f"{arch}_diagnostic_retry",
            title=f"Bounded repair after execution failure ({arch})",
            goal=f"Minimal diagnostic after execution failure: {reason[:280]}",
            category="maintenance",
            reason="Post-execution failure with recorded cause.",
            priority=0.44,
            recommended_capabilities=["module:tool_registry"],
            success_criteria="Non-empty tool list or explicit error captured.",
            dedupe_key=f"exec_fail_repair_{arch}_{int(time.time() // 7200)}",
        )
        t["task_kind"] = "diagnostic"
        t["follows_task_id"] = completed_task.get("task_id")
        t["objective_id"] = oid
        enrich_task_metadata(t)
        if queue.enqueue(t, dedupe_key=t["dedupe_key"], cooldown_sec=cooldown_sec):
            n += 1
            if oid:
                objective_store.link_task(oid, t["task_id"])
            logger.info("[SelfTask] execution failure follow-up enqueued for %s", arch)
        return n

    if exo == "partial" and need and bool(completed_task.get("value_verified")):
        t = new_task_dict(
            archetype="generate_execution_plan",
            title="Completion pass after partial execution",
            goal="Tighten execution plan after partial execution outcome (local only).",
            category="finance",
            reason="Single completion step after partial execution.",
            priority=0.77,
            recommended_capabilities=["tool:revenue_executor"],
            success_criteria="execution_plan JSON.",
            dedupe_key=f"exec_partial_completion_{oid or arch}_{int(time.time() // 3600)}",
        )
        t["objective_id"] = oid
        t["follows_task_id"] = completed_task.get("task_id")
        enrich_task_metadata(t)
        if queue.enqueue(t, dedupe_key=t.get("dedupe_key", ""), cooldown_sec=cooldown_sec):
            n += 1
            if oid:
                objective_store.link_task(oid, t["task_id"])
            logger.info("[SelfTask] partial execution completion task enqueued for %s", arch)

    return n
