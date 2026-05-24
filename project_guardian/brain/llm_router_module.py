# project_guardian/brain/llm_router_module.py
# Single stable entry: delegates routing to unified_llm_route + multi_api_router.

from __future__ import annotations

import logging
from typing import Any, Tuple

from .contracts import LLMRouterModule, RiskLevel

logger = logging.getLogger(__name__)


class UnifiedLLMRouterFacade(LLMRouterModule):
    """Uses decide_chat_llm_backend — no hardcoded provider strings for selection logic."""

    def choose_backend(
        self,
        *,
        user_text: str,
        router_task_type: str,
        risk_level: RiskLevel,
        registry: Any = None,
    ) -> Tuple[str, str]:
        from ..unified_llm_route import decide_chat_llm_backend

        task_type = router_task_type or "simple"
        if risk_level in (RiskLevel.HIGH, RiskLevel.BLOCKED):
            task_type = "reasoning"
        elif risk_level == RiskLevel.MEDIUM:
            if task_type == "simple":
                task_type = "reasoning"
        backend, reason = decide_chat_llm_backend(
            user_text,
            registry=registry,
            require_autonomy_safe=False,
            task_type=task_type,
        )
        logger.info("brain.llm_router backend=%s reason=%s task_type=%s risk=%s", backend, reason, task_type, risk_level.value)
        return backend, reason
