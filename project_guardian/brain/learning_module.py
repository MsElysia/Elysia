# project_guardian/brain/learning_module.py

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .contracts import ExecutionResult, LearningModule, LearningOutcome, MemoryModule, Observation, Plan

logger = logging.getLogger(__name__)


class DefaultLearningModule(LearningModule):
    def __init__(self) -> None:
        self._pipeline_context: Optional[Dict[str, Any]] = None

    def bind_pipeline_context(self, ctx: Optional[Dict[str, Any]]) -> None:
        self._pipeline_context = ctx

    def review_outcome(
        self,
        observation: Observation,
        plan: Plan,
        execution: ExecutionResult,
        memory: MemoryModule,
    ) -> LearningOutcome:
        worked = bool(execution.success)
        lesson = (
            f"brain.lesson ok={worked} goal={plan.goal_summary[:120]!r} "
            f"source={observation.source} err={execution.error or ''}"
        )
        hints: List[str] = []
        if not worked:
            hints.append("retry_with_fallback_route")
        extras: Dict[str, Any] = {}
        try:
            from project_guardian.memory_ranking import optional_remember_extras_for_pipeline

            extras = optional_remember_extras_for_pipeline(lesson, self._pipeline_context)
        except Exception as e:
            logger.debug("brain.learning ranking extras skipped: %s", e)
        try:
            memory.remember(lesson, category="brain_lesson", priority=0.55, **extras)
        except Exception as e:
            logger.warning("brain.learning memory.remember failed: %s", e)
        logger.info("brain.learning lesson_stored worked=%s", worked)
        return LearningOutcome(worked=worked, lesson=lesson, improvement_hints=hints)
