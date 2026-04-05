# project_guardian/orchestration/telemetry/
from __future__ import annotations

from typing import Any, Dict, Protocol

from .events import LLMCallEvent
from .sqlite_store import TelemetrySqliteStore, prompt_hash


class TelemetryStore(Protocol):
    async def log_call(self, event: LLMCallEvent) -> None: ...

    async def recent_route_health(self, task_type: str, model: str) -> Dict[str, Any]: ...
