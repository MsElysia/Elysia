# project_guardian/orchestration/think_decide_act.py
"""Visible Think-Decide-Act pipeline for Elysia.

This module keeps cognition, decision, validation, execution, review, and
memory writes as separate typed stages. It is intentionally conservative:
free-form LLM or user text is never treated as executable code or commands.
"""

from __future__ import annotations

import inspect
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .tools.schemas import ActionIntent, execution_result_to_dict

logger = logging.getLogger(__name__)

RiskLevel = str

_SAFE_TOOL_TARGETS = frozenset(
    {
        "run_diagnostic",
        "create_task",
        "search_memory",
        "ask_user",
        "consider_learning",
        "consider_adversarial_learning",
        "rebuild_vector",
        "continue_monitoring",
        "safe_noop",
    }
)
_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|auth|bearer|credential|password|secret|token|private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|credential)\s*[:=]\s*([^\s,;]+)"
)
_DANGEROUS_ACTION_RE = re.compile(
    r"(?i)\b(shell|powershell|cmd(?:\.exe)?|terminal|subprocess|os\.system|exec\(|eval\(|"
    r"sudo|rm\s+-rf|del\s+/s|format\s+c:|delete|wipe|destroy|shutdown|reboot)\b"
)


@dataclass
class Observation:
    source: str
    raw_input: Any
    timestamp: str
    detected_intent: str
    confidence: float
    relevant_context_ids: List[str] = field(default_factory=list)


@dataclass
class ThoughtSummary:
    situation_summary: str
    likely_goal: str
    constraints: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    candidate_actions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ActionProposal:
    action_type: str
    target_module_or_tool: str
    inputs: Dict[str, Any]
    expected_result: str
    estimated_risk: RiskLevel
    fallback_action: Optional[Dict[str, Any]]
    reason_summary: str
    action_id: str = field(default_factory=lambda: f"tda-{uuid.uuid4().hex[:12]}")


@dataclass
class ValidationResult:
    approved: bool
    risk_level: RiskLevel
    required_permissions: List[str] = field(default_factory=list)
    validation_notes: str = ""
    safe_alternative: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionLogEntry:
    action_id: str
    action_type: str
    tool_or_module_used: str
    start_time: str
    end_time: str
    success: bool
    output_summary: str
    error: Optional[str] = None
    result_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewResult:
    did_it_work: bool
    usefulness_score: float
    failure_reason: Optional[str]
    should_retry: bool
    should_create_memory: bool
    should_create_improvement_ticket: bool


@dataclass
class MemoryRecord:
    memory_type: str
    summary: str
    relevance_score: float
    confidence_score: float
    linked_goal: str
    linked_action_id: str
    stored: bool = False


@dataclass
class StageLog:
    stage: str
    input_summary: str
    output_summary: str
    timestamp: str
    success: bool
    error: Optional[str] = None


@dataclass
class ThinkDecideActTrace:
    observation: Observation
    thought: ThoughtSummary
    proposal: ActionProposal
    validation: ValidationResult
    execution: ExecutionLogEntry
    review: ReviewResult
    memory: Optional[MemoryRecord]
    stage_logs: List[StageLog] = field(default_factory=list)
    dry_run: bool = False
    errors: List[str] = field(default_factory=list)
    prompt_contract_validation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_think_decide_act_pipeline(
    input_event: Any,
    context: Optional[Dict[str, Any]] = None,
    *,
    dry_run: bool = False,
    guardian: Any = None,
    risk_checker: Any = None,
    executor: Any = None,
    memory: Any = None,
    llm_router: Any = None,
) -> ThinkDecideActTrace:
    """Run Observe -> Think -> Propose -> Validate -> Execute -> Review -> Remember.

    Dependencies may be passed directly or through ``context``. The function
    returns the complete trace even when a stage fails; failures are captured in
    ``trace.errors`` and in the relevant ``StageLog``.
    """

    ctx = dict(context or {})
    guardian = guardian if guardian is not None else ctx.get("guardian")
    risk_checker = risk_checker if risk_checker is not None else ctx.get("risk_checker")
    executor = executor if executor is not None else ctx.get("executor")
    memory = memory if memory is not None else ctx.get("memory") or _get_attr(guardian, "memory")
    llm_router = llm_router if llm_router is not None else ctx.get("llm_router")
    dry_run = bool(dry_run or ctx.get("dry_run", False))
    ctx["dry_run"] = dry_run
    if executor is not None:
        ctx.setdefault("has_injected_executor", True)

    stage_logs: List[StageLog] = []
    errors: List[str] = []
    prompt_contract_validation: Dict[str, Any] = {}

    observation = _stage(
        "observe",
        _summarize_for_log(input_event),
        lambda: observe(input_event, ctx),
        _fallback_observation(input_event, ctx),
        stage_logs,
        errors,
    )
    thought = _stage(
        "think",
        _summarize_for_log(observation),
        lambda: think(observation, ctx, llm_router=llm_router),
        _fallback_thought(observation),
        stage_logs,
        errors,
    )
    _record_prompt_contract_validation(
        prompt_contract_validation,
        "think_decide_act_thinker",
        ctx,
        lambda: _tda_thinker_contract_output(observation, thought),
    )
    proposal = _stage(
        "propose",
        _summarize_for_log(thought),
        lambda: propose(thought, ctx),
        _fallback_proposal(thought),
        stage_logs,
        errors,
    )
    _record_prompt_contract_validation(
        prompt_contract_validation,
        "think_decide_act_proposer",
        ctx,
        lambda: _tda_proposer_contract_output(proposal),
    )
    forced_validation = ctx.pop("_prompt_contract_force_validation_result", None)
    if forced_validation is not None:
        validation = forced_validation
        stage_logs.append(
            StageLog(
                stage="validate",
                input_summary=_proposal_summary(proposal)[:1000],
                output_summary="prompt_contract_strict_block",
                timestamp=_now_iso(),
                success=False,
                error=None,
            )
        )
    else:
        validation = _stage(
            "validate",
            _proposal_summary(proposal),
            lambda: validate(proposal, ctx, guardian=guardian, risk_checker=risk_checker),
            _blocked_validation("validate_stage_failed"),
            stage_logs,
            errors,
        )
    execution = _stage(
        "execute",
        _validation_summary(validation),
        lambda: execute(
            proposal,
            validation,
            ctx,
            dry_run=dry_run,
            guardian=guardian,
            executor=executor,
            memory=memory,
        ),
        _skipped_execution(proposal, "execute_stage_failed"),
        stage_logs,
        errors,
    )
    review = _stage(
        "review",
        _execution_summary(execution),
        lambda: review_execution(proposal, validation, execution, ctx, dry_run=dry_run),
        _fallback_review(execution),
        stage_logs,
        errors,
    )
    memory_record = _stage(
        "remember",
        _review_summary(review),
        lambda: remember(observation, thought, proposal, execution, review, ctx, memory=memory),
        None,
        stage_logs,
        errors,
    )

    return ThinkDecideActTrace(
        observation=observation,
        thought=thought,
        proposal=proposal,
        validation=validation,
        execution=execution,
        review=review,
        memory=memory_record,
        stage_logs=stage_logs,
        dry_run=dry_run,
        errors=errors,
        prompt_contract_validation=prompt_contract_validation,
    )


def observe(input_event: Any, context: Optional[Dict[str, Any]] = None) -> Observation:
    ctx = context or {}
    source = "user_request"
    raw_input: Any = input_event
    intent = ""
    confidence: Optional[float] = None

    if isinstance(input_event, dict):
        source = str(input_event.get("source") or input_event.get("event_source") or "system_event")
        raw_input = input_event.get("raw_input", input_event.get("message", input_event.get("text", input_event)))
        intent = str(input_event.get("detected_intent") or input_event.get("intent") or "")
        if input_event.get("confidence") is not None:
            try:
                confidence = float(input_event.get("confidence"))
            except (TypeError, ValueError):
                confidence = None
    elif ctx.get("source"):
        source = str(ctx["source"])

    detected_intent, inferred_confidence = _detect_intent(raw_input)
    if intent:
        detected_intent = intent[:80]
    if confidence is None:
        confidence = inferred_confidence

    relevant_context_ids = _context_ids(ctx)
    return Observation(
        source=source[:80],
        raw_input=raw_input,
        timestamp=_now_iso(),
        detected_intent=detected_intent,
        confidence=_clamp(float(confidence), 0.0, 1.0),
        relevant_context_ids=relevant_context_ids,
    )


def think(
    observation: Observation,
    context: Optional[Dict[str, Any]] = None,
    *,
    llm_router: Any = None,
) -> ThoughtSummary:
    ctx = context or {}
    raw_text = _raw_text(observation.raw_input)
    constraints = [
        "Do not execute raw user or LLM text as code or shell commands.",
        "Validate every proposed action before execution.",
        "Use existing safe executors and project gates when execution is required.",
        "Store only useful, redacted result summaries in memory.",
    ]
    missing_information: List[str] = []

    if observation.detected_intent in {"general_request", "unknown"}:
        missing_information.append("A specific safe target capability may be needed.")
    if observation.confidence < 0.5:
        missing_information.append("Intent confidence is low.")

    likely_goal = _infer_goal(observation.detected_intent, raw_text)
    situation_summary = (
        f"{observation.source} event with intent '{observation.detected_intent}' "
        f"and confidence {observation.confidence:.2f}."
    )

    candidate_actions = _candidate_actions_for(observation, ctx)
    if llm_router is not None and ctx.get("use_llm_router_for_think"):
        router_note = _call_router_for_summary(llm_router, observation, ctx)
        if router_note:
            situation_summary = f"{situation_summary} Router note: {router_note[:400]}"

    override_actions = ctx.get("candidate_actions")
    if isinstance(override_actions, list) and override_actions:
        candidate_actions = [dict(item) for item in override_actions if isinstance(item, dict)]

    return ThoughtSummary(
        situation_summary=situation_summary,
        likely_goal=likely_goal,
        constraints=constraints,
        missing_information=missing_information,
        candidate_actions=candidate_actions,
    )


def propose(thought: ThoughtSummary, context: Optional[Dict[str, Any]] = None) -> ActionProposal:
    ctx = context or {}
    preferred = ctx.get("preferred_action")
    if isinstance(preferred, ActionProposal):
        return preferred
    if isinstance(preferred, dict):
        return _proposal_from_candidate(preferred)

    candidates = [c for c in thought.candidate_actions if isinstance(c, dict)]
    if not candidates:
        candidates = [_ask_user_candidate("No safe candidate action was available.")]

    chosen = sorted(candidates, key=_candidate_rank)[0]
    return _proposal_from_candidate(chosen)


def validate(
    proposal: ActionProposal,
    context: Optional[Dict[str, Any]] = None,
    *,
    guardian: Any = None,
    risk_checker: Any = None,
) -> ValidationResult:
    ctx = context or {}
    checker = risk_checker or _get_attr(guardian, "risk_checker")
    if checker is None:
        checker = (
            _get_attr(guardian, "trust_eval")
            or _get_attr(guardian, "trust_eval_action")
            or _get_attr(guardian, "trust_eval_action_module")
        )
    default_checker = DefaultRiskChecker(guardian=guardian)
    result = default_checker.validate(proposal, ctx)
    if not result.approved:
        return result

    if checker is None:
        return result

    checked = _call_external_risk_checker(checker, proposal, ctx)
    if checked is None:
        return result
    if not checked.approved:
        return checked

    return ValidationResult(
        approved=True,
        risk_level=_max_risk_level(result.risk_level, checked.risk_level),
        required_permissions=_dedupe(result.required_permissions + checked.required_permissions),
        validation_notes="; ".join(
            note for note in (result.validation_notes, checked.validation_notes) if note
        )[:1000],
        safe_alternative=None,
    )


def execute(
    proposal: ActionProposal,
    validation: ValidationResult,
    context: Optional[Dict[str, Any]] = None,
    *,
    dry_run: bool = False,
    guardian: Any = None,
    executor: Any = None,
    memory: Any = None,
) -> ExecutionLogEntry:
    start = _now_iso()
    if not validation.approved:
        return ExecutionLogEntry(
            action_id=proposal.action_id,
            action_type=proposal.action_type,
            tool_or_module_used=proposal.target_module_or_tool,
            start_time=start,
            end_time=_now_iso(),
            success=False,
            output_summary="Execution skipped because validation did not approve the action.",
            error=validation.validation_notes or "validation_blocked",
            result_payload={"skipped": True, "reason": validation.validation_notes},
        )

    if dry_run:
        return ExecutionLogEntry(
            action_id=proposal.action_id,
            action_type=proposal.action_type,
            tool_or_module_used=proposal.target_module_or_tool,
            start_time=start,
            end_time=_now_iso(),
            success=False,
            output_summary="Dry run: validation completed and execution was intentionally skipped.",
            error=None,
            result_payload={"dry_run": True, "skipped": True},
        )

    try:
        raw_result = _execute_approved_action(
            proposal,
            context or {},
            guardian=guardian,
            executor=executor,
            memory=memory,
        )
        success, output_summary, error, payload = _normalize_execution_result(raw_result)
    except Exception as exc:
        logger.exception("Think-Decide-Act execute stage failed")
        success = False
        output_summary = "Execution raised an exception."
        error = str(exc)[:1000]
        payload = {"exception": True}

    return ExecutionLogEntry(
        action_id=proposal.action_id,
        action_type=proposal.action_type,
        tool_or_module_used=proposal.target_module_or_tool,
        start_time=start,
        end_time=_now_iso(),
        success=success,
        output_summary=output_summary,
        error=error,
        result_payload=payload,
    )


def review_execution(
    proposal: ActionProposal,
    validation: ValidationResult,
    execution: ExecutionLogEntry,
    context: Optional[Dict[str, Any]] = None,
    *,
    dry_run: bool = False,
) -> ReviewResult:
    ctx = context or {}
    retry_count = int(ctx.get("retry_count", 0) or 0)

    if not validation.approved:
        return ReviewResult(
            did_it_work=False,
            usefulness_score=0.0,
            failure_reason=validation.validation_notes or "validation_blocked",
            should_retry=False,
            should_create_memory=False,
            should_create_improvement_ticket=bool(validation.safe_alternative),
        )

    if dry_run:
        return ReviewResult(
            did_it_work=False,
            usefulness_score=0.45,
            failure_reason="dry_run_no_execution",
            should_retry=False,
            should_create_memory=False,
            should_create_improvement_ticket=False,
        )

    if execution.success:
        score = 0.9 if validation.risk_level == "low" else 0.72
        create_memory = proposal.target_module_or_tool not in {"ask_user", "continue_monitoring"}
        return ReviewResult(
            did_it_work=True,
            usefulness_score=score,
            failure_reason=None,
            should_retry=False,
            should_create_memory=create_memory,
            should_create_improvement_ticket=False,
        )

    retryable = (
        retry_count < 1
        and validation.risk_level in {"low", "medium"}
        and proposal.action_type not in {"ask_user", "blocked_request"}
        and not _looks_dangerous(proposal.action_type, proposal.target_module_or_tool, proposal.inputs)
    )
    return ReviewResult(
        did_it_work=False,
        usefulness_score=0.25,
        failure_reason=execution.error or "execution_failed",
        should_retry=retryable,
        should_create_memory=False,
        should_create_improvement_ticket=not retryable,
    )


def remember(
    observation: Observation,
    thought: ThoughtSummary,
    proposal: ActionProposal,
    execution: ExecutionLogEntry,
    review: ReviewResult,
    context: Optional[Dict[str, Any]] = None,
    *,
    memory: Any = None,
) -> Optional[MemoryRecord]:
    if not review.should_create_memory:
        return None

    ctx = context or {}
    summary = (
        f"Think-Decide-Act action {proposal.action_type} via "
        f"{proposal.target_module_or_tool} worked: {execution.output_summary}"
    )
    summary = _redact_sensitive_text(summary)[:900]
    if _is_junk_memory(summary):
        return None

    record = MemoryRecord(
        memory_type=str(ctx.get("memory_type") or "pipeline_result"),
        summary=summary,
        relevance_score=_clamp(review.usefulness_score, 0.0, 1.0),
        confidence_score=_clamp(observation.confidence, 0.0, 1.0),
        linked_goal=thought.likely_goal[:300],
        linked_action_id=proposal.action_id,
        stored=False,
    )

    writer = memory
    if writer is None:
        return record

    metadata = {
        "source": "think_decide_act_pipeline",
        "memory_type": record.memory_type,
        "relevance_score": record.relevance_score,
        "confidence_score": record.confidence_score,
        "linked_goal": record.linked_goal,
        "linked_action_id": record.linked_action_id,
    }
    if hasattr(writer, "remember") and callable(writer.remember):
        writer.remember(
            record.summary,
            category="think_decide_act",
            priority=record.relevance_score,
            metadata=metadata,
        )
        record.stored = True
    elif callable(writer):
        writer(record)
        record.stored = True
    return record


class DefaultRiskChecker:
    """Conservative local risk checker with optional existing Guardian gates."""

    def __init__(self, guardian: Any = None) -> None:
        self.guardian = guardian

    def validate(self, proposal: ActionProposal, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        ctx = context or {}
        required_permissions = _required_permissions(proposal)

        if _looks_dangerous(proposal.action_type, proposal.target_module_or_tool, proposal.inputs):
            return ValidationResult(
                approved=False,
                risk_level="blocked",
                required_permissions=required_permissions,
                validation_notes="Blocked direct shell, destructive, or command-like action; use an approved safe executor or request operator approval.",
                safe_alternative=_ask_user_candidate("Ask the operator to approve a safe executor path."),
            )

        if proposal.estimated_risk == "blocked":
            return ValidationResult(
                approved=False,
                risk_level="blocked",
                required_permissions=required_permissions,
                validation_notes="Proposal estimated risk is blocked.",
                safe_alternative=proposal.fallback_action,
            )

        if proposal.estimated_risk == "high" and not ctx.get("operator_approved"):
            return ValidationResult(
                approved=False,
                risk_level="high",
                required_permissions=required_permissions,
                validation_notes="High-risk action requires explicit operator approval.",
                safe_alternative=proposal.fallback_action,
            )

        if proposal.target_module_or_tool == "execute_task" and not ctx.get("approved_task_execution"):
            return ValidationResult(
                approved=False,
                risk_level="high",
                required_permissions=required_permissions,
                validation_notes="execute_task requires an explicit approved_task_execution context flag.",
                safe_alternative=_ask_user_candidate("Request approval for task execution."),
            )

        if proposal.target_module_or_tool.startswith(("module:", "tool:")):
            allowed = {str(item).strip().lower() for item in ctx.get("allowed_capabilities", [])}
            target_key = proposal.target_module_or_tool.strip().lower()
            if not ctx.get("has_injected_executor") and target_key not in allowed:
                return ValidationResult(
                    approved=False,
                    risk_level="blocked",
                    required_permissions=required_permissions,
                    validation_notes="Capability execution requires an injected approved executor or an allowed_capabilities entry.",
                    safe_alternative=proposal.fallback_action,
                )

        eai_result = self._check_eai_safety(proposal, ctx)
        if eai_result is not None and not eai_result.approved:
            return eai_result

        trust_result = self._check_trust_matrix(proposal, ctx)
        if trust_result is not None and not trust_result.approved:
            return trust_result

        risk_level = proposal.estimated_risk if proposal.estimated_risk in {"low", "medium"} else "medium"
        return ValidationResult(
            approved=True,
            risk_level=risk_level,
            required_permissions=required_permissions,
            validation_notes="Approved by default Think-Decide-Act risk checker.",
            safe_alternative=None,
        )

    def _check_eai_safety(self, proposal: ActionProposal, context: Dict[str, Any]) -> Optional[ValidationResult]:
        framework = _get_attr(self.guardian, "eai_safety") or _get_attr(self.guardian, "eai_safety_framework")
        if framework is None or not hasattr(framework, "assess_action"):
            return None
        action_text = f"{proposal.action_type} {proposal.target_module_or_tool}"
        if not re.search(r"(?i)\b(mutation|replicate|clone|spawn|deploy|publish|fine[-_ ]?tune|model_merge)\b", action_text):
            return None
        try:
            assessment = framework.assess_action(
                action_type=proposal.action_type,
                actor=str(context.get("actor") or "elysia_think_decide_act"),
                target=proposal.target_module_or_tool,
                metadata={
                    "source": "think_decide_act_pipeline",
                    "estimated_risk": proposal.estimated_risk,
                    "operator_approved": bool(context.get("operator_approved")),
                    **dict(context.get("validation_metadata") or {}),
                },
                dry_run=True,
            )
        except Exception as exc:
            return ValidationResult(
                approved=False,
                risk_level="blocked",
                required_permissions=_required_permissions(proposal),
                validation_notes=f"EAI safety assessment failed: {exc}",
                safe_alternative=proposal.fallback_action,
            )
        decision = str(getattr(getattr(assessment, "decision", None), "value", getattr(assessment, "decision", "")))
        risk_score = float(getattr(assessment, "risk_score", 1.0) or 1.0)
        if decision in {"deny", "review"}:
            risk = "blocked" if decision == "deny" else "high"
            return ValidationResult(
                approved=False,
                risk_level=risk,
                required_permissions=_required_permissions(proposal) + list(getattr(assessment, "required_controls", []) or []),
                validation_notes=str(getattr(assessment, "reasoning", "EAI safety blocked action")),
                safe_alternative=proposal.fallback_action,
            )
        if risk_score >= 0.7 and not context.get("operator_approved"):
            return ValidationResult(
                approved=False,
                risk_level="high",
                required_permissions=_required_permissions(proposal),
                validation_notes="EAI safety reported high risk without operator approval.",
                safe_alternative=proposal.fallback_action,
            )
        return None

    def _check_trust_matrix(self, proposal: ActionProposal, context: Dict[str, Any]) -> Optional[ValidationResult]:
        trust = _get_attr(self.guardian, "trust") or _get_attr(self.guardian, "trust_matrix")
        if trust is None or not hasattr(trust, "validate_trust_for_action"):
            return None
        trust_action = _trust_action_for(proposal)
        if trust_action is None:
            return None
        try:
            decision = trust.validate_trust_for_action(
                "ThinkDecideActPipeline",
                trust_action,
                context={
                    "action_id": proposal.action_id,
                    "action_type": proposal.action_type,
                    "target": proposal.target_module_or_tool,
                    "source": "think_decide_act_pipeline",
                },
            )
        except Exception as exc:
            return ValidationResult(
                approved=False,
                risk_level="blocked",
                required_permissions=_required_permissions(proposal),
                validation_notes=f"TrustMatrix validation failed: {exc}",
                safe_alternative=proposal.fallback_action,
            )
        allowed = bool(getattr(decision, "allowed", False))
        if allowed:
            return None
        return ValidationResult(
            approved=False,
            risk_level="high" if getattr(decision, "decision", "") == "review" else "blocked",
            required_permissions=_required_permissions(proposal),
            validation_notes=str(getattr(decision, "message", "TrustMatrix blocked action")),
            safe_alternative=proposal.fallback_action,
        )


def _stage(
    name: str,
    input_summary: str,
    fn: Any,
    fallback: Any,
    stage_logs: List[StageLog],
    errors: List[str],
) -> Any:
    logger.info("[ThinkDecideAct:%s] input=%s", name, input_summary[:500])
    timestamp = _now_iso()
    try:
        out = fn()
        output_summary = _summarize_for_log(out)
        logger.info("[ThinkDecideAct:%s] output=%s", name, output_summary[:500])
        stage_logs.append(
            StageLog(
                stage=name,
                input_summary=input_summary[:1000],
                output_summary=output_summary[:1000],
                timestamp=timestamp,
                success=True,
                error=None,
            )
        )
        return out
    except Exception as exc:
        msg = f"{name}: {exc}"
        logger.exception("[ThinkDecideAct:%s] failed", name)
        errors.append(msg)
        fallback_summary = _summarize_for_log(fallback)
        logger.info("[ThinkDecideAct:%s] output=%s", name, fallback_summary[:500])
        stage_logs.append(
            StageLog(
                stage=name,
                input_summary=input_summary[:1000],
                output_summary=fallback_summary[:1000],
                timestamp=timestamp,
                success=False,
                error=str(exc)[:1000],
            )
        )
        return fallback


def _record_prompt_contract_validation(
    validation_bucket: Dict[str, Any],
    module_name: str,
    context: Dict[str, Any],
    default_payload_factory: Any,
) -> None:
    try:
        from project_guardian.prompt_contracts.integration import (
            resolve_prompt_contract_payload,
            should_validate_prompt_contracts,
            validate_module_output_for_trace,
        )

        if not should_validate_prompt_contracts(context, module_name):
            return
        payload = resolve_prompt_contract_payload(context, module_name, default_payload_factory)
        result = validate_module_output_for_trace(module_name, payload, context)
        validation_bucket[module_name] = result
        if result.get("blocked") and "_prompt_contract_force_validation_result" not in context:
            context["_prompt_contract_force_validation_result"] = ValidationResult(
                approved=False,
                risk_level="blocked",
                required_permissions=[],
                validation_notes=f"prompt_contract_strict:{module_name}",
                safe_alternative=None,
            )
    except Exception as exc:
        logger.warning("Think-Decide-Act prompt contract validation skipped: %s", exc)
        mode = "warn"
        try:
            from project_guardian.prompt_contracts.integration import contract_mode_from_context

            mode = contract_mode_from_context(context)
        except Exception:
            pass
        validation_bucket[module_name] = {
            "module_name": module_name,
            "contract_id": "",
            "valid": False,
            "errors": [str(exc)[:240]],
            "warnings": [],
            "mode": mode,
            "blocked": False,
        }


def _tda_thinker_contract_output(observation: Observation, thought: ThoughtSummary) -> Dict[str, Any]:
    return {
        "goal_candidates": list(thought.candidate_actions[:10]),
        "reason_summary": thought.situation_summary[:400],
        "confidence": _clamp(float(observation.confidence), 0.0, 1.0),
        "risk_level": _highest_candidate_risk(thought.candidate_actions),
    }


def _tda_proposer_contract_output(proposal: ActionProposal) -> Dict[str, Any]:
    return {
        "action_type": proposal.action_type,
        "target": proposal.target_module_or_tool,
        "reason_summary": proposal.reason_summary[:400],
        "confidence": 0.71,
        "risk_level": _normalize_risk(proposal.estimated_risk),
    }


def _highest_candidate_risk(candidates: List[Dict[str, Any]]) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    chosen = "low"
    for candidate in candidates or []:
        risk = _normalize_risk(candidate.get("estimated_risk", "low")) if isinstance(candidate, dict) else "low"
        if order[risk] > order[chosen]:
            chosen = risk
    return chosen


def _candidate_actions_for(observation: Observation, context: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = _raw_text(observation.raw_input)
    intent = observation.detected_intent
    if intent == "shell_execution":
        return [
            {
                "action_type": "shell_command",
                "target_module_or_tool": "shell",
                "inputs": {"requested_text": text[:500]},
                "expected_result": "Would run a local command if it were safe.",
                "estimated_risk": "blocked",
                "fallback_action": _ask_user_candidate("Explain that direct shell execution is blocked."),
                "reason_summary": "The request appears to ask for direct shell or command execution.",
            }
        ]
    if intent == "destructive_action":
        return [
            {
                "action_type": "destructive_action",
                "target_module_or_tool": "file_system",
                "inputs": {"requested_text": text[:500]},
                "expected_result": "Would alter or remove state.",
                "estimated_risk": "blocked",
                "fallback_action": _ask_user_candidate("Ask for a safe, reviewed plan before destructive changes."),
                "reason_summary": "The request contains destructive operation language.",
            }
        ]
    if intent == "memory_search":
        return [
            {
                "action_type": "tool_call",
                "target_module_or_tool": "search_memory",
                "inputs": {"query": text[:500], "limit": int(context.get("memory_search_limit", 10) or 10)},
                "expected_result": "Relevant memory snippets are returned.",
                "estimated_risk": "low",
                "fallback_action": _ask_user_candidate("Ask for a more specific memory query."),
                "reason_summary": "The user appears to be asking for prior memory or recall.",
            }
        ]
    if intent == "status_check":
        return [
            {
                "action_type": "tool_call",
                "target_module_or_tool": "run_diagnostic",
                "inputs": {"reason": text[:300]},
                "expected_result": "A diagnostic or status report is produced.",
                "estimated_risk": "medium",
                "fallback_action": {"action_type": "tool_call", "target_module_or_tool": "continue_monitoring"},
                "reason_summary": "The request is asking for system health, status, or diagnostics.",
            }
        ]
    if intent == "create_task":
        return [
            {
                "action_type": "tool_call",
                "target_module_or_tool": "create_task",
                "inputs": {
                    "name": _title_from_text(text),
                    "description": text[:1000],
                    "priority": float(context.get("task_priority", 0.7) or 0.7),
                },
                "expected_result": "A task is created through the existing task surface.",
                "estimated_risk": "medium",
                "fallback_action": _ask_user_candidate("Ask for task title and priority."),
                "reason_summary": "The request looks like task creation or follow-up capture.",
            }
        ]
    if intent == "learning_cycle":
        return [
            {
                "action_type": "tool_call",
                "target_module_or_tool": "consider_learning",
                "inputs": {"trigger": "think_decide_act", "reason": text[:300]},
                "expected_result": "A guarded learning consideration is triggered.",
                "estimated_risk": "medium",
                "fallback_action": {"action_type": "tool_call", "target_module_or_tool": "continue_monitoring"},
                "reason_summary": "The request asks Elysia to learn or reflect.",
            }
        ]
    if intent == "remember_request":
        return [
            {
                "action_type": "memory_note",
                "target_module_or_tool": "memory",
                "inputs": {"summary": _redact_sensitive_text(text[:800])},
                "expected_result": "Memory write is deferred to the Remember stage after review.",
                "estimated_risk": "low",
                "fallback_action": None,
                "reason_summary": "The request asks to remember something; storage still goes through review.",
            }
        ]
    return [_ask_user_candidate("Clarify the requested safe action before execution.")]


def _execute_approved_action(
    proposal: ActionProposal,
    context: Dict[str, Any],
    *,
    guardian: Any = None,
    executor: Any = None,
    memory: Any = None,
) -> Any:
    if executor is not None:
        return _call_executor(executor, proposal, context)

    target = proposal.target_module_or_tool
    if target == "safe_noop":
        return {"success": True, "output_summary": "No-op completed safely."}
    if target == "ask_user":
        return {"success": True, "status": "deferred", "output_summary": "User clarification requested."}
    if target == "continue_monitoring":
        return {"success": True, "action": "continue_monitoring", "output_summary": "Monitoring continued."}
    if target == "memory":
        return {
            "success": True,
            "output_summary": "Memory candidate accepted; Remember stage decides whether to store it.",
        }
    if target == "search_memory" and guardian is None and memory is not None:
        return _execute_memory_search(memory, proposal.inputs)
    if target in _SAFE_TOOL_TARGETS and guardian is not None:
        from ..tool_executor import execute_action

        allowed_tools = set(context.get("allowed_tools") or _SAFE_TOOL_TARGETS)
        allowed_tools = allowed_tools & _SAFE_TOOL_TARGETS
        return execute_action({"tool": target, "args": _redact_sensitive(proposal.inputs)}, allowed_tools, guardian)
    if target.startswith(("module:", "tool:")) and guardian is not None:
        kind, _, name = target.partition(":")
        from .tools.bridge import execute_action_intent

        intent = ActionIntent(
            action_type=proposal.action_type,
            target_kind=kind,  # type: ignore[arg-type]
            target_name=name,
            payload=dict(proposal.inputs),
            confidence=0.75,
            rationale=proposal.reason_summary,
        )
        er = execute_action_intent(
            guardian,
            intent,
            allowed_capabilities=list(context.get("allowed_capabilities") or []),
            task_context=context,
        )
        return execution_result_to_dict(er)
    return {
        "success": False,
        "error": "No approved executor or safe built-in path available for this action.",
    }


def _call_executor(executor: Any, proposal: ActionProposal, context: Dict[str, Any]) -> Any:
    if hasattr(executor, "execute") and callable(executor.execute):
        try:
            return executor.execute(proposal, context=context)
        except TypeError:
            return executor.execute(proposal)
    if callable(executor):
        try:
            sig = inspect.signature(executor)
            if len(sig.parameters) >= 2:
                return executor(proposal, context)
        except (TypeError, ValueError):
            pass
        return executor(proposal)
    raise TypeError("executor must be callable or expose execute()")


def _call_external_risk_checker(
    checker: Any,
    proposal: ActionProposal,
    context: Dict[str, Any],
) -> Optional[ValidationResult]:
    try:
        if hasattr(checker, "authorize_action") and callable(checker.authorize_action):
            raw = checker.authorize_action(
                {"user_id": str(context.get("actor") or "elysia")},
                {
                    "id": proposal.action_id,
                    "type": _trust_eval_action_type(proposal),
                    "target": proposal.target_module_or_tool,
                    "parameters": _redact_sensitive(proposal.inputs),
                },
                dry_run=True,
            )
        elif hasattr(checker, "validate") and callable(checker.validate):
            try:
                raw = checker.validate(proposal, context=context)
            except TypeError:
                raw = checker.validate(proposal)
        elif hasattr(checker, "check") and callable(checker.check):
            try:
                raw = checker.check(proposal, context=context)
            except TypeError:
                raw = checker.check(proposal)
        elif callable(checker):
            try:
                raw = checker(proposal, context)
            except TypeError:
                raw = checker(proposal)
        else:
            return None
    except Exception as exc:
        return ValidationResult(
            approved=False,
            risk_level="blocked",
            required_permissions=_required_permissions(proposal),
            validation_notes=f"Risk checker failed closed: {exc}",
            safe_alternative=proposal.fallback_action,
        )
    return _coerce_validation_result(raw, proposal)


def _coerce_validation_result(raw: Any, proposal: ActionProposal) -> Optional[ValidationResult]:
    if raw is None:
        return None
    if isinstance(raw, ValidationResult):
        return raw
    if isinstance(raw, dict):
        approved = bool(raw.get("approved", raw.get("allowed", raw.get("valid", False))))
        risk_level = str(
            raw.get("risk_level")
            or raw.get("severity_level")
            or ("low" if approved else "blocked")
        ).lower()
        if risk_level in {"critical", "deny", "denied"}:
            risk_level = "blocked"
        if risk_level not in {"low", "medium", "high", "blocked"}:
            risk_level = "low" if approved else "blocked"
        permissions = raw.get("required_permissions") or raw.get("permissions") or _required_permissions(proposal)
        notes = raw.get("validation_notes") or raw.get("reason") or raw.get("message") or ""
        return ValidationResult(
            approved=approved,
            risk_level=risk_level,
            required_permissions=[str(item) for item in permissions],
            validation_notes=str(notes)[:1000],
            safe_alternative=raw.get("safe_alternative") or proposal.fallback_action if not approved else None,
        )
    allowed = getattr(raw, "allowed", None)
    if allowed is not None:
        return ValidationResult(
            approved=bool(allowed),
            risk_level="low" if allowed else "blocked",
            required_permissions=_required_permissions(proposal),
            validation_notes=str(getattr(raw, "message", ""))[:1000],
            safe_alternative=proposal.fallback_action if not allowed else None,
        )
    return None


def _normalize_execution_result(raw: Any) -> Tuple[bool, str, Optional[str], Dict[str, Any]]:
    if isinstance(raw, ExecutionLogEntry):
        return raw.success, raw.output_summary, raw.error, raw.result_payload
    if isinstance(raw, dict):
        success = bool(raw.get("success", raw.get("ok", raw.get("status") == "ok")))
        error = raw.get("error")
        summary = raw.get("output_summary") or raw.get("message")
        if summary is None:
            result = raw.get("result", raw.get("data", raw))
            summary = _summarize_for_log(result)
        return success, str(summary)[:1000], str(error)[:1000] if error else None, dict(raw)
    if raw is None:
        return False, "Executor returned no result.", "empty_result", {}
    return True, _summarize_for_log(raw), None, {"raw": raw}


def _execute_memory_search(memory: Any, inputs: Dict[str, Any]) -> Dict[str, Any]:
    query = str(inputs.get("query") or "")
    limit = int(inputs.get("limit", 10) or 10)
    if hasattr(memory, "search_memories") and callable(memory.search_memories):
        results = memory.search_memories(query, limit=limit)
    elif hasattr(memory, "get_recent_memories") and callable(memory.get_recent_memories):
        results = memory.get_recent_memories(limit=limit)
    else:
        return {"success": False, "error": "memory object does not expose search/read methods"}
    return {
        "success": True,
        "result": {"count": len(results or []), "items": results},
        "output_summary": f"Memory search returned {len(results or [])} item(s).",
    }


def _detect_intent(raw_input: Any) -> Tuple[str, float]:
    text = _raw_text(raw_input).lower()
    if not text.strip():
        return "unknown", 0.2
    if _DANGEROUS_ACTION_RE.search(text):
        if re.search(r"(?i)\b(shell|powershell|cmd(?:\.exe)?|terminal|subprocess|os\.system|exec\(|eval\(|sudo|rm\s+-rf)\b", text):
            return "shell_execution", 0.9
        return "destructive_action", 0.84
    if any(token in text for token in ("search memory", "recall", "what do you remember", "remember about")):
        return "memory_search", 0.78
    if any(token in text for token in ("status", "health", "diagnostic", "check system", "logs")):
        return "status_check", 0.72
    if any(token in text for token in ("create task", "add task", "todo", "follow up")):
        return "create_task", 0.75
    if any(token in text for token in ("learn", "reflect", "introspect", "self-improve")):
        return "learning_cycle", 0.68
    if any(token in text for token in ("remember this", "save this", "store this")):
        return "remember_request", 0.7
    return "general_request", 0.55


def _infer_goal(intent: str, text: str) -> str:
    if intent == "memory_search":
        return "Retrieve relevant prior memory safely."
    if intent == "status_check":
        return "Understand current system status or diagnostics."
    if intent == "create_task":
        return "Capture a requested task for later work."
    if intent == "learning_cycle":
        return "Consider a guarded learning or reflection cycle."
    if intent in {"shell_execution", "destructive_action"}:
        return "Avoid unsafe execution and route toward an approved safe alternative."
    if intent == "remember_request":
        return "Preserve useful information only after review and redaction."
    return f"Clarify and safely handle request: {text[:120]}"


def _proposal_from_candidate(candidate: Dict[str, Any]) -> ActionProposal:
    fallback = candidate.get("fallback_action")
    if isinstance(fallback, ActionProposal):
        fallback = asdict(fallback)
    return ActionProposal(
        action_type=str(candidate.get("action_type") or "ask_user"),
        target_module_or_tool=str(candidate.get("target_module_or_tool") or candidate.get("target") or "ask_user"),
        inputs=dict(candidate.get("inputs") or candidate.get("payload") or {}),
        expected_result=str(candidate.get("expected_result") or "Action completes safely."),
        estimated_risk=_normalize_risk(candidate.get("estimated_risk", "medium")),
        fallback_action=fallback if isinstance(fallback, dict) else None,
        reason_summary=str(candidate.get("reason_summary") or candidate.get("reason") or "")[:1000],
        action_id=str(candidate.get("action_id") or f"tda-{uuid.uuid4().hex[:12]}"),
    )


def _candidate_rank(candidate: Dict[str, Any]) -> Tuple[int, int]:
    risk_order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    risk = _normalize_risk(candidate.get("estimated_risk", "medium"))
    preferred = 0 if candidate.get("preferred") else 1
    return (risk_order.get(risk, 2), preferred)


def _ask_user_candidate(message: str) -> Dict[str, Any]:
    return {
        "action_type": "ask_user",
        "target_module_or_tool": "ask_user",
        "inputs": {"message": message},
        "expected_result": "The operator is asked for clarification or approval.",
        "estimated_risk": "low",
        "fallback_action": None,
        "reason_summary": message,
    }


def _required_permissions(proposal: ActionProposal) -> List[str]:
    target = proposal.target_module_or_tool
    action = proposal.action_type.lower()
    if target == "search_memory":
        return ["memory.read"]
    if target == "memory":
        return ["memory.write"]
    if target == "create_task":
        return ["task.create"]
    if target == "run_diagnostic":
        return ["diagnostic.run"]
    if target == "execute_task":
        return ["task.execute"]
    if target.startswith(("module:", "tool:")):
        return ["capability.execute", f"capability.{target}"]
    if "shell" in action or target in {"shell", "subprocess"}:
        return ["subprocess.execute"]
    if "file" in action:
        return ["file.write" if "write" in action or "delete" in action else "file.read"]
    return ["pipeline.execute.low_risk"]


def _looks_dangerous(action_type: str, target: str, inputs: Dict[str, Any]) -> bool:
    text = f"{action_type} {target} {_raw_text(inputs)}"
    if _DANGEROUS_ACTION_RE.search(text):
        return True
    if target in {"shell", "terminal", "subprocess", "file_system"}:
        return True
    if action_type in {"shell_command", "destructive_action", "file_delete", "system_command"}:
        return True
    return False


def _trust_eval_action_type(proposal: ActionProposal) -> str:
    text = f"{proposal.action_type} {proposal.target_module_or_tool}".lower()
    if "network" in text or "web" in text or "http" in text:
        return "network"
    if "file" in text:
        return "file_write" if any(w in text for w in ("write", "delete", "modify")) else "file_read"
    if "shell" in text or "subprocess" in text or "system" in text:
        return "system"
    if "database" in text or "sql" in text:
        return "database"
    return "module_execution"


def _trust_action_for(proposal: ActionProposal) -> Optional[str]:
    text = f"{proposal.action_type} {proposal.target_module_or_tool}".lower()
    try:
        from ..trust import FILE_WRITE, GOVERNANCE_MUTATION, NETWORK_ACCESS, SUBPROCESS_EXECUTION
    except Exception:
        return None
    if "network" in text or "web" in text or "http" in text:
        return NETWORK_ACCESS
    if "file" in text:
        return FILE_WRITE
    if "shell" in text or "subprocess" in text or "system" in text:
        return SUBPROCESS_EXECUTION
    if "mutation" in text or "governance" in text:
        return GOVERNANCE_MUTATION
    return None


def _call_router_for_summary(llm_router: Any, observation: Observation, context: Dict[str, Any]) -> str:
    prompt = (
        "Summarize the situation and constraints for a safe staged pipeline. "
        "Do not emit commands or code.\n\n"
        f"Observation intent={observation.detected_intent} source={observation.source}"
    )
    try:
        if hasattr(llm_router, "route") and callable(llm_router.route):
            raw = llm_router.route(prompt, context=context)
        elif hasattr(llm_router, "complete") and callable(llm_router.complete):
            raw = llm_router.complete(prompt)
        elif callable(llm_router):
            raw = llm_router(prompt)
        else:
            return ""
    except Exception as exc:
        logger.debug("think llm_router summary skipped: %s", exc)
        return ""
    return _redact_sensitive_text(str(raw))[:600]


def _fallback_observation(input_event: Any, context: Dict[str, Any]) -> Observation:
    return Observation(
        source=str(context.get("source") or "unknown"),
        raw_input=input_event,
        timestamp=_now_iso(),
        detected_intent="unknown",
        confidence=0.0,
        relevant_context_ids=_context_ids(context),
    )


def _fallback_thought(observation: Observation) -> ThoughtSummary:
    return ThoughtSummary(
        situation_summary="Thinking stage failed; using safe clarification path.",
        likely_goal="Clarify the requested action safely.",
        constraints=["No execution without validation.", "No raw command execution."],
        missing_information=["Think stage failed."],
        candidate_actions=[_ask_user_candidate("Thinking failed; ask for clarification.")],
    )


def _fallback_proposal(thought: ThoughtSummary) -> ActionProposal:
    return _proposal_from_candidate(_ask_user_candidate("Proposal failed; ask for clarification."))


def _blocked_validation(reason: str) -> ValidationResult:
    return ValidationResult(
        approved=False,
        risk_level="blocked",
        required_permissions=[],
        validation_notes=reason,
        safe_alternative=_ask_user_candidate("Validation failed closed."),
    )


def _skipped_execution(proposal: ActionProposal, reason: str) -> ExecutionLogEntry:
    now = _now_iso()
    return ExecutionLogEntry(
        action_id=proposal.action_id,
        action_type=proposal.action_type,
        tool_or_module_used=proposal.target_module_or_tool,
        start_time=now,
        end_time=now,
        success=False,
        output_summary="Execution skipped.",
        error=reason,
        result_payload={"skipped": True, "reason": reason},
    )


def _fallback_review(execution: ExecutionLogEntry) -> ReviewResult:
    return ReviewResult(
        did_it_work=False,
        usefulness_score=0.0,
        failure_reason=execution.error or "review_stage_failed",
        should_retry=False,
        should_create_memory=False,
        should_create_improvement_ticket=True,
    )


def _context_ids(context: Dict[str, Any]) -> List[str]:
    raw = context.get("relevant_context_ids", context.get("context_ids", []))
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return []
    return [str(item)[:120] for item in raw if str(item).strip()][:20]


def _raw_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key in ("message", "text", "raw_input", "request", "event", "summary", "query"):
            if value.get(key) is not None:
                parts.append(str(value.get(key)))
        if parts:
            return "\n".join(parts)
    return str(value)


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                out[key] = "[REDACTED]"
            else:
                out[key] = _redact_sensitive(item)
        return out
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def _redact_sensitive_text(text: str) -> str:
    return _SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text or "")


def _is_junk_memory(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 32:
        return True
    try:
        from ..memory_noise import is_low_value_memory_text

        return is_low_value_memory_text(stripped, min_chars_for_substantive=32)
    except Exception:
        return stripped.lower() in {"ok", "noop", "none", "ping", "pong"}


def _title_from_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return "Elysia pipeline task"
    return clean[:80]


def _normalize_risk(value: Any) -> RiskLevel:
    risk = str(value or "medium").strip().lower()
    if risk in {"low", "medium", "high", "blocked"}:
        return risk
    if risk in {"critical", "deny", "denied"}:
        return "blocked"
    return "medium"


def _max_risk_level(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "blocked": 3}
    return left if order.get(left, 1) >= order.get(right, 1) else right


def _dedupe(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        text = str(item)
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _get_attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    return getattr(obj, name, None)


def _summarize_for_log(value: Any) -> str:
    if isinstance(value, Observation):
        return (
            f"Observation(source={value.source}, intent={value.detected_intent}, "
            f"confidence={value.confidence:.2f})"
        )
    if isinstance(value, ThoughtSummary):
        return (
            f"Thought(goal={value.likely_goal[:120]!r}, "
            f"candidates={len(value.candidate_actions)})"
        )
    if isinstance(value, ActionProposal):
        return _proposal_summary(value)
    if isinstance(value, ValidationResult):
        return _validation_summary(value)
    if isinstance(value, ExecutionLogEntry):
        return _execution_summary(value)
    if isinstance(value, ReviewResult):
        return _review_summary(value)
    if isinstance(value, MemoryRecord):
        return f"MemoryRecord(type={value.memory_type}, stored={value.stored}, score={value.relevance_score:.2f})"
    text = _redact_sensitive_text(str(value))
    return re.sub(r"\s+", " ", text).strip()[:1000]


def _proposal_summary(proposal: ActionProposal) -> str:
    return (
        f"Proposal(id={proposal.action_id}, action={proposal.action_type}, "
        f"target={proposal.target_module_or_tool}, risk={proposal.estimated_risk})"
    )


def _validation_summary(validation: ValidationResult) -> str:
    return (
        f"Validation(approved={validation.approved}, risk={validation.risk_level}, "
        f"permissions={validation.required_permissions})"
    )


def _execution_summary(execution: ExecutionLogEntry) -> str:
    return (
        f"Execution(action_id={execution.action_id}, success={execution.success}, "
        f"target={execution.tool_or_module_used}, error={execution.error})"
    )


def _review_summary(review: ReviewResult) -> str:
    return (
        f"Review(worked={review.did_it_work}, score={review.usefulness_score:.2f}, "
        f"retry={review.should_retry}, memory={review.should_create_memory})"
    )
