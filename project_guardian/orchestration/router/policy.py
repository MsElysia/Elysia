# project_guardian/orchestration/router/policy.py
from __future__ import annotations

import copy
import time
from typing import Optional

from ..telemetry.sqlite_store import TelemetrySqliteStore
from ..types import RouteDecision, TaskRequest
from .health import RouteHealthSummary, summarize_route_health
from ...ollama_model_config import ollama_provider_ref
from .rules import _openai_available, _resolve_reviewer
from .task_types import CRITIQUE

MIN_LLM_SAMPLE = 5
MIN_LLM_SAMPLE_STRICT = 8
MIN_VALIDATION_SAMPLE = 4
MIN_PARALLEL_BRANCH_SAMPLE = 6
HEALTH_WINDOW_SEC = 7 * 86400

INVALID_INTENT_ESCALATE = 0.38
LEGACY_FALLBACK_ESCALATE = 0.45
OUTCOME_WEAK = 0.48
SUCCESS_WEAK = 0.48
PARALLEL_NO_GAIN_EPS = 0.02


def _weak_serial_route(h: RouteHealthSummary) -> bool:
    if h.intent_validation_samples >= MIN_VALIDATION_SAMPLE and h.invalid_intent_rate >= INVALID_INTENT_ESCALATE:
        return True
    if h.fallback_labeled_samples >= MIN_VALIDATION_SAMPLE and h.legacy_fallback_rate >= LEGACY_FALLBACK_ESCALATE:
        return True
    if h.avg_outcome_score is not None and h.avg_outcome_score < OUTCOME_WEAK and h.recent_calls >= MIN_LLM_SAMPLE:
        return True
    if h.recent_calls >= MIN_LLM_SAMPLE and h.success_rate < SUCCESS_WEAK:
        return True
    return False


def _repeated_local_failure(h: RouteHealthSummary) -> bool:
    if h.recent_calls < MIN_LLM_SAMPLE_STRICT:
        return False
    if h.success_rate < 0.42:
        return True
    if h.avg_outcome_score is not None and h.avg_outcome_score < 0.4 and h.recent_calls >= MIN_LLM_SAMPLE:
        return True
    if h.review_action_samples >= 3 and h.review_fail_rate >= 0.55:
        return True
    return False


async def adapt_route_from_telemetry(
    *,
    base: RouteDecision,
    request: TaskRequest,
    telemetry: TelemetrySqliteStore,
    effective_task_type: str,
) -> RouteDecision:
    openai_ok = _openai_available()
    meta = request.metadata or {}
    high_stakes = bool(meta.get("high_stakes"))
    uncertainty = str((request.context or {}).get("uncertainty_level") or "").lower()
    yaml_parallel = base.pipeline_id == "parallel_compare_and_judge"

    since_ts = time.time() - HEALTH_WINDOW_SEC
    serial_id = "serial_plan_execute_review"
    parallel_id = "parallel_compare_and_judge"

    raw_par = await telemetry.aggregate_route_metrics(
        task_type=effective_task_type,
        pipeline_id=parallel_id,
        since_ts=since_ts,
        planner_provider=None,
        planner_model_short=None,
    )
    raw_ser = await telemetry.aggregate_route_metrics(
        task_type=effective_task_type,
        pipeline_id=serial_id,
        since_ts=since_ts,
        planner_provider=None,
        planner_model_short=None,
    )

    h_serial = await summarize_route_health(
        telemetry,
        effective_task_type,
        serial_id,
        base.planner_model,
        window_sec=HEALTH_WINDOW_SEC,
    )
    par_fan_total = int(raw_par.get("fanout_total") or 0)
    par_fan_ok = int(raw_par.get("fanout_ok") or 0)
    ser_llm_total = int(raw_ser.get("llm_total") or 0)
    ser_llm_ok = int(raw_ser.get("llm_ok") or 0)
    par_fan_sr = (par_fan_ok / par_fan_total) if par_fan_total else None
    ser_llm_sr = (ser_llm_ok / ser_llm_total) if ser_llm_total else None

    out = copy.deepcopy(base)
    tel_reason: Optional[str] = None

    par_fan_early = int(raw_par.get("fanout_total") or 0)
    has_validation_signal = h_serial.intent_validation_samples > 0 or h_serial.fallback_labeled_samples > 0
    insufficient = (
        h_serial.recent_calls < MIN_LLM_SAMPLE
        and par_fan_early < MIN_PARALLEL_BRANCH_SAMPLE
        and not has_validation_signal
    )
    if insufficient:
        tel_reason = "yaml_default_local_first"
        out.reason = _join_reason(base.reason, tel_reason)
        return out

    if yaml_parallel and effective_task_type != CRITIQUE and not high_stakes and uncertainty != "high":
        if (
            par_fan_total >= MIN_PARALLEL_BRANCH_SAMPLE
            and ser_llm_total >= MIN_LLM_SAMPLE
            and par_fan_sr is not None
            and ser_llm_sr is not None
            and par_fan_sr + PARALLEL_NO_GAIN_EPS < ser_llm_sr
        ):
            out.pipeline_id = serial_id
            out.fanout_models = []
            out.judge_model = None
            if openai_ok and "openai" not in (out.executor_model or ""):
                out.executor_model = "openai:gpt-4.1-mini"
            out.reviewer_model = _resolve_reviewer(
                out.executor_model or "",
                out.reviewer_model,
                out.planner_model or ollama_provider_ref(),
            )
            tel_reason = "reverted_from_parallel_due_to_no_quality_gain"
            out.reason = _join_reason(base.reason, tel_reason)
            return out

    if base.pipeline_id == serial_id:
        weak = _weak_serial_route(h_serial)
        repeated = _repeated_local_failure(h_serial)
        if not weak and not repeated:
            tel_reason = "kept_serial_due_to_healthy_local_route"
            out.reason = _join_reason(base.reason, tel_reason)
            return out

        if repeated or (uncertainty == "high"):
            out.pipeline_id = parallel_id
            fan = list(base.fanout_models or [])
            if len(fan) < 2:
                fan = [ollama_provider_ref(), "openai:gpt-4.1-mini"]
            if not openai_ok:
                _pl = base.planner_model or ollama_provider_ref()
                fan = [_pl, _pl]
                while len(fan) < 2:
                    fan.append(ollama_provider_ref())
            out.fanout_models = fan[:2]
            out.judge_model = "openai:gpt-4.1-mini" if openai_ok else None
            tel_reason = "escalated_parallel_due_to_repeated_local_failures"
            out.reason = _join_reason(base.reason, tel_reason)
            return out

        if weak and openai_ok:
            out.executor_model = "openai:gpt-4.1-mini"
            out.reviewer_model = _resolve_reviewer(
                out.executor_model,
                out.reviewer_model,
                out.planner_model or ollama_provider_ref(),
            )
            if (
                h_serial.intent_validation_samples >= MIN_VALIDATION_SAMPLE
                and h_serial.invalid_intent_rate >= INVALID_INTENT_ESCALATE
            ):
                tel_reason = "escalated_cloud_due_to_invalid_intents"
            elif (
                h_serial.fallback_labeled_samples >= MIN_VALIDATION_SAMPLE
                and h_serial.legacy_fallback_rate >= LEGACY_FALLBACK_ESCALATE
            ):
                tel_reason = "escalated_cloud_due_to_legacy_fallbacks"
            elif h_serial.avg_outcome_score is not None and h_serial.avg_outcome_score < OUTCOME_WEAK:
                tel_reason = "escalated_cloud_due_to_low_outcome_scores"
            else:
                tel_reason = "escalated_cloud_due_to_weak_local_route"
            out.reason = _join_reason(base.reason, tel_reason)
            return out

        if weak and not openai_ok:
            tel_reason = "yaml_default_local_first"
            out.reason = _join_reason(base.reason, tel_reason)
            return out

    if out.pipeline_id == parallel_id:
        tel_reason = "kept_parallel_due_to_yaml"
    else:
        tel_reason = "kept_serial_due_to_healthy_local_route"
    out.reason = _join_reason(base.reason, tel_reason)
    return out


def _join_reason(base_reason: str, telemetry_tag: str) -> str:
    br = (base_reason or "").strip()
    if not br:
        return f"telemetry:{telemetry_tag}"
    if telemetry_tag in br:
        return br
    return f"{br}; telemetry:{telemetry_tag}"
