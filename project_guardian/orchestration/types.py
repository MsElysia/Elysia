# project_guardian/orchestration/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskRequest:
    task_id: str
    task_type: str
    prompt: str
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteDecision:
    pipeline_id: str
    planner_model: Optional[str] = None
    executor_model: Optional[str] = None
    reviewer_model: Optional[str] = None
    fanout_models: List[str] = field(default_factory=list)
    judge_model: Optional[str] = None
    reason: str = ""


@dataclass
class NodeResult:
    node_id: str
    provider: str
    model: str
    output: Any
    success: bool
    latency_ms: float
    input_tokens_est: int = 0
    output_tokens_est: int = 0
    cost_estimate_usd: float = 0.0
    outcome_score: Optional[float] = None
    review_verdict: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PipelineResult:
    task_id: str
    pipeline_id: str
    success: bool
    final_output: Any
    node_results: List[NodeResult] = field(default_factory=list)
    route_reason: str = ""
    error: Optional[str] = None
