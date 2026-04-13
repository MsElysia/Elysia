# tests/test_router_rules.py
import asyncio

import pytest

from project_guardian.orchestration.router.rules import RulesRouter
from project_guardian.orchestration.types import TaskRequest


def test_reasoning_defaults_serial(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
                "reviewer_model": "openai:gpt-4.1-mini",
            },
            "routes": {},
        }
    )

    async def _run():
        return await r.resolve(TaskRequest(task_id="t1", task_type="reasoning", prompt="x"))

    d = asyncio.run(_run())
    assert d.pipeline_id == "serial_plan_execute_review"


def test_critique_parallel(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {"pipeline": "serial_plan_execute_review", "planner_model": "ollama:mistral"},
            "routes": {
                "critique": {
                    "pipeline": "parallel_compare_and_judge",
                    "fanout_models": ["ollama:mistral", "ollama:mistral"],
                }
            },
        }
    )

    async def _run():
        return await r.resolve(TaskRequest(task_id="t2", task_type="critique", prompt="y"))

    d = asyncio.run(_run())
    assert d.pipeline_id == "parallel_compare_and_judge"
    assert len(d.fanout_models) == 2


def test_governance_escalate_parallel(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
            },
            "routes": {"reasoning": {}},
        }
    )
    req = TaskRequest(
        task_id="t3",
        task_type="reasoning",
        prompt="z",
        metadata={"governance_hints": ["escalate_reasoning"]},
    )

    async def _run():
        return await r.resolve(req)

    d = asyncio.run(_run())
    assert d.pipeline_id == "parallel_compare_and_judge"


def test_governance_cloud_executor_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
            },
            "routes": {"reasoning": {}},
        }
    )
    req = TaskRequest(
        task_id="t4",
        task_type="reasoning",
        prompt="z",
        metadata={"governance_hints": ["low_confidence_local"]},
    )

    async def _run():
        return await r.resolve(req)

    d = asyncio.run(_run())
    assert "openai" in (d.executor_model or "")
