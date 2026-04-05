# project_guardian/orchestration/
"""Minimal multi-LLM orchestration (YAML router, serial/parallel pipelines, SQLite telemetry)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import NodeResult, PipelineResult, RouteDecision, TaskRequest

__all__ = [
    "OrchestrationBroker",
    "get_orchestration_broker",
    "TaskRequest",
    "RouteDecision",
    "NodeResult",
    "PipelineResult",
]


def get_orchestration_broker():
    from .broker import get_orchestration_broker as _impl

    return _impl()


def __getattr__(name: str):
    if name == "OrchestrationBroker":
        from .broker import OrchestrationBroker as _OB

        return _OB
    raise AttributeError(name)


if TYPE_CHECKING:
    from .broker import OrchestrationBroker  # noqa: F401
