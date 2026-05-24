# project_guardian/brain/execution_module.py

from __future__ import annotations

import logging
from typing import Any

from .contracts import (
    ExecutionModule,
    ExecutionResult,
    RiskAssessment,
    StructuredCommand,
    ToolRouteDecision,
)

logger = logging.getLogger(__name__)


class CapabilityExecutionFacade(ExecutionModule):
    """Runs structured commands via capability_execution; logs success and failure."""

    def execute(
        self,
        guardian: Any,
        command: StructuredCommand,
        *,
        risk: RiskAssessment,
        route: ToolRouteDecision,
    ) -> ExecutionResult:
        del risk  # already vetted by pipeline
        ref = (command.capability_ref or "").strip()
        if ref == "brain:noop" or ref.startswith("brain:"):
            logger.info("brain.execution success noop ref=%s route=%s", ref, route.selected)
            return ExecutionResult(True, {"note": "noop", "route": route.selected})

        if not guardian:
            logger.warning("brain.execution failure no_guardian ref=%s", ref)
            return ExecutionResult(False, {}, error="no_guardian")

        try:
            from ..capability_execution import execute_capability
        except Exception as e:
            logger.exception("brain.execution import failed: %s", e)
            return ExecutionResult(False, {}, error=f"import:{e}")

        try:
            out = execute_capability(guardian, ref, command.payload)
        except Exception as e:
            logger.exception("brain.execution exception ref=%s err=%s", ref, e)
            return ExecutionResult(False, {}, error=str(e))

        ok = bool(out.get("success")) if isinstance(out, dict) else False
        if ok:
            logger.info("brain.execution success ref=%s keys=%s", ref, list(out.keys()) if isinstance(out, dict) else type(out))
        else:
            logger.warning(
                "brain.execution failure ref=%s error=%s",
                ref,
                (out or {}).get("error") if isinstance(out, dict) else out,
            )
        err = None if ok else str((out or {}).get("error") or "execution_failed")
        return ExecutionResult(ok, dict(out) if isinstance(out, dict) else {"raw": out}, error=err)
