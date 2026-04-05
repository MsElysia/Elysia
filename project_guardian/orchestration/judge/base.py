# project_guardian/orchestration/judge/base.py
from __future__ import annotations

from typing import Protocol, List

from ..types import NodeResult, TaskRequest


class Judge(Protocol):
    async def compare(self, outputs: List[NodeResult], request: TaskRequest) -> NodeResult: ...
