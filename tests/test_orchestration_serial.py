# tests/test_orchestration_serial.py
import asyncio
import json
from typing import Any, Optional

import pytest

from project_guardian.orchestration.broker import OrchestrationBroker
from project_guardian.orchestration.pipelines.serial import SerialPlanExecuteReviewPipeline
from project_guardian.orchestration.router.rules import RulesRouter
from project_guardian.orchestration.telemetry.sqlite_store import TelemetrySqliteStore
from project_guardian.orchestration.types import TaskRequest


class _FakeLLM:
    def __init__(self, provider: str, model: str, replies: list) -> None:
        self.provider_name = provider
        self.model_name = model
        self._replies = list(replies)
        self._i = 0

    async def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> str:
        if self._i >= len(self._replies):
            return ""
        out = self._replies[self._i]
        self._i += 1
        return out

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0


def test_serial_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db = TelemetrySqliteStore(tmp_path / "tel.db")
    calls: list = []

    async def log_ev(ev: Any) -> None:
        calls.append(ev)
        await db.log_call(ev)

    combined = _FakeLLM(
        "ollama",
        "mistral",
        [
            "- step one\n- step two",
            json.dumps({"chosen_action": "a", "reasoning": "r", "confidence": 0.8}),
        ],
    )

    def get_adapter(ref: str) -> Any:
        return combined

    pipe = SerialPlanExecuteReviewPipeline(get_adapter, log_ev)

    async def _run():
        route = await RulesRouter(
            {
                "orchestration": {"enabled": True},
                "defaults": {
                    "pipeline": "serial_plan_execute_review",
                    "planner_model": "ollama:mistral",
                    "executor_model": "ollama:mistral",
                    "reviewer_model": None,
                },
                "routes": {},
            }
        ).resolve(TaskRequest(task_id="x", task_type="reasoning", prompt="hello"))
        req = TaskRequest(
            task_id="x",
            task_type="reasoning",
            prompt="Pick action from list",
            metadata={"ollama_json_schema": {"type": "object"}},
        )
        return await pipe.run(req, route)

    pr = asyncio.run(_run())
    assert pr.success
    assert isinstance(pr.final_output, dict)
    assert pr.final_output.get("chosen_action") == "a"
    assert len(pr.node_results) >= 3
    assert len(calls) >= 2


def test_broker_run_task_minimal(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class _MiniBroker(OrchestrationBroker):
        def __init__(self) -> None:
            self.telemetry = TelemetrySqliteStore(tmp_path / "t2.db")
            self.router = RulesRouter(
                {
                    "orchestration": {"enabled": True},
                    "defaults": {
                        "pipeline": "serial_plan_execute_review",
                        "planner_model": "ollama:mistral",
                        "executor_model": "ollama:mistral",
                    },
                    "routes": {},
                }
            )
            self._ollama_base = None
            self._adapter_cache = {}
            self._serial = SerialPlanExecuteReviewPipeline(self.get_adapter, self._log_event)
            from project_guardian.orchestration.pipelines.parallel import ParallelCompareAndJudgePipeline

            self._parallel = ParallelCompareAndJudgePipeline(self.get_adapter, self._log_event)

        def get_adapter(self, model_ref: str) -> Any:
            key = "shared"
            if key not in self._adapter_cache:
                self._adapter_cache[key] = _FakeLLM(
                    "ollama",
                    "mistral",
                    [
                        "- plan bullet",
                        json.dumps({"chosen_action": "c", "reasoning": "ok", "confidence": 0.6}),
                    ],
                )
            return self._adapter_cache[key]

    b = _MiniBroker()

    async def _run():
        return await b.run_task(TaskRequest(task_id="z", task_type="summarization", prompt="sum"))

    pr = asyncio.run(_run())
    assert pr.pipeline_id == "serial_plan_execute_review"
    assert pr.success
