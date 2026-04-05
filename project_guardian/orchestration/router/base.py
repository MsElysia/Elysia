# project_guardian/orchestration/router/base.py
from __future__ import annotations

from typing import Protocol

from ..types import RouteDecision, TaskRequest


class Router(Protocol):
    async def resolve(self, request: TaskRequest) -> RouteDecision: ...
