# project_guardian/brain/context_builder_module.py

from __future__ import annotations

import logging
from typing import Any, Optional

from .contracts import ContextBuilderModule, MemoryModule, Observation

logger = logging.getLogger(__name__)


class CreativityContextBuilderFacade:
    """Delegates to project_guardian.creativity.ContextBuilder when memory is MemoryCore-compatible."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def build(self, observation: Observation, memory: MemoryModule) -> str:
        del memory  # creativity builder bound at init in typical use
        try:
            parts = [
                f"[source={observation.source}]",
                observation.text.strip(),
            ]
            if self._inner and hasattr(self._inner, "build_recent_context"):
                parts.append(self._inner.build_recent_context(minutes=90))
            return "\n".join(p for p in parts if p)
        except Exception as e:
            logger.debug("brain.context_builder facade: %s", e)
            return observation.text.strip()


class MinimalContextBuilder:
    """No heavy imports: observation + optional memory keyword context."""

    def build(self, observation: Observation, memory: MemoryModule) -> str:
        try:
            snippets = memory.retrieve(observation.text[:400], limit=6)
        except Exception:
            snippets = []
        tail = "\n".join(f"- {s}" for s in snippets[-6:])
        base = f"{observation.source}: {observation.text.strip()}"
        return f"{base}\n{tail}" if tail else base


def default_context_builder(guardian: Optional[Any]) -> ContextBuilderModule:
    mem = getattr(guardian, "memory", None) if guardian else None
    if mem is not None:
        try:
            from ..creativity import ContextBuilder as _CB

            return CreativityContextBuilderFacade(_CB(mem))
        except Exception as e:
            logger.debug("brain.context_builder creativity import: %s", e)
    return MinimalContextBuilder()
