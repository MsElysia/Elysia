# project_guardian/orchestration/pipelines/nodes.py
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from ..adapters.base import LLMAdapter
from ..telemetry.events import LLMCallEvent
from ..telemetry.sqlite_store import prompt_hash
from ..types import NodeResult


def _est_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def _telemetry_meta_fields(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not meta:
        return {}
    keys = (
        "candidate_count",
        "chosen_target_in_candidates",
        "action_intent_valid",
        "validation_reason",
        "fallback_mode",
    )
    return {k: meta[k] for k in keys if k in meta}


async def run_llm_node(
    *,
    node_id: str,
    adapter: LLMAdapter,
    task_id: str,
    task_type: str,
    pipeline_id: str,
    prompt: str,
    system: Optional[str],
    telemetry_log: Callable[..., Any],
    execution_path: str = "model",
    action_type: Optional[str] = None,
    target_kind: Optional[str] = None,
    target_name: Optional[str] = None,
    state_change_detected: Optional[bool] = None,
    tel_meta: Optional[Dict[str, Any]] = None,
    **gen_kwargs: Any,
) -> NodeResult:
    t0 = time.perf_counter()
    err: Optional[str] = None
    out_text = ""
    try:
        out_text = await adapter.generate(prompt, system=system, **gen_kwargs)
        ok = bool(out_text.strip())
    except Exception as e:
        err = str(e)[:500]
        ok = False
    lat = (time.perf_counter() - t0) * 1000
    in_t = _est_tokens((system or "") + prompt)
    out_t = _est_tokens(out_text)
    cost = adapter.estimate_cost(in_t, out_t)
    nr = NodeResult(
        node_id=node_id,
        provider=adapter.provider_name,
        model=adapter.model_name,
        output=out_text,
        success=ok,
        latency_ms=lat,
        input_tokens_est=in_t,
        output_tokens_est=out_t,
        cost_estimate_usd=cost,
        error=err,
    )
    tm = _telemetry_meta_fields(tel_meta)
    await telemetry_log(
        LLMCallEvent(
            task_id=task_id,
            pipeline_id=pipeline_id,
            node_id=node_id,
            provider=adapter.provider_name,
            model=adapter.model_name,
            prompt_hash=prompt_hash(prompt),
            latency_ms=lat,
            input_tokens_est=in_t,
            output_tokens_est=out_t,
            cost_estimate_usd=cost,
            outcome_score=None,
            review_verdict=None,
            success=ok,
            task_type=task_type,
            action_type=action_type,
            target_kind=target_kind,
            target_name=target_name,
            execution_path=execution_path,
            state_change_detected=state_change_detected,
            candidate_count=tm.get("candidate_count"),
            chosen_target_in_candidates=tm.get("chosen_target_in_candidates"),
            action_intent_valid=tm.get("action_intent_valid"),
            validation_reason=tm.get("validation_reason"),
            fallback_mode=tm.get("fallback_mode"),
        )
    )
    return nr


async def log_bridge_execution(
    telemetry_log: Callable[..., Any],
    *,
    task_id: str,
    task_type: str,
    pipeline_id: str,
    node_id: str,
    action_type: str,
    target_kind: str,
    target_name: str,
    execution_path: str,
    success: bool,
    latency_ms: float,
    state_change_detected: bool,
    outcome_score: Optional[float] = None,
    review_verdict: Optional[str] = None,
    tel_meta: Optional[Dict[str, Any]] = None,
) -> None:
    key = f"{target_kind}:{target_name}"
    tm = _telemetry_meta_fields(tel_meta)
    await telemetry_log(
        LLMCallEvent(
            task_id=task_id,
            pipeline_id=pipeline_id,
            node_id=node_id,
            provider="capability_bridge",
            model="execute_capability_kind",
            prompt_hash=prompt_hash(key),
            latency_ms=latency_ms,
            input_tokens_est=max(1, len(key) // 4),
            output_tokens_est=0,
            cost_estimate_usd=0.0,
            outcome_score=outcome_score,
            review_verdict=review_verdict,
            success=success,
            task_type=task_type,
            action_type=action_type,
            target_kind=target_kind,
            target_name=target_name,
            execution_path=execution_path,
            state_change_detected=state_change_detected,
            candidate_count=tm.get("candidate_count"),
            chosen_target_in_candidates=tm.get("chosen_target_in_candidates"),
            action_intent_valid=tm.get("action_intent_valid"),
            validation_reason=tm.get("validation_reason"),
            fallback_mode=tm.get("fallback_mode"),
        )
    )


async def log_validation_event(
    telemetry_log: Callable[..., Any],
    *,
    task_id: str,
    task_type: str,
    pipeline_id: str,
    candidate_count: int,
    valid: bool,
    reason: str,
    fallback_mode: str,
    chosen_in_set: bool,
) -> None:
    await telemetry_log(
        LLMCallEvent(
            task_id=task_id,
            pipeline_id=pipeline_id,
            node_id="validate",
            provider="deterministic",
            model="action_intent_validator",
            prompt_hash=prompt_hash(reason),
            latency_ms=0.0,
            input_tokens_est=1,
            output_tokens_est=1,
            cost_estimate_usd=0.0,
            outcome_score=None,
            review_verdict=None,
            success=valid,
            task_type=task_type,
            execution_path="model",
            candidate_count=candidate_count,
            chosen_target_in_candidates=chosen_in_set,
            action_intent_valid=valid,
            validation_reason=reason[:400],
            fallback_mode=fallback_mode,
        )
    )
