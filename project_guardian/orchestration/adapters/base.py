# project_guardian/orchestration/adapters/base.py
from __future__ import annotations

from typing import Protocol


class LLMAdapter(Protocol):
    provider_name: str
    model_name: str

    async def generate(self, prompt: str, system: str | None = None, **kwargs: object) -> str: ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float: ...
