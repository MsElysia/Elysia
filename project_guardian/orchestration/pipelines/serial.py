# project_guardian/orchestration/pipelines/serial.py
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from typing import Any, Awaitable, Callable, List, Optional, Tuple

from ..adapters.openai import OpenAIAdapter
from ..judge.deterministic import DeterministicJudge, strip_json_fence
from ..judge.model_judge import ModelJudge
from ..router.rules import parse_model_ref
from ...ollama_model_config import ollama_provider_ref
from ..telemetry.events import LLMCallEvent
from ..tools.bridge import execute_action_intent
from ..tools.candidates import build_capability_candidates, candidates_json_for_prompt
from ..tools.schemas import (
    ACTION_INTENT_SCHEMA,
    ActionIntent,
    ExecutionResult,
    execution_result_to_dict,
    parse_action_intent,
)
from ..tools.validator import ValidatedActionIntent, validate_action_intent
from ..types import NodeResult, PipelineResult, RouteDecision, TaskRequest
from .nodes import log_bridge_execution, log_validation_event, run_llm_node
from ..telemetry.sqlite_store import prompt_hash
from ...prompts.prompt_builder import build_prompt

logger = logging.getLogger(__name__)


def _telemetry_execution_path_for_intent(kind: str) -> str:
    k = (kind or "").lower()
    if k == "tool":
        return "tool"
    if k == "module":
        return "capability"
    return "model"


def _score_action_review(
    intent: Optional[ActionIntent],
    bridge_er: Optional[ExecutionResult],
    exec_nr: NodeResult,
    used_bridge: bool,
    *,
    validation: Optional[ValidatedActionIntent] = None,
) -> Tuple[float, str]:
    eff = intent
    if validation and validation.normalized_intent is not None:
        eff = validation.normalized_intent
    if validation and not validation.valid:
        return 0.25, f"validation_failed:{validation.reason}"
    if eff is None:
        return 0.35, "no_parseable_intent"
    if used_bridge and bridge_er is not None:
        iname = (eff.target_name or "").strip().lower()
        rname = (bridge_er.target_name or "").strip().lower()
        name_match = iname == rname and bool(iname)
        kind_match = eff.target_kind == bridge_er.target_kind
        base = 0.92 if (validation and validation.chosen_target_in_candidates) else 0.88
        if bridge_er.success and name_match and kind_match:
            return base, "intent_matches_successful_execution"
        if bridge_er.success:
            return 0.7, "executed_with_soft_mismatch"
        return 0.28, "execution_failed_vs_intent"
    if eff.target_kind != "none":
        return 0.42, "non_none_intent_used_model_executor"
    if exec_nr.success:
        return 0.66, "model_path_ok"
    return 0.22, "model_path_failed"


class SerialPlanExecuteReviewPipeline:
    pipeline_id = "serial_plan_execute_review"

    def __init__(
        self,
        get_adapter: Callable[[str], Any],
        telemetry_log: Callable[[Any], Awaitable[None]],
    ) -> None:
        self._get_adapter = get_adapter
        self._telemetry_log = telemetry_log
        self._det = DeterministicJudge()

    async def run(
        self,
        request: TaskRequest,
        route: RouteDecision,
        guardian: Any = None,
    ) -> PipelineResult:
        if request.task_type == "bounded_action":
            return await self._run_bounded_action(request, route, guardian)
        return await self._run_model_serial(request, route)

    async def _run_bounded_action(
        self,
        request: TaskRequest,
        route: RouteDecision,
        guardian: Any,
    ) -> PipelineResult:
        nodes: List[NodeResult] = []

        planner_ref = route.planner_model or ollama_provider_ref()
        exec_ref = route.executor_model or planner_ref
        rev_ref = route.reviewer_model
        if rev_ref and parse_model_ref(rev_ref) == parse_model_ref(exec_ref):
            rev_ref = None

        planner = self._get_adapter(planner_ref)
        executor = self._get_adapter(exec_ref)

        ctx = request.context if isinstance(request.context, dict) else {}
        bs = ctx.get("bounded_settings") if isinstance(ctx.get("bounded_settings"), dict) else {}
        min_conf = float(bs.get("min_action_confidence", 0.35))
        max_cand = int(bs.get("max_action_candidates", 5))
        inv_fb = str(bs.get("invalid_intent_fallback", "legacy_capability_loop"))
        if inv_fb not in ("legacy_capability_loop", "model_only"):
            inv_fb = "legacy_capability_loop"

        caps = list(ctx.get("allowed_capabilities") or [])
        arch = str(ctx.get("archetype") or "")
        reg_hint = ctx.get("capability_registry_hint")
        candidates = build_capability_candidates(
            allowed_capabilities=caps,
            archetype=arch,
            max_candidates=max_cand,
            registry_hint=reg_hint if isinstance(reg_hint, dict) else None,
        )
        cand_tel = {"candidate_count": len(candidates)}

        _exec_system_bounded = build_prompt(
            "planner",
            "executor",
            task_text="Executor step: follow the task payload; output JSON if the host requested a schema.",
        )

        plan_prompt = (
            "You MUST emit ActionIntent JSON only.\n"
            "Pick exactly one entry from CANDIDATES by copying its target_kind and target_name,\n"
            'OR set target_kind to \"none\" and action_type to \"model_only\" if unsafe.\n'
            "Do not invent modules or tools outside CANDIDATES.\n\n"
            f"CANDIDATES:\n{candidates_json_for_prompt(candidates)}\n\n"
            f"Task:\n{request.prompt[:8000]}"
        )
        plan_system = build_prompt(
            "planner",
            "orchestrator",
            task_text="Planner step: emit ActionIntent JSON only for the bounded capability task.",
            extra_rules=["Pick from CANDIDATES only; emit JSON; no markdown."],
        )
        plan_temp = float(request.metadata.get("planner_temperature", 0.25) or 0.25)
        if isinstance(planner, OpenAIAdapter):
            plan_nr = await run_llm_node(
                node_id="plan",
                adapter=planner,
                task_id=request.task_id,
                task_type=request.task_type,
                pipeline_id=self.pipeline_id,
                prompt=plan_prompt,
                system=plan_system,
                telemetry_log=self._telemetry_log,
                execution_path="model",
                action_type="plan",
                temperature=plan_temp,
                response_format_json=True,
                tel_meta=cand_tel,
            )
        else:
            plan_nr = await run_llm_node(
                node_id="plan",
                adapter=planner,
                task_id=request.task_id,
                task_type=request.task_type,
                pipeline_id=self.pipeline_id,
                prompt=plan_prompt,
                system=plan_system,
                telemetry_log=self._telemetry_log,
                execution_path="model",
                action_type="plan",
                temperature=plan_temp,
                format=ACTION_INTENT_SCHEMA,
                tel_meta=cand_tel,
            )
        nodes.append(plan_nr)

        raw_intent = parse_action_intent(str(plan_nr.output or ""))
        validated = validate_action_intent(
            raw_intent,
            candidates,
            min_confidence=min_conf,
            invalid_fallback=inv_fb,
        )
        await log_validation_event(
            self._telemetry_log,
            task_id=request.task_id,
            task_type=request.task_type,
            pipeline_id=self.pipeline_id,
            candidate_count=len(candidates),
            valid=validated.valid,
            reason=validated.reason,
            fallback_mode=validated.fallback_mode,
            chosen_in_set=validated.chosen_target_in_candidates,
        )

        bridge_er: Optional[ExecutionResult] = None
        used_bridge = False
        exec_nr: NodeResult
        tel_common = {
            "candidate_count": len(candidates),
            "chosen_target_in_candidates": validated.chosen_target_in_candidates,
            "action_intent_valid": validated.valid,
            "validation_reason": validated.reason[:200],
            "fallback_mode": validated.fallback_mode,
        }

        if not validated.valid:
            if validated.fallback_mode == "model_only":
                exec_prompt = (
                    request.prompt
                    + "\n\n---\nValidation failed; answer with best-effort text/JSON.\nReason: "
                    + validated.reason
                    + "\nRaw plan output:\n"
                    + str(plan_nr.output)[:3000]
                )
                exec_temp = float(request.metadata.get("executor_temperature", 0.3) or 0.3)
                exec_kwargs: dict = {"temperature": exec_temp}
                meta_schema = request.metadata.get("ollama_json_schema")
                if isinstance(meta_schema, dict):
                    if isinstance(executor, OpenAIAdapter):
                        exec_kwargs["response_format_json"] = True
                    else:
                        exec_kwargs["format"] = meta_schema
                exec_nr = await run_llm_node(
                    node_id="execute",
                    adapter=executor,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    pipeline_id=self.pipeline_id,
                    prompt=exec_prompt,
                    system=_exec_system_bounded,
                    telemetry_log=self._telemetry_log,
                    execution_path="model",
                    tel_meta=tel_common,
                    **exec_kwargs,
                )
                nodes.append(exec_nr)
            else:
                exec_nr = NodeResult(
                    node_id="execute_skipped",
                    provider="deterministic",
                    model="legacy_fallback",
                    output=json.dumps({"skipped": True, "reason": validated.reason}),
                    success=False,
                    latency_ms=0.0,
                    error=validated.reason,
                )
                nodes.append(exec_nr)
        elif validated.normalized_intent and validated.normalized_intent.target_kind in (
            "module",
            "tool",
        ):
            if guardian is None:
                logger.debug("bounded_action: validated intent but no guardian; legacy fallback")
                exec_nr = NodeResult(
                    node_id="execute_skipped",
                    provider="deterministic",
                    model="no_guardian",
                    output="",
                    success=False,
                    latency_ms=0.0,
                    error="no_guardian",
                )
                nodes.append(exec_nr)
                validated = ValidatedActionIntent(
                    valid=False,
                    normalized_intent=validated.normalized_intent,
                    fallback_mode="legacy_capability_loop",
                    reason="no_guardian_for_bridge",
                    chosen_target_in_candidates=validated.chosen_target_in_candidates,
                )
            else:
                exec_i = validated.normalized_intent
                t0 = time.perf_counter()
                allowed_list = list(caps) if caps else []
                er = execute_action_intent(
                    guardian,
                    exec_i,
                    allowed_capabilities=allowed_list or None,
                    task_context=request.context,
                )
                lat = (time.perf_counter() - t0) * 1000
                bridge_er = er
                used_bridge = True
                out_json = json.dumps(execution_result_to_dict(er))
                exec_nr = NodeResult(
                    node_id="execute_capability",
                    provider="capability_bridge",
                    model="execute_capability_kind",
                    output=out_json,
                    success=er.success,
                    latency_ms=lat,
                    input_tokens_est=0,
                    output_tokens_est=max(1, len(out_json) // 4),
                    cost_estimate_usd=0.0,
                    error=er.error,
                )
                ep = _telemetry_execution_path_for_intent(exec_i.target_kind)
                sc = bool(er.success and er.payload.get("result") is not None)
                await log_bridge_execution(
                    self._telemetry_log,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    pipeline_id=self.pipeline_id,
                    node_id="execute_capability",
                    action_type=exec_i.action_type,
                    target_kind=exec_i.target_kind,
                    target_name=exec_i.target_name or "",
                    execution_path=ep,
                    success=er.success,
                    latency_ms=lat,
                    state_change_detected=sc,
                    tel_meta=tel_common,
                )
                nodes.append(exec_nr)
        else:
            exec_prompt = (
                request.prompt
                + "\n\n---\nValidated intent: model_only path.\nPlan:\n"
                + str(plan_nr.output)[:4000]
            )
            exec_temp = float(request.metadata.get("executor_temperature", 0.3) or 0.3)
            exec_kwargs2: dict = {"temperature": exec_temp}
            meta_schema = request.metadata.get("ollama_json_schema")
            if isinstance(meta_schema, dict):
                if isinstance(executor, OpenAIAdapter):
                    exec_kwargs2["response_format_json"] = True
                else:
                    exec_kwargs2["format"] = meta_schema
            exec_nr = await run_llm_node(
                node_id="execute",
                adapter=executor,
                task_id=request.task_id,
                task_type=request.task_type,
                pipeline_id=self.pipeline_id,
                prompt=exec_prompt,
                system=_exec_system_bounded,
                telemetry_log=self._telemetry_log,
                execution_path="model",
                action_type=validated.normalized_intent.action_type if validated.normalized_intent else None,
                target_kind="none",
                target_name=None,
                tel_meta=tel_common,
                **exec_kwargs2,
            )
            nodes.append(exec_nr)

        eff_intent = (
            validated.normalized_intent
            if validated.normalized_intent is not None
            else raw_intent
        )
        r_score, r_verdict = _score_action_review(
            eff_intent, bridge_er, exec_nr, used_bridge, validation=validated
        )
        review_nr = NodeResult(
            node_id="review_action",
            provider="deterministic",
            model="action_execution_review",
            output=json.dumps({"verdict": r_verdict, "outcome_score": r_score}),
            success=r_score >= 0.55,
            latency_ms=0.0,
            outcome_score=r_score,
            review_verdict=r_verdict,
        )
        nodes.append(review_nr)
        await self._telemetry_log(
            LLMCallEvent(
                task_id=request.task_id,
                pipeline_id=self.pipeline_id,
                node_id="review_action",
                provider="deterministic",
                model="action_execution_review",
                prompt_hash=prompt_hash(r_verdict),
                latency_ms=0.0,
                input_tokens_est=1,
                output_tokens_est=1,
                cost_estimate_usd=0.0,
                outcome_score=r_score,
                review_verdict=r_verdict,
                success=r_score >= 0.55,
                task_type=request.task_type,
                action_type=eff_intent.action_type if eff_intent else None,
                target_kind=eff_intent.target_kind if eff_intent else None,
                target_name=eff_intent.target_name if eff_intent else None,
                execution_path="model",
                state_change_detected=bool(bridge_er and bridge_er.success) if bridge_er else None,
                candidate_count=len(candidates),
                chosen_target_in_candidates=validated.chosen_target_in_candidates,
                action_intent_valid=validated.valid,
                validation_reason=validated.reason[:300],
                fallback_mode=validated.fallback_mode,
            )
        )

        gov: Any = None
        if bridge_er is not None:
            gov = bridge_er.result_for_governance()
        elif exec_nr.node_id == "execute_skipped":
            gov = None
        else:
            ft = strip_json_fence(str(exec_nr.output or ""))
            try:
                gov = json.loads(ft) if ft.strip().startswith("{") else ft
            except Exception:
                gov = ft if ft else None

        final_bundle = {
            "candidates": [c.to_planner_dict() for c in candidates],
            "validation": {
                "valid": validated.valid,
                "reason": validated.reason,
                "fallback_mode": validated.fallback_mode,
                "chosen_target_in_candidates": validated.chosen_target_in_candidates,
            },
            "action_intent_raw": asdict(raw_intent) if raw_intent else None,
            "action_intent": asdict(validated.normalized_intent) if validated.normalized_intent else None,
            "execution": execution_result_to_dict(bridge_er)
            if bridge_er
            else (
                {"mode": "skipped_legacy_fallback", "reason": validated.reason}
                if exec_nr.node_id == "execute_skipped"
                else {"mode": "model", "output": exec_nr.output}
            ),
            "review_verdict": r_verdict,
            "outcome_score": r_score,
            "result_for_governance": gov,
        }
        ok = (
            (bridge_er.success if bridge_er is not None else exec_nr.success)
            and r_score >= 0.45
            and exec_nr.node_id != "execute_skipped"
        )
        return PipelineResult(
            task_id=request.task_id,
            pipeline_id=self.pipeline_id,
            success=bool(ok),
            final_output=final_bundle,
            node_results=nodes,
            route_reason=route.reason,
            error=None if ok else "bounded_action_incomplete",
        )

    async def _run_model_serial(self, request: TaskRequest, route: RouteDecision) -> PipelineResult:
        nodes: List[NodeResult] = []

        planner_ref = route.planner_model or ollama_provider_ref()
        exec_ref = route.executor_model or planner_ref
        rev_ref = route.reviewer_model

        if rev_ref and parse_model_ref(rev_ref) == parse_model_ref(exec_ref):
            rev_ref = None

        planner = self._get_adapter(planner_ref)
        executor = self._get_adapter(exec_ref)

        _serial_plan_sys = build_prompt(
            "planner",
            "orchestrator",
            task_text="Produce a short bullet plan (max 5 bullets) for the user task; plain lines starting with '- '.",
            extra_rules=["No JSON in the plan body."],
        )
        _serial_exec_sys = build_prompt(
            "planner",
            "executor",
            task_text="Execute the full task using the coordinator plan; output only what the task requires.",
        )

        plan_prompt = (
            "Produce a short bullet plan (max 5 bullets) for how to answer the user task. "
            "No JSON; plain lines starting with '- '.\n\n"
            + request.prompt[:12_000]
        )
        plan_temp = float(request.metadata.get("planner_temperature", 0.25) or 0.25)
        plan_nr = await run_llm_node(
            node_id="plan",
            adapter=planner,
            task_id=request.task_id,
            task_type=request.task_type,
            pipeline_id=self.pipeline_id,
            prompt=plan_prompt,
            system=_serial_plan_sys,
            telemetry_log=self._telemetry_log,
            temperature=plan_temp,
            execution_path="model",
        )
        nodes.append(plan_nr)

        exec_prompt = (
            request.prompt
            + "\n\n---\nCoordinator plan:\n"
            + str(plan_nr.output)[:4000]
        )
        exec_temp = float(request.metadata.get("executor_temperature", 0.3) or 0.3)
        exec_kwargs: dict = {"temperature": exec_temp}
        meta_schema = request.metadata.get("ollama_json_schema")
        if isinstance(meta_schema, dict):
            if isinstance(executor, OpenAIAdapter):
                exec_kwargs["response_format_json"] = True
            else:
                exec_kwargs["format"] = meta_schema

        exec_nr = await run_llm_node(
            node_id="execute",
            adapter=executor,
            task_id=request.task_id,
            task_type=request.task_type,
            pipeline_id=self.pipeline_id,
            prompt=exec_prompt,
            system=_serial_exec_sys,
            telemetry_log=self._telemetry_log,
            execution_path="model",
            **exec_kwargs,
        )
        nodes.append(exec_nr)

        det = await self._det.compare([exec_nr], request)
        nodes.append(det)

        final_text = strip_json_fence(str(exec_nr.output or ""))
        if det.review_verdict == "inconclusive" or (not det.success and rev_ref):
            try:
                rev_adapt = self._get_adapter(rev_ref)
                ep, em = parse_model_ref(exec_ref)
                rp, rm = parse_model_ref(rev_ref)
                if (ep, em) == (rp, rm):
                    logger.debug("serial review skipped: same adapter as execute")
                else:
                    mj = ModelJudge(rev_adapt)
                    fix_prompt = (
                        "Fix or validate the following output. Return ONLY valid JSON if the task expects JSON.\n\n"
                        + final_text[:8000]
                    )
                    mnr = await run_llm_node(
                        node_id="review_model",
                        adapter=rev_adapt,
                        task_id=request.task_id,
                        task_type=request.task_type,
                        pipeline_id=self.pipeline_id,
                        prompt=fix_prompt,
                        system=build_prompt(
                            "debugger",
                            "critic",
                            task_text="Review another model's output; fix or validate; do not repeat its mistakes.",
                            output_schema={"type": "freeform_or_json", "note": "JSON only if task expects JSON"},
                        ),
                        telemetry_log=self._telemetry_log,
                        temperature=0.1,
                        execution_path="model",
                    )
                    nodes.append(mnr)
                    final_text = strip_json_fence(str(mnr.output or final_text))
            except Exception as e:
                logger.debug("serial model review skipped: %s", e)

        parsed: Any = final_text
        try:
            parsed = json.loads(final_text) if final_text.strip().startswith("{") else final_text
        except Exception:
            parsed = final_text

        ok = det.success or bool(str(final_text).strip())
        return PipelineResult(
            task_id=request.task_id,
            pipeline_id=self.pipeline_id,
            success=ok,
            final_output=parsed,
            node_results=nodes,
            route_reason=route.reason,
            error=None if ok else "review_failed",
        )
