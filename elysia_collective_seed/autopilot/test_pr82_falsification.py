from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import types


def _load_module(monkeypatch, name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _load_router_and_policy(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    orch = root / "project_guardian" / "orchestration"
    pkg = "_pr82_falsify"

    for name in (
        pkg,
        f"{pkg}.orchestration",
        f"{pkg}.orchestration.router",
        f"{pkg}.orchestration.telemetry",
    ):
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, module)

    ollama = types.ModuleType(f"{pkg}.ollama_model_config")
    ollama.ollama_provider_ref = lambda: "ollama:mistral:7b"
    monkeypatch.setitem(sys.modules, ollama.__name__, ollama)

    telemetry_mod = types.ModuleType(f"{pkg}.orchestration.telemetry.sqlite_store")
    telemetry_mod.TelemetrySqliteStore = object
    monkeypatch.setitem(sys.modules, telemetry_mod.__name__, telemetry_mod)

    health_mod = types.ModuleType(f"{pkg}.orchestration.router.health")

    @dataclass
    class FakeHealth:
        recent_calls: int = 10
        success_rate: float = 0.45
        avg_outcome_score: float | None = 0.45
        intent_validation_samples: int = 0
        invalid_intent_rate: float = 0.0
        fallback_labeled_samples: int = 0
        legacy_fallback_rate: float = 0.0
        review_action_samples: int = 0
        review_fail_rate: float = 0.0

    async def summarize_route_health(*args, **kwargs):
        return FakeHealth()

    health_mod.RouteHealthSummary = FakeHealth
    health_mod.summarize_route_health = summarize_route_health
    monkeypatch.setitem(sys.modules, health_mod.__name__, health_mod)

    _load_module(
        monkeypatch,
        f"{pkg}.orchestration.types",
        orch / "types.py",
    )
    _load_module(
        monkeypatch,
        f"{pkg}.orchestration.router.task_types",
        orch / "router" / "task_types.py",
    )
    rules = _load_module(
        monkeypatch,
        f"{pkg}.orchestration.router.rules",
        orch / "router" / "rules.py",
    )
    policy = _load_module(
        monkeypatch,
        f"{pkg}.orchestration.router.policy",
        orch / "router" / "policy.py",
    )
    return rules, policy, sys.modules[f"{pkg}.orchestration.types"]


class FakeTelemetry:
    async def aggregate_route_metrics(self, *, pipeline_id, **kwargs):
        if pipeline_id == "serial_plan_execute_review":
            return {"llm_total": 10, "llm_ok": 4}
        return {"fanout_total": 0, "fanout_ok": 0}


def test_pr82_local_only_survives_telemetry_adaptation(monkeypatch):
    rules, policy, types_mod = _load_router_and_policy(monkeypatch)
    monkeypatch.setattr(rules, "_openai_available", lambda: True)
    monkeypatch.setattr(policy, "_openai_available", lambda: True)

    raw = {
        "orchestration": {"enabled": True},
        "defaults": {
            "pipeline": "serial_plan_execute_review",
            "planner_model": "ollama:mistral:7b",
            "executor_model": "ollama:mistral:7b",
            "reviewer_model": None,
        },
        "routes": {
            "reasoning": {
                "pipeline": "serial_plan_execute_review",
                "planner_model": "ollama:mistral:7b",
                "executor_model": "ollama:mistral:7b",
                "reviewer_model": None,
            }
        },
    }

    request = types_mod.TaskRequest(
        task_id="ELY-TASK-990001",
        task_type="reasoning",
        prompt="diagnose synthetic pytest log",
        metadata={"local_only": True},
    )
    route = asyncio.run(
        rules.RulesRouter(raw, telemetry_store=FakeTelemetry()).resolve(request)
    )

    refs = [
        route.planner_model,
        route.executor_model,
        route.reviewer_model,
        route.judge_model,
        *route.fanout_models,
    ]
    assert all(ref is None or ref.startswith("ollama:") for ref in refs), (
        "PR #82 local_only was overridden after the initial router decision: "
        f"{route}"
    )
