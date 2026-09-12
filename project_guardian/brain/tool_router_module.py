# project_guardian/brain/tool_router_module.py

from __future__ import annotations

import logging
from typing import Any

from .contracts import Observation, Plan, ToolRouteDecision, ToolRouterModule

logger = logging.getLogger(__name__)

_FALLBACK = "module:longterm_planner"
_INTERNAL_NOOP = "brain:noop"


class DefaultToolRouterModule(ToolRouterModule):
    """
    Picks a capability string for execution. Pure decision logic — does not call tools.
    Falls back when registry / task_router is missing or primary target is unavailable.
    """

    def route(
        self,
        observation: Observation,
        plan: Plan,
        *,
        guardian: Any,
    ) -> ToolRouteDecision:
        primary = self._primary_from_plan(plan)
        if self._capability_usable(guardian, primary):
            decision = ToolRouteDecision(
                primary=primary,
                selected=primary,
                used_fallback=False,
                reason="primary_available",
            )
            logger.info("brain.tool_router selected=%s fallback=%s", decision.selected, decision.used_fallback)
            return decision

        fb = _FALLBACK if self._capability_usable(guardian, _FALLBACK) else _INTERNAL_NOOP
        decision = ToolRouteDecision(
            primary=primary,
            selected=fb,
            used_fallback=True,
            reason="primary_unavailable_used_fallback",
            extras={"observation_source": observation.source},
        )
        logger.info(
            "brain.tool_router selected=%s used_fallback=%s primary=%s",
            decision.selected,
            decision.used_fallback,
            primary,
        )
        return decision

    def _primary_from_plan(self, plan: Plan) -> str:
        for step in plan.steps:
            hint = (step.capability_hint or "").strip()
            if hint:
                if hint == "task_router":
                    return "module:task_router"
                if ":" in hint:
                    return hint
                return f"tool:{hint}"
        return "module:task_router"

    def _capability_usable(self, guardian: Any, ref: str) -> bool:
        if not guardian:
            return ref == _INTERNAL_NOOP
        if ref == _INTERNAL_NOOP:
            return True
        mods = getattr(guardian, "_modules", None) or {}
        if ref.startswith("module:"):
            name = ref.split(":", 1)[1]
            mod = mods.get(name)
            if mod is None:
                return False
            if name == "task_router":
                return callable(getattr(mod, "route_task", None))
            return True
        if ref.startswith("tool:"):
            name = ref.split(":", 1)[1]
            tr = mods.get("tool_registry")
            if tr is None:
                return False
            tools = getattr(tr, "list_tools", None) or getattr(tr, "tools", None)
            if callable(tools):
                try:
                    listed = tools()  # type: ignore[misc]
                except Exception:
                    listed = None
                if isinstance(listed, (list, tuple, set)):
                    return name in {str(x) for x in listed}
            if hasattr(tr, "has_tool"):
                try:
                    return bool(tr.has_tool(name))  # type: ignore[misc]
                except Exception:
                    return False
            return False
        return ref in mods
