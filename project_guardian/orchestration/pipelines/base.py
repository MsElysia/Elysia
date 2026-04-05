# project_guardian/orchestration/pipelines/base.py
from __future__ import annotations

from typing import Protocol

from ..types import PipelineResult, RouteDecision, TaskRequest


class Pipeline(Protocol):
    pipeline_id: str

    async def run(self, request: TaskRequest, route: RouteDecision) -> PipelineResult: ...
