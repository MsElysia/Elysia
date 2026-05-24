# project_guardian/brain/planner_module.py
# Produces structured plans only — never executes tools or capabilities.

from __future__ import annotations

import logging
import re
from typing import List

from .contracts import Observation, Plan, PlanStep, PlannerModule

logger = logging.getLogger(__name__)


class HeuristicPlannerModule(PlannerModule):
    """Small deterministic planner suitable for local / offline operation."""

    def plan(
        self,
        observation: Observation,
        memory_snippets: List[str],
        context_text: str,
    ) -> Plan:
        del memory_snippets, context_text  # reserved for richer planners
        text = observation.text.strip()
        goal = text[:500] or "(empty goal)"
        steps: List[PlanStep] = [
            PlanStep("Clarify objective and constraints", None, {}),
            PlanStep("Select capability or fallback", "task_router", {"hint": "route"}),
            PlanStep("Execute vetted step with logging", None, {"phase": "execute"}),
        ]
        router_task_type = "simple"
        if len(text) > 600 or re.search(r"\b(plan|architecture|strategy|prove)\b", text, re.I):
            router_task_type = "planning"
        if re.search(r"\b(code review|refactor|audit|security)\b", text, re.I):
            router_task_type = "reasoning"
        plan = Plan(goal_summary=goal, steps=steps, router_task_type=router_task_type)
        logger.info("brain.planner produced %d steps router_task_type=%s", len(steps), router_task_type)
        return plan
