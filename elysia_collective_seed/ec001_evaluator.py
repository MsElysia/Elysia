"""Evaluation helpers for Elysia Collective experiment EC-001.

The evaluator is model-agnostic. Human raters or automated benchmark adapters can
supply normalized 0..1 scores for a control run and a collective run. This module
computes deltas, cost-normalized lift, and guardrail flags without making model
calls or changing Guardian state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Mapping, Optional


DEFAULT_DIMENSIONS = (
    "accuracy",
    "completeness",
    "originality",
    "risk_detection",
    "implementation_feasibility",
    "self_correction",
    "provenance_quality",
)


@dataclass(frozen=True)
class RunScores:
    label: str
    dimensions: Mapping[str, float]
    cost_units: float
    latency_units: float = 0.0
    severe_error_count: int = 0
    unsupported_claim_count: int = 0


@dataclass(frozen=True)
class Evaluation:
    control_label: str
    collective_label: str
    mean_control: float
    mean_collective: float
    absolute_lift: float
    relative_lift: Optional[float]
    cost_ratio: Optional[float]
    lift_per_extra_cost: Optional[float]
    per_dimension_delta: Dict[str, float]
    collective_wins: List[str]
    control_wins: List[str]
    ties: List[str]
    guardrail_flags: List[str]


def _bounded(value: float, field: str) -> float:
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1, got {value}")
    return value


def normalize(run: RunScores, dimensions: Iterable[str] = DEFAULT_DIMENSIONS) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for name in dimensions:
        if name not in run.dimensions:
            raise ValueError(f"missing dimension {name!r} for {run.label}")
        out[name] = _bounded(run.dimensions[name], f"{run.label}.{name}")
    if run.cost_units < 0:
        raise ValueError("cost_units must be non-negative")
    if run.latency_units < 0:
        raise ValueError("latency_units must be non-negative")
    return out


def evaluate(
    control: RunScores,
    collective: RunScores,
    dimensions: Iterable[str] = DEFAULT_DIMENSIONS,
    *,
    tie_epsilon: float = 0.01,
) -> Evaluation:
    dims = tuple(dimensions)
    c = normalize(control, dims)
    k = normalize(collective, dims)

    mean_c = sum(c.values()) / len(dims)
    mean_k = sum(k.values()) / len(dims)
    lift = mean_k - mean_c
    relative = None if mean_c == 0 else lift / mean_c
    cost_ratio = None if control.cost_units == 0 else collective.cost_units / control.cost_units
    extra_cost = collective.cost_units - control.cost_units
    lift_per_extra_cost = None if extra_cost <= 0 else lift / extra_cost

    deltas = {name: k[name] - c[name] for name in dims}
    wins: List[str] = []
    losses: List[str] = []
    ties: List[str] = []
    for name, delta in deltas.items():
        if delta > tie_epsilon:
            wins.append(name)
        elif delta < -tie_epsilon:
            losses.append(name)
        else:
            ties.append(name)

    flags: List[str] = []
    if collective.severe_error_count > control.severe_error_count:
        flags.append("collective_increased_severe_errors")
    if collective.unsupported_claim_count > control.unsupported_claim_count:
        flags.append("collective_increased_unsupported_claims")
    if lift <= 0:
        flags.append("no_positive_collective_lift")
    if cost_ratio is not None and cost_ratio >= 2.0 and lift < 0.05:
        flags.append("weak_lift_for_cost")

    return Evaluation(
        control_label=control.label,
        collective_label=collective.label,
        mean_control=round(mean_c, 6),
        mean_collective=round(mean_k, 6),
        absolute_lift=round(lift, 6),
        relative_lift=None if relative is None else round(relative, 6),
        cost_ratio=None if cost_ratio is None else round(cost_ratio, 6),
        lift_per_extra_cost=None if lift_per_extra_cost is None else round(lift_per_extra_cost, 6),
        per_dimension_delta={k_: round(v, 6) for k_, v in deltas.items()},
        collective_wins=sorted(wins),
        control_wins=sorted(losses),
        ties=sorted(ties),
        guardrail_flags=flags,
    )


def to_dict(result: Evaluation) -> dict:
    return asdict(result)
