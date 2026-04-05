# project_guardian/orchestration/judge/model_judge.py
from __future__ import annotations

import json
import time
from typing import Any, List

from ..adapters.base import LLMAdapter
from ..types import NodeResult, TaskRequest
from ...prompts.prompt_builder import build_prompt


class ModelJudge:
    """Optional LLM judge when deterministic compare is inconclusive."""

    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    async def compare(self, outputs: List[NodeResult], request: TaskRequest) -> NodeResult:
        if not outputs:
            return NodeResult(
                node_id="model_judge",
                provider=self._adapter.provider_name,
                model=self._adapter.model_name,
                output="",
                success=False,
                latency_ms=0.0,
                error="no_outputs",
            )
        parts = []
        for i, nr in enumerate(outputs):
            parts.append(f"--- candidate_{i} ({nr.provider}:{nr.model}) ---\n{nr.output}\n")
        prompt = (
            "Select the best candidate for the task. Return ONLY compact JSON: "
            '{"chosen_index": <int 0-based>, "reason": "<short>"}\n'
            + "\n".join(parts)
        )
        t0 = time.perf_counter()
        gen_kw: dict = {"temperature": 0.1}
        if getattr(self._adapter, "provider_name", "") == "openai":
            gen_kw["response_format_json"] = True
        _judge_sys = build_prompt(
            "router",
            "critic",
            task_text="Judge which candidate best satisfies the task; output JSON only.",
            output_schema={"type": "judge_choice", "fields": ["chosen_index", "reason"]},
        )
        raw = await self._adapter.generate(
            prompt,
            system=_judge_sys,
            **gen_kw,
        )
        lat = (time.perf_counter() - t0) * 1000
        try:
            obj = json.loads(raw)
            idx = int(obj.get("chosen_index", 0))
        except Exception:
            idx = 0
        idx = max(0, min(len(outputs) - 1, idx))
        picked = outputs[idx]
        return NodeResult(
            node_id="model_judge",
            provider=self._adapter.provider_name,
            model=self._adapter.model_name,
            output=picked.output,
            success=True,
            latency_ms=lat,
            review_verdict="model_selected",
            outcome_score=0.75,
        )
