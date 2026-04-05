# project_guardian/orchestration/router/health.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from ..telemetry.sqlite_store import TelemetrySqliteStore
from .rules import parse_model_ref

DEFAULT_HEALTH_WINDOW_SEC = 7 * 86400


@dataclass
class RouteHealthSummary:
    task_type: str
    pipeline_id: str
    model: str
    recent_calls: int
    success_rate: float
    avg_outcome_score: Optional[float]
    invalid_intent_rate: float
    legacy_fallback_rate: float
    review_fail_rate: float
    recent_latency_ms: Optional[float]
    intent_validation_samples: int
    fallback_labeled_samples: int
    review_action_samples: int
    recommendation: str


def _rate(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return round(float(num) / float(den), 4)


async def summarize_route_health(
    store: TelemetrySqliteStore,
    task_type: str,
    pipeline_id: str,
    planner_model_ref: Optional[str],
    *,
    window_sec: float = DEFAULT_HEALTH_WINDOW_SEC,
) -> RouteHealthSummary:
    since_ts = time.time() - float(window_sec)
    from ...ollama_model_config import ollama_provider_ref

    prov, mod = parse_model_ref(planner_model_ref or ollama_provider_ref())
    model_display = f"{prov}:{mod}"
    raw = await store.aggregate_route_metrics(
        task_type=task_type,
        pipeline_id=pipeline_id,
        since_ts=since_ts,
        planner_provider=prov,
        planner_model_short=mod,
    )
    llm_total = int(raw.get("llm_total") or 0)
    llm_ok = int(raw.get("llm_ok") or 0)
    intent_labeled = int(raw.get("intent_labeled") or 0)
    invalid_intents = int(raw.get("invalid_intents") or 0)
    fb_labeled = int(raw.get("fallback_labeled") or 0)
    legacy_fb = int(raw.get("legacy_fallbacks") or 0)
    rev_total = int(raw.get("review_total") or 0)
    rev_fail = int(raw.get("review_fail") or 0)

    avg_out = raw.get("avg_outcome_score")
    if avg_out is not None:
        avg_out = round(float(avg_out), 4)
    avg_lat = raw.get("avg_latency_ms")
    if avg_lat is not None:
        avg_lat = round(float(avg_lat), 2)

    inv_rate = _rate(invalid_intents, intent_labeled)
    leg_rate = _rate(legacy_fb, fb_labeled)

    rec = "observe"
    if llm_total >= 5:
        sr = _rate(llm_ok, llm_total)
        if sr < 0.5 and intent_labeled < 3:
            rec = "consider_parallel_or_cloud"
        elif intent_labeled >= 3 and inv_rate > 0.35:
            rec = "consider_cloud_serial"
        elif fb_labeled >= 3 and leg_rate > 0.4:
            rec = "consider_cloud_serial"
        elif avg_out is not None and avg_out < 0.5:
            rec = "consider_cloud_serial"
        else:
            rec = "healthy"
    else:
        rec = "insufficient_samples"

    return RouteHealthSummary(
        task_type=task_type,
        pipeline_id=pipeline_id,
        model=model_display,
        recent_calls=llm_total,
        success_rate=_rate(llm_ok, llm_total) if llm_total else 0.0,
        avg_outcome_score=avg_out,
        invalid_intent_rate=inv_rate,
        legacy_fallback_rate=leg_rate,
        review_fail_rate=_rate(rev_fail, rev_total),
        recent_latency_ms=avg_lat,
        intent_validation_samples=intent_labeled,
        fallback_labeled_samples=fb_labeled,
        review_action_samples=rev_total,
        recommendation=rec,
    )
