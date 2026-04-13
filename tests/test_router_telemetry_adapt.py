# tests/test_router_telemetry_adapt.py
import asyncio

from project_guardian.orchestration.router.rules import RulesRouter
from project_guardian.orchestration.telemetry.events import LLMCallEvent
from project_guardian.orchestration.telemetry.sqlite_store import TelemetrySqliteStore, prompt_hash
from project_guardian.orchestration.types import TaskRequest


def _ev(
    *,
    task_id: str,
    task_type: str = "reasoning",
    pipeline_id: str = "serial_plan_execute_review",
    node_id: str,
    provider: str = "ollama",
    model: str = "mistral",
    success: bool = True,
    action_intent_valid=None,
    fallback_mode=None,
) -> LLMCallEvent:
    return LLMCallEvent(
        task_id=task_id,
        task_type=task_type,
        pipeline_id=pipeline_id,
        node_id=node_id,
        provider=provider,
        model=model,
        prompt_hash=prompt_hash(task_id),
        latency_ms=12.0,
        input_tokens_est=10,
        output_tokens_est=10,
        cost_estimate_usd=0.0,
        outcome_score=None,
        review_verdict=None,
        success=success,
        action_intent_valid=action_intent_valid,
        fallback_mode=fallback_mode,
    )


def test_telemetry_empty_yields_yaml_default_local_first(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db = TelemetrySqliteStore(tmp_path / "t.db")
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
            },
            "routes": {"reasoning": {}},
        },
        telemetry_store=db,
    )

    async def _run():
        return await r.resolve(TaskRequest(task_id="a", task_type="reasoning", prompt="x"))

    d = asyncio.run(_run())
    assert d.pipeline_id == "serial_plan_execute_review"
    assert "telemetry:yaml_default_local_first" in d.reason


def test_healthy_serial_kept(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db = TelemetrySqliteStore(tmp_path / "t2.db")

    async def _seed():
        for i in range(6):
            await db.log_call(
                _ev(
                    task_id=f"h{i}",
                    node_id="plan",
                    success=True,
                )
            )
            await db.log_call(
                LLMCallEvent(
                    task_id=f"h{i}",
                    task_type="reasoning",
                    pipeline_id="serial_plan_execute_review",
                    node_id="execute",
                    provider="ollama",
                    model="mistral",
                    prompt_hash=prompt_hash(f"x{i}"),
                    latency_ms=10.0,
                    input_tokens_est=10,
                    output_tokens_est=10,
                    cost_estimate_usd=0.0,
                    outcome_score=None,
                    review_verdict=None,
                    success=True,
                )
            )

    asyncio.run(_seed())
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
            },
            "routes": {"reasoning": {}},
        },
        telemetry_store=db,
    )

    async def _run():
        return await r.resolve(TaskRequest(task_id="n", task_type="reasoning", prompt="y"))

    d = asyncio.run(_run())
    assert "telemetry:kept_serial_due_to_healthy_local_route" in d.reason


def test_invalid_intents_escalate_cloud_serial(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    db = TelemetrySqliteStore(tmp_path / "t3.db")

    async def _seed():
        for i in range(4):
            await db.log_call(
                _ev(
                    task_id=f"v{i}",
                    node_id="validate",
                    provider="deterministic",
                    model="action_intent_validator",
                    success=False,
                    action_intent_valid=False,
                    fallback_mode="legacy_capability_loop",
                )
            )
        for i in range(6):
            await db.log_call(_ev(task_id=f"p{i}", node_id="plan", success=True))

    asyncio.run(_seed())
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
            },
            "routes": {"reasoning": {}},
        },
        telemetry_store=db,
    )

    async def _run():
        return await r.resolve(TaskRequest(task_id="z", task_type="reasoning", prompt="z"))

    d = asyncio.run(_run())
    assert d.pipeline_id == "serial_plan_execute_review"
    assert "openai" in (d.executor_model or "")
    assert "telemetry:escalated_cloud_due_to_invalid_intents" in d.reason


def test_repeated_failures_escalate_parallel(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    db = TelemetrySqliteStore(tmp_path / "t4.db")

    async def _seed():
        for i in range(10):
            await db.log_call(_ev(task_id=f"f{i}", node_id="plan", success=(i % 9 == 0)))

    asyncio.run(_seed())
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
            },
            "routes": {"reasoning": {}},
        },
        telemetry_store=db,
    )

    async def _run():
        return await r.resolve(TaskRequest(task_id="p", task_type="reasoning", prompt="p"))

    d = asyncio.run(_run())
    assert d.pipeline_id == "parallel_compare_and_judge"
    assert len(d.fanout_models) == 2
    assert "telemetry:escalated_parallel_due_to_repeated_local_failures" in d.reason


def test_parallel_revert_when_no_gain(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    db = TelemetrySqliteStore(tmp_path / "t5.db")

    async def _seed():
        for i in range(8):
            await db.log_call(
                _ev(
                    task_id=f"pa{i}",
                    task_type="reasoning",
                    pipeline_id="parallel_compare_and_judge",
                    node_id="fanout_a",
                    success=False,
                )
            )
            await db.log_call(
                _ev(
                    task_id=f"pa{i}",
                    task_type="reasoning",
                    pipeline_id="parallel_compare_and_judge",
                    node_id="fanout_b",
                    success=False,
                )
            )
        for i in range(8):
            await db.log_call(_ev(task_id=f"sb{i}", node_id="plan", success=True))
            await db.log_call(_ev(task_id=f"sb{i}", node_id="execute", success=True))

    asyncio.run(_seed())
    r = RulesRouter(
        {
            "orchestration": {"enabled": True},
            "defaults": {
                "pipeline": "parallel_compare_and_judge",
                "planner_model": "ollama:mistral",
                "executor_model": "ollama:mistral",
                "fanout_models": ["ollama:mistral", "openai:gpt-4.1-mini"],
            },
            "routes": {"reasoning": {}},
        },
        telemetry_store=db,
    )

    async def _run():
        return await r.resolve(TaskRequest(task_id="r", task_type="reasoning", prompt="r"))

    d = asyncio.run(_run())
    assert d.pipeline_id == "serial_plan_execute_review"
    assert "telemetry:reverted_from_parallel_due_to_no_quality_gain" in d.reason
