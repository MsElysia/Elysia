# tests/test_orchestration_parallel.py
import asyncio
import json
from typing import Any, Optional

import pytest

from project_guardian.orchestration.pipelines.parallel import ParallelCompareAndJudgePipeline
from project_guardian.orchestration.telemetry.sqlite_store import TelemetrySqliteStore
from project_guardian.orchestration.types import RouteDecision, TaskRequest


class _FakeLLM:
    def __init__(self, provider: str, model: str, text: str) -> None:
        self.provider_name = provider
        self.model_name = model
        self._text = text

    async def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> str:
        return self._text

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.01


def test_parallel_pipeline_two_branches(tmp_path):
    db = TelemetrySqliteStore(tmp_path / "p.db")

    async def log_ev(ev: Any) -> None:
        await db.log_call(ev)

    adapters = {
        "a": _FakeLLM("ollama", "mistral", '{"chosen_action":"x","reasoning":"short","confidence":0.5}'),
        "b": _FakeLLM("openai", "gpt", '{"chosen_action":"y","reasoning":"longer better text","confidence":0.9}'),
    }

    def get_adapter(ref: str) -> Any:
        if ref.startswith("ollama"):
            return adapters["a"]
        return adapters["b"]

    pipe = ParallelCompareAndJudgePipeline(get_adapter, log_ev)
    route = RouteDecision(
        pipeline_id="parallel_compare_and_judge",
        fanout_models=["ollama:mistral", "openai:gpt-4.1-mini"],
        judge_model=None,
        reason="test",
    )

    async def _run():
        return await pipe.run(
            TaskRequest(task_id="p1", task_type="critique", prompt="compare outputs"),
            route,
        )

    pr = asyncio.run(_run())
    assert pr.pipeline_id == "parallel_compare_and_judge"
    assert pr.success
    out = pr.final_output
    if isinstance(out, str):
        out = json.loads(out)
    assert "chosen_action" in out
