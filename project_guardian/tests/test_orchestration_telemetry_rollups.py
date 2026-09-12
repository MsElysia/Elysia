from __future__ import annotations

import asyncio
import time

from project_guardian.orchestration.telemetry.events import LLMCallEvent
from project_guardian.orchestration.telemetry.sqlite_store import TelemetrySqliteStore


def _event(
    node_id: str,
    *,
    success: bool,
    validation_reason: str | None = None,
    action_intent_valid: bool | None = None,
    review_verdict: str | None = None,
) -> LLMCallEvent:
    return LLMCallEvent(
        task_id="t1",
        task_type="reasoning",
        pipeline_id="serial_plan_execute_review",
        node_id=node_id,
        provider="ollama",
        model="llama3.2:3b",
        prompt_hash="hash",
        latency_ms=1.0,
        input_tokens_est=10,
        output_tokens_est=12,
        cost_estimate_usd=0.0,
        outcome_score=None,
        review_verdict=review_verdict,
        success=success,
        action_intent_valid=action_intent_valid,
        validation_reason=validation_reason,
    )


def test_aggregate_route_metrics_splits_invalid_intent_reasons(tmp_path) -> None:
    store = TelemetrySqliteStore(tmp_path / "telemetry.db")
    asyncio.run(store.log_call(_event("plan", success=False)))
    asyncio.run(
        store.log_call(
            _event(
                "validate",
                success=False,
                action_intent_valid=False,
                validation_reason="unparseable_intent",
            )
        )
    )
    asyncio.run(
        store.log_call(
            _event(
                "validate",
                success=False,
                action_intent_valid=False,
                validation_reason="not_in_candidates",
            )
        )
    )
    asyncio.run(store.log_call(_event("review_action", success=False, review_verdict="reject")))

    m = asyncio.run(
        store.aggregate_route_metrics(
            task_type="reasoning",
            pipeline_id="serial_plan_execute_review",
            since_ts=time.time() - 60.0,
        )
    )

    assert m["llm_total"] >= 1
    assert m["invalid_intents"] == 2
    assert m["invalid_unparseable_intent"] == 1
    assert m["invalid_policy_or_candidate_mismatch"] == 1
    assert m["review_fail"] == 1
