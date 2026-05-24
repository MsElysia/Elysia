# project_guardian/brain/think_decide_act_adapter.py
"""Bridge BrainPipeline to Think-Decide-Act without duplicating execution or safety stages."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from .contracts import (
    ExecutionResult,
    Observation,
    Plan,
    RiskAssessment,
    RiskLevel,
    StructuredCommand,
    ToolRouteDecision,
)

logger = logging.getLogger(__name__)


CONTRACT_CONCEPT_MAP: Dict[str, str] = {
    "Observation": "Observation",
    "Plan/PlanStep": "ThoughtSummary or ActionProposal",
    "StructuredCommand": "ActionProposal",
    "RiskAssessment": "ValidationResult",
    "ExecutionResult": "ExecutionLogEntry",
    "LearningOutcome": "ReviewResult",
    "Memory write": "MemoryRecord",
}


@dataclass
class BrainTDAResult:
    risk: RiskAssessment
    execution_for_trace: Optional[ExecutionResult]
    execution_for_learning: ExecutionResult
    learning: Any
    tda_trace: Dict[str, Any]


def validate_contract_concept_map() -> Dict[str, Any]:
    """Lightweight drift check for the BrainPipeline <-> TDA adapter concepts."""
    try:
        from project_guardian.orchestration import think_decide_act as tda
    except Exception as exc:
        return {"ok": False, "missing": ["think_decide_act"], "error": str(exc)}

    missing = []
    for name in (
        "Observation",
        "ActionProposal",
        "ValidationResult",
        "ExecutionLogEntry",
        "ReviewResult",
        "MemoryRecord",
    ):
        if not hasattr(tda, name):
            missing.append(name)
    expected_keys = {
        "Observation",
        "Plan/PlanStep",
        "StructuredCommand",
        "RiskAssessment",
        "ExecutionResult",
        "LearningOutcome",
        "Memory write",
    }
    missing.extend(sorted(expected_keys - set(CONTRACT_CONCEPT_MAP)))
    return {
        "ok": not missing,
        "missing": missing,
        "map": dict(CONTRACT_CONCEPT_MAP),
    }


def is_think_decide_act_available() -> bool:
    try:
        from project_guardian.orchestration.think_decide_act import run_think_decide_act_pipeline  # noqa: F401

        return True
    except Exception:
        return False


def is_brain_tda_adapter_available() -> bool:
    return is_think_decide_act_available()


def brain_risk_to_tda_estimated_risk(risk: RiskAssessment) -> str:
    return risk.level.value


class BrainCapabilityExecutor:
    """Approved executor for TDA: runs only ``execute_capability`` (no shell)."""

    def __init__(self, guardian: Any) -> None:
        self.guardian = guardian

    def execute(self, proposal: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        del context
        from project_guardian.capability_execution import execute_capability

        ref = str(getattr(proposal, "target_module_or_tool", "") or "").strip()
        payload = dict(getattr(proposal, "inputs", None) or {})
        if not ref:
            return {"success": False, "error": "empty_capability_ref"}
        if self.guardian is None:
            return {"success": False, "error": "no_guardian_for_capability_executor"}
        try:
            return execute_capability(self.guardian, ref, payload)
        except Exception as exc:
            logger.exception("BrainCapabilityExecutor.execute failed ref=%s", ref)
            return {"success": False, "error": str(exc)[:1000]}


def build_preferred_action_proposal(
    *,
    observation: Observation,
    command: StructuredCommand,
    route: ToolRouteDecision,
    brain_risk: RiskAssessment,
    plan: Plan,
) -> Any:
    from project_guardian.orchestration.think_decide_act import ActionProposal

    inputs = dict(command.payload)
    inputs["brain_capability_ref"] = command.capability_ref
    inputs["brain_route_primary"] = route.primary
    inputs["brain_route_selected"] = route.selected
    inputs["brain_route_used_fallback"] = route.used_fallback
    inputs["brain_plan_goal"] = plan.goal_summary[:2000]
    inputs["brain_audit_label"] = (command.audit_label or "")[:2000]

    risk_s = brain_risk_to_tda_estimated_risk(brain_risk)
    target = command.capability_ref
    if target == "brain:noop" or target.startswith("brain:"):
        target = "safe_noop"
    return ActionProposal(
        action_type="brain_capability_execute",
        target_module_or_tool=target,
        inputs=inputs,
        expected_result="Execute brain-routed capability via Guardian bridge.",
        estimated_risk=risk_s,
        fallback_action=None,
        reason_summary=f"BrainPipeline routed to {route.selected} (primary={route.primary}); brain_risk={risk_s}.",
    )


def run_tda_for_brain_action(
    *,
    brain_observation: Observation,
    structured_command: StructuredCommand,
    tool_route: ToolRouteDecision,
    brain_risk: RiskAssessment,
    planner_plan: Plan,
    guardian: Any,
    memory: Any,
    dry_run: bool,
    extra_context: Dict[str, Any],
) -> Any:
    """Run full Think-Decide-Act with a brain-supplied preferred proposal."""
    from project_guardian.orchestration.think_decide_act import run_think_decide_act_pipeline

    proposal = build_preferred_action_proposal(
        observation=brain_observation,
        command=structured_command,
        route=tool_route,
        brain_risk=brain_risk,
        plan=planner_plan,
    )

    executor: Any = None
    if guardian is not None:
        executor = BrainCapabilityExecutor(guardian)
    elif extra_context.get("tda_executor_override") is not None:
        executor = extra_context.get("tda_executor_override")
    elif extra_context.get("tda_executor") is not None:
        executor = extra_context.get("tda_executor")

    allowed = list(extra_context.get("allowed_capabilities") or [])
    can_execute_capability = guardian is not None or executor is not None
    if (
        can_execute_capability
        and structured_command.capability_ref.startswith(("module:", "tool:"))
        and structured_command.capability_ref not in allowed
    ):
        allowed.append(structured_command.capability_ref)
    tda_ctx: Dict[str, Any] = {
        "source": "brain_pipeline",
        "preferred_action": proposal,
        "relevant_context_ids": list(extra_context.get("relevant_context_ids") or []),
        "allowed_capabilities": allowed,
        "operator_approved": bool(extra_context.get("operator_approved", False)),
        "approved_task_execution": bool(extra_context.get("approved_task_execution", False)),
    }
    if extra_context.get("risk_checker") is not None:
        tda_ctx["risk_checker"] = extra_context.get("risk_checker")

    input_event: Dict[str, Any] = {
        "source": brain_observation.source,
        "raw_input": brain_observation.text,
        "message": brain_observation.text,
    }
    if brain_observation.metadata:
        input_event["metadata"] = dict(brain_observation.metadata)

    return run_think_decide_act_pipeline(
        input_event,
        context=tda_ctx,
        dry_run=dry_run,
        guardian=guardian,
        memory=memory,
        executor=executor,
    )


def run_brain_action_through_tda(
    *,
    observation: Observation,
    plan: Plan,
    command: StructuredCommand,
    route: ToolRouteDecision,
    guardian: Any = None,
    memory: Any = None,
    context: Optional[Dict[str, Any]] = None,
    executor: Any = None,
    risk_checker: Any = None,
) -> BrainTDAResult:
    """Delegate BrainPipeline action validation/execution/review/remember to TDA."""
    ctx = dict(context or {})
    if executor is not None:
        ctx["tda_executor"] = executor
    if risk_checker is not None:
        ctx["risk_checker"] = risk_checker
    base_risk = RiskAssessment(
        RiskLevel.LOW if command.capability_ref.startswith(("brain:", "tool:")) else RiskLevel.MEDIUM,
        "brain_tda_precheck",
        {"capability_ref": command.capability_ref},
    )
    tda_trace = run_tda_for_brain_action(
        brain_observation=observation,
        structured_command=command,
        tool_route=route,
        brain_risk=base_risk,
        planner_plan=plan,
        guardian=guardian,
        memory=memory,
        dry_run=bool(ctx.get("dry_run", False)),
        extra_context=ctx,
    )
    risk = tda_trace_to_risk_assessment(tda_trace)
    execution_for_learning = tda_trace_to_execution_result(tda_trace)
    execution_for_trace: Optional[ExecutionResult] = execution_for_learning
    if not bool(getattr(tda_trace.validation, "approved", False)):
        execution_for_trace = None
    learning = tda_trace_to_learning_outcome(tda_trace, "brain_tda")
    return BrainTDAResult(
        risk=risk,
        execution_for_trace=execution_for_trace,
        execution_for_learning=execution_for_learning,
        learning=learning,
        tda_trace=tda_trace.to_dict(),
    )


def tda_trace_to_risk_assessment(tda_trace: Any) -> RiskAssessment:
    val = tda_trace.validation
    raw_level = str(getattr(val, "risk_level", "medium") or "medium").lower()
    approved = bool(getattr(val, "approved", False))
    if raw_level == "blocked":
        level = RiskLevel.BLOCKED
    elif raw_level == "high" or not approved:
        level = RiskLevel.HIGH
    elif raw_level == "low":
        level = RiskLevel.LOW
    else:
        level = RiskLevel.MEDIUM
    return RiskAssessment(
        level=level,
        reason=str(getattr(val, "validation_notes", "") or f"tda_validation:{raw_level}"),
        details={
            "approved": approved,
            "risk_level": raw_level,
            "required_permissions": list(getattr(val, "required_permissions", []) or []),
            "safe_alternative": getattr(val, "safe_alternative", None),
        },
    )


def tda_trace_to_execution_result(tda_trace: Any) -> ExecutionResult:
    """Map TDA execution + validation into Brain ``ExecutionResult``."""
    val = tda_trace.validation
    ex = tda_trace.execution
    approved = bool(getattr(val, "approved", False))
    success = bool(getattr(ex, "success", False)) and approved
    err: Optional[str] = ex.error if ex else None
    if not approved:
        success = False
        err = val.validation_notes or "tda_validation_blocked"
    data = dict(ex.result_payload or {})
    data["tda_action_id"] = ex.action_id
    data["tda_validation_approved"] = approved
    data["tda_validation_risk_level"] = getattr(val, "risk_level", None)
    if getattr(tda_trace, "dry_run", False):
        success = False
        err = err or "dry_run"
    return ExecutionResult(success=success, data=data, error=err)


def tda_trace_to_learning_outcome(tda_trace: Any, brain_pipeline_id: str) -> Any:
    from .contracts import LearningOutcome

    rev = tda_trace.review
    ex = tda_trace.execution
    worked = bool(rev.did_it_work) and bool(ex.success) and bool(tda_trace.validation.approved)
    lesson = (
        f"brain+tda pipeline_id={brain_pipeline_id} action_id={ex.action_id} "
        f"worked={worked} review={rev.failure_reason or 'ok'}"
    )
    hints: list[str] = []
    if rev.should_create_improvement_ticket:
        hints.append("tda_improvement_ticket")
    return LearningOutcome(worked=worked, lesson=lesson, improvement_hints=hints)


def build_unified_export(trace: Any) -> Dict[str, Any]:
    """Single JSON-friendly export for dashboard / diagnostics."""
    tool_route_dict: Optional[Dict[str, Any]] = None
    if trace.tool_route is not None:
        tool_route_dict = asdict(trace.tool_route)
    risk_dict: Optional[Dict[str, Any]] = None
    if trace.risk is not None:
        risk_dict = {"level": trace.risk.level.value, "reason": trace.risk.reason, "details": trace.risk.details}
    exec_dict: Optional[Dict[str, Any]] = None
    if trace.execution is not None:
        exec_dict = {
            "success": trace.execution.success,
            "error": trace.execution.error,
            "data": trace.execution.data,
        }
    learn_dict: Optional[Dict[str, Any]] = None
    if trace.learning is not None:
        learn_dict = {
            "worked": trace.learning.worked,
            "lesson": trace.learning.lesson,
            "improvement_hints": trace.learning.improvement_hints,
        }
    mem_result: Optional[Dict[str, Any]] = None
    if trace.think_decide_act_trace and isinstance(trace.think_decide_act_trace, dict):
        mem = trace.think_decide_act_trace.get("memory")
        if isinstance(mem, dict):
            mem_result = {
                "stored": mem.get("stored"),
                "memory_type": mem.get("memory_type"),
                "summary_preview": str(mem.get("summary") or "")[:400],
            }
    stage_logs: Any = trace.transitions
    if trace.think_decide_act_trace and isinstance(trace.think_decide_act_trace, dict):
        stage_logs = trace.think_decide_act_trace.get("stage_logs") or trace.transitions

    return {
        "brain_pipeline_id": trace.brain_pipeline_id,
        "started_at": trace.started_at,
        "input_source": trace.input_source,
        "observation_preview": trace.observation_preview,
        "context_summary": (trace.context_preview or "")[:4000],
        "planner_output": {
            "goal_summary": trace.plan.goal_summary if trace.plan else "",
            "router_task_type": trace.plan.router_task_type if trace.plan else "",
            "step_count": len(trace.plan.steps) if trace.plan else 0,
        },
        "llm_backend": trace.llm_backend,
        "llm_reason": trace.llm_reason,
        "selected_tool_route": trace.tool_route.selected if trace.tool_route else None,
        "tool_route": tool_route_dict,
        "risk": risk_dict,
        "execution": exec_dict,
        "learning": learn_dict,
        "memory_result": mem_result,
        "think_decide_act_trace": trace.think_decide_act_trace,
        "stage_logs": stage_logs,
        "run_context": dict(trace.run_context or {}),
        "brain_transitions": list(trace.transitions),
    }
