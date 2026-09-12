# project_guardian/brain/pipeline.py
# Composition root: wires brain modules and logs every transition.
#
# Note on ordering vs the design sketch: risk is evaluated on the *concrete*
# routed capability (after the tool router) so blocked patterns apply to the
# actual execution target. LLM routing stays advisory and uses the planner hint.

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .contracts import (
    BrainPipelineTrace,
    ExecutionResult,
    Observation,
    RiskAssessment,
    RiskLevel,
    StructuredCommand,
    ToolRouteDecision,
)
from .context_builder_module import default_context_builder
from .dashboard_module import DefaultDashboardModule
from .execution_module import CapabilityExecutionFacade
from .learning_module import DefaultLearningModule
from .llm_router_module import UnifiedLLMRouterFacade
from .memory_module import GuardianMemoryFacade, InMemoryBrainStore
from .planner_module import HeuristicPlannerModule
from .risk_module import KeywordRiskChecker
from .self_improvement_module import JsonlSelfImprovementQueue
from .tool_router_module import DefaultToolRouterModule

from project_guardian.prompt_contracts.integration import (
    add_prompt_contract_result_to_trace,
    brain_learning_outcome_to_projection,
    brain_llm_router_choice_to_projection,
    brain_plan_to_contract_projection,
    brain_risk_to_contract_projection,
    brain_tool_route_to_projection,
    memory_ranking_run_context_to_projection,
    resolve_prompt_contract_payload,
    should_validate_prompt_contracts,
    validate_module_output_for_trace,
)

logger = logging.getLogger(__name__)

_TRACE_PATH = Path(__file__).resolve().parents[2] / "data" / "runtime" / "brain_last_pipeline.json"


def _transition(trace: BrainPipelineTrace, step: str, detail: str = "") -> None:
    trace.transitions.append(step)
    if detail:
        logger.info("brain.transition %s | %s", step, detail[:500])
    else:
        logger.info("brain.transition %s", step)


def _persist_trace(trace: BrainPipelineTrace, *, path: Optional[Path] = None) -> None:
    out_path = path or _TRACE_PATH
    try:
        from .think_decide_act_adapter import build_unified_export

        unified = build_unified_export(trace)
        trace.unified_export = unified
        from .tda_trace_fields import apply_persisted_tda_fields

        payload = {
            "brain_pipeline_id": trace.brain_pipeline_id,
            "started_at": trace.started_at,
            "input_source": trace.input_source,
            "transitions": trace.transitions,
            "context_preview": trace.context_preview[:1200],
            "memory_snippets": trace.memory_snippets[:12],
            "plan_goal": trace.plan.goal_summary if trace.plan else "",
            "llm_backend": trace.llm_backend,
            "llm_reason": trace.llm_reason,
            "risk": trace.risk.level.value if trace.risk else None,
            "risk_reason": trace.risk.reason if trace.risk else None,
            "tool_selected": trace.tool_route.selected if trace.tool_route else None,
            "tool_fallback": trace.tool_route.used_fallback if trace.tool_route else None,
            "execution_ok": trace.execution.success if trace.execution else None,
            "execution_error": trace.execution.error if trace.execution else None,
            "lesson_preview": trace.learning.lesson[:400] if trace.learning else None,
            "use_think_decide_act": bool((trace.run_context or {}).get("use_think_decide_act")),
            "dry_run": bool((trace.run_context or {}).get("dry_run")),
            "unified_export": unified,
        }
        apply_persisted_tda_fields(payload, trace)
        try:
            from project_guardian.prompt_contracts.controls import (
                compact_prompt_contract_validation_for_persist,
            )

            pvc = compact_prompt_contract_validation_for_persist(trace.run_context)
            if pvc:
                payload["prompt_contract_validation"] = pvc
        except Exception:
            pass
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.debug("brain.trace persist skipped: %s", e)


class BrainPipeline:
    def __init__(
        self,
        *,
        guardian: Optional[Any] = None,
        memory: Optional[Any] = None,
        context_builder: Optional[Any] = None,
        planner: Optional[Any] = None,
        llm_router: Optional[Any] = None,
        tool_router: Optional[Any] = None,
        risk_checker: Optional[Any] = None,
        execution: Optional[Any] = None,
        learning: Optional[Any] = None,
        self_improvement: Optional[Any] = None,
        dashboard: Optional[Any] = None,
    ) -> None:
        self.guardian = guardian
        if memory is not None:
            self.memory = memory
        elif guardian is not None and getattr(guardian, "memory", None) is not None:
            self.memory = GuardianMemoryFacade(guardian.memory)
        else:
            self.memory = InMemoryBrainStore()

        self.context_builder = context_builder or default_context_builder(guardian)
        self.planner = planner or HeuristicPlannerModule()
        self.llm_router = llm_router or UnifiedLLMRouterFacade()
        self.tool_router = tool_router or DefaultToolRouterModule()
        self.risk_checker = risk_checker or KeywordRiskChecker()
        self.execution = execution or CapabilityExecutionFacade()
        self.learning = learning or DefaultLearningModule()
        self.self_improvement = self_improvement or JsonlSelfImprovementQueue()
        self.dashboard = dashboard or DefaultDashboardModule()

    def _abort_strict_planner_contract(
        self,
        trace: BrainPipelineTrace,
        observation: Observation,
        plan: Any,
        ctx: Dict[str, Any],
        out_path: Path,
        persist: bool,
    ) -> Tuple[BrainPipelineTrace, Dict[str, Any]]:
        """Early-exit path when strict+dry planner contract validation fails."""
        trace.llm_backend = "skipped"
        trace.llm_reason = "prompt_contract_strict_abort_planner"
        trace.tool_route = ToolRouteDecision(
            primary="brain:noop",
            selected="brain:noop",
            used_fallback=True,
            reason="prompt_contract_strict_abort_planner",
            extras={},
        )
        trace.risk = RiskAssessment(RiskLevel.BLOCKED, "prompt_contract_strict_abort_planner", {})
        ex_for_learning = ExecutionResult(False, {}, error="prompt_contract_strict_abort_planner")
        trace.execution = ex_for_learning
        rank_ctx: Dict[str, Any] = {**ctx, "failure_related": True}
        if plan:
            rank_ctx["plan_goal_hint"] = (plan.goal_summary or "")[:800]
        if hasattr(self.learning, "bind_pipeline_context"):
            try:
                self.learning.bind_pipeline_context(rank_ctx)
            except Exception:
                pass
        try:
            learn = self.learning.review_outcome(observation, plan, ex_for_learning, self.memory)
        finally:
            if hasattr(self.learning, "bind_pipeline_context"):
                try:
                    self.learning.bind_pipeline_context(None)
                except Exception:
                    pass
        trace.learning = learn
        _transition(trace, "prompt_contract_strict_abort_planner", "")
        self.self_improvement.enqueue(learn, trace)
        dash = self.dashboard.snapshot(trace)
        _transition(trace, "dashboard_snapshot", "")
        if persist:
            _persist_trace(trace, path=out_path)
        else:
            from .think_decide_act_adapter import build_unified_export

            trace.unified_export = build_unified_export(trace)
        return trace, dash

    def run(
        self,
        observation: Observation,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[BrainPipelineTrace, Dict[str, Any]]:
        trace = BrainPipelineTrace()
        ctx = dict(context or {})
        trace.brain_pipeline_id = uuid.uuid4().hex
        trace.started_at = datetime.now(timezone.utc).isoformat()
        trace.input_source = observation.source
        trace.observation_preview = observation.text[:800]
        trace.run_context = {
            "use_think_decide_act": bool(ctx.get("use_think_decide_act", False)),
            "dry_run": bool(ctx.get("dry_run", False)),
            "persist_trace": bool(ctx.get("persist_trace", True)),
            "trace_path": str(ctx.get("trace_path") or str(_TRACE_PATH)),
            "source_entrypoint": str(ctx.get("source_entrypoint") or ""),
        }
        for key in (
            "validate_prompt_contracts",
            "prompt_contract_mode",
            "prompt_contract_modules",
            "prompt_contract_overrides",
            "dry_validate_planner_contract",
            "dry_validate_planner_contract_sample",
        ):
            if key in ctx:
                trace.run_context[key] = ctx[key]

        reg = getattr(self.guardian, "_module_registry", None) if self.guardian else None
        use_tda = bool(ctx.get("use_think_decide_act", False))
        dry_run = bool(ctx.get("dry_run", False))

        _transition(trace, "observation_received", observation.source)
        bctx = self.context_builder.build(observation, self.memory)
        trace.context_preview = bctx[:2000]
        _transition(trace, "context_built", f"len={len(bctx)}")

        snippets = self.memory.retrieve(observation.text[:800], limit=10)
        trace.memory_snippets = snippets
        _transition(trace, "memory_retrieved", f"n={len(snippets)}")

        if ctx.get("rank_memory"):
            try:
                from project_guardian.memory_ranking import get_memory_ranking_config, rank_memories_from_snippets

                ranked_memory = rank_memories_from_snippets(
                    snippets,
                    get_memory_ranking_config(),
                    current_goal_text=observation.text[:2000],
                )
                trace.run_context["memory_ranking"] = {
                    "enabled": True,
                    "count": len(ranked_memory),
                    "top_ids": [item.memory_id for item in ranked_memory[:3]],
                    "top_scores": [round(item.memory_value_score, 3) for item in ranked_memory[:3]],
                }
                _transition(trace, "memory_ranked", f"n={len(ranked_memory)}")
                if should_validate_prompt_contracts(ctx, "memory_ranker"):
                    mr = trace.run_context["memory_ranking"]
                    payload = resolve_prompt_contract_payload(
                        ctx,
                        "memory_ranker",
                        lambda: memory_ranking_run_context_to_projection(mr),
                    )
                    res_mr = validate_module_output_for_trace("memory_ranker", payload, ctx)
                    add_prompt_contract_result_to_trace(trace, "memory_ranker", res_mr)
            except Exception as e:
                logger.warning("brain.memory ranking skipped: %s", e)
                trace.run_context["memory_ranking"] = {"enabled": True, "error": str(e)[:200]}

        plan = self.planner.plan(observation, snippets, bctx)
        trace.plan = plan
        _transition(trace, "planner_finished", f"steps={len(plan.steps)}")

        if should_validate_prompt_contracts(ctx, "planner"):
            payload = resolve_prompt_contract_payload(
                ctx,
                "planner",
                lambda: brain_plan_to_contract_projection(plan),
            )
            res_plan = validate_module_output_for_trace("planner", payload, ctx)
            add_prompt_contract_result_to_trace(trace, "planner", res_plan)
            trace.run_context["planner_contract_validation"] = {
                "ok": res_plan["valid"],
                "errors": res_plan["errors"],
            }
            if res_plan.get("blocked"):
                trace.run_context["prompt_contract_strict_gate_failed"] = "planner"

        if trace.run_context.get("prompt_contract_strict_gate_failed") == "planner":
            persist_early = bool(ctx.get("persist_trace", True))
            tp_early = ctx.get("trace_path")
            out_early = Path(str(tp_early)) if tp_early else _TRACE_PATH
            return self._abort_strict_planner_contract(trace, observation, plan, ctx, out_early, persist_early)

        backend, why = self.llm_router.choose_backend(
            user_text=observation.text,
            router_task_type=plan.router_task_type,
            risk_level=RiskLevel.LOW,
            registry=reg,
        )
        trace.llm_backend = backend
        trace.llm_reason = why
        _transition(trace, "llm_router_chose", f"{backend}:{why[:120]}")
        if should_validate_prompt_contracts(ctx, "llm_router"):
            payload_lr = resolve_prompt_contract_payload(
                ctx,
                "llm_router",
                lambda: brain_llm_router_choice_to_projection(backend, why),
            )
            res_lr = validate_module_output_for_trace("llm_router", payload_lr, ctx)
            add_prompt_contract_result_to_trace(trace, "llm_router", res_lr)

        route = self.tool_router.route(observation, plan, guardian=self.guardian)
        trace.tool_route = route
        _transition(trace, "tool_router_decided", route.selected)
        if should_validate_prompt_contracts(ctx, "tool_router"):
            payload_tr = resolve_prompt_contract_payload(
                ctx,
                "tool_router",
                lambda: brain_tool_route_to_projection(route),
            )
            res_tr = validate_module_output_for_trace("tool_router", payload_tr, ctx)
            add_prompt_contract_result_to_trace(trace, "tool_router", res_tr)

        cmd = StructuredCommand(
            capability_ref=route.selected,
            payload={"objective": observation.text[:4000], "source": observation.source},
            audit_label=plan.goal_summary[:500],
        )
        risk = self.risk_checker.review(observation, plan, cmd)
        trace.risk = risk
        _transition(trace, "risk_checked", f"{risk.level.value}:{risk.reason}")
        if should_validate_prompt_contracts(ctx, "risk_checker"):
            payload_rc = resolve_prompt_contract_payload(
                ctx,
                "risk_checker",
                lambda: brain_risk_to_contract_projection(risk),
            )
            res_rc = validate_module_output_for_trace("risk_checker", payload_rc, ctx)
            add_prompt_contract_result_to_trace(trace, "risk_checker", res_rc)

        adapter_used = False
        tda_trace = None
        if risk.level in (RiskLevel.BLOCKED, RiskLevel.HIGH):
            trace.execution = None
            _transition(trace, "execution_skipped", risk.reason)
            ex_for_learning = ExecutionResult(False, {}, error="skipped_for_risk")
        else:
            tda_ok = False
            if use_tda:
                try:
                    from .think_decide_act_adapter import is_brain_tda_adapter_available

                    tda_ok = is_brain_tda_adapter_available()
                except Exception as e:
                    logger.warning("brain.tda adapter import failed: %s", e)
                    tda_ok = False

            if use_tda and tda_ok:
                adapter_used = True
                _transition(trace, "think_decide_act_enter", f"dry_run={dry_run}")
                from .think_decide_act_adapter import (
                    run_tda_for_brain_action,
                    tda_trace_to_execution_result,
                    tda_trace_to_learning_outcome,
                )

                tda_trace = run_tda_for_brain_action(
                    brain_observation=observation,
                    structured_command=cmd,
                    tool_route=route,
                    brain_risk=risk,
                    planner_plan=plan,
                    guardian=self.guardian,
                    memory=self.memory,
                    dry_run=dry_run,
                    extra_context=ctx,
                )
                d = tda_trace.to_dict()
                trace.think_decide_act_trace = d
                ex_for_learning = tda_trace_to_execution_result(tda_trace)
                trace.execution = ex_for_learning
                _transition(
                    trace,
                    "think_decide_act_finished",
                    f"validation={tda_trace.validation.approved} exec={tda_trace.execution.success}",
                )
            else:
                if use_tda and not tda_ok:
                    logger.warning("brain.tda requested but unavailable; using direct execution")
                    _transition(trace, "think_decide_act_fallback", "adapter_unavailable")
                if dry_run and not (use_tda and tda_ok):
                    ex_for_learning = ExecutionResult(False, {}, error="dry_run_skipped_direct_execution")
                    trace.execution = ex_for_learning
                    _transition(trace, "execution_skipped", "dry_run_without_tda_or_adapter")
                else:
                    ex_for_learning = self.execution.execute(self.guardian, cmd, risk=risk, route=route)
                    trace.execution = ex_for_learning
                    _transition(trace, "execution_finished", f"ok={ex_for_learning.success}")

        rank_ctx: Dict[str, Any] = {**ctx}
        rank_ctx["failure_related"] = not bool(ex_for_learning.success)
        if plan:
            rank_ctx["plan_goal_hint"] = (plan.goal_summary or "")[:800]
        if hasattr(self.learning, "bind_pipeline_context"):
            try:
                self.learning.bind_pipeline_context(rank_ctx)
            except Exception:
                pass
        try:
            if adapter_used and tda_trace is not None:
                from .think_decide_act_adapter import tda_trace_to_learning_outcome

                learn = tda_trace_to_learning_outcome(tda_trace, trace.brain_pipeline_id)
                if not learn.worked:
                    try:
                        from project_guardian.memory_ranking import optional_remember_extras_for_pipeline

                        _rk = optional_remember_extras_for_pipeline(learn.lesson, rank_ctx)
                        self.memory.remember(learn.lesson, category="brain_lesson", priority=0.5, **_rk)
                    except Exception as e:
                        logger.debug("brain.learning remember after tda failure: %s", e)
            else:
                learn = self.learning.review_outcome(observation, plan, ex_for_learning, self.memory)
        finally:
            if hasattr(self.learning, "bind_pipeline_context"):
                try:
                    self.learning.bind_pipeline_context(None)
                except Exception:
                    pass
        trace.learning = learn
        if should_validate_prompt_contracts(ctx, "learning_reviewer"):
            payload_lv = resolve_prompt_contract_payload(
                ctx,
                "learning_reviewer",
                lambda: brain_learning_outcome_to_projection(learn),
            )
            res_lv = validate_module_output_for_trace("learning_reviewer", payload_lv, ctx)
            add_prompt_contract_result_to_trace(trace, "learning_reviewer", res_lv)
        _transition(trace, "learning_finished", learn.lesson[:160])

        self.self_improvement.enqueue(learn, trace)
        _transition(trace, "self_improvement_enqueued", "")

        dash = self.dashboard.snapshot(trace)
        _transition(trace, "dashboard_snapshot", "")
        persist = bool(ctx.get("persist_trace", True))
        tp = ctx.get("trace_path")
        out_path = Path(str(tp)) if tp else _TRACE_PATH
        if persist:
            _persist_trace(trace, path=out_path)
        else:
            from .think_decide_act_adapter import build_unified_export

            trace.unified_export = build_unified_export(trace)
        return trace, dash
