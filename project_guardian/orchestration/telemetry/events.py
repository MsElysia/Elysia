# project_guardian/orchestration/telemetry/events.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMCallEvent:
    task_id: str
    pipeline_id: str
    node_id: str
    provider: str
    model: str
    prompt_hash: str
    latency_ms: float
    input_tokens_est: int
    output_tokens_est: int
    cost_estimate_usd: float
    outcome_score: Optional[float]
    review_verdict: Optional[str]
    success: bool
    task_type: str = ""
    action_type: Optional[str] = None
    target_kind: Optional[str] = None
    target_name: Optional[str] = None
    execution_path: Optional[str] = None
    state_change_detected: Optional[bool] = None
    candidate_count: Optional[int] = None
    chosen_target_in_candidates: Optional[bool] = None
    action_intent_valid: Optional[bool] = None
    validation_reason: Optional[str] = None
    fallback_mode: Optional[str] = None
