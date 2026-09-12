from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

from project_guardian.brain.contracts import Observation
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.memory_ranking import clear_memory_ranking_config_cache


class StaticLLMRouter:
    def choose_backend(self, *, user_text, router_task_type, risk_level, registry=None):
        return "fake-local", "offline"


class NoopSelfImprovement:
    def enqueue(self, outcome, trace):
        return None


def test_canonical_import_works():
    from project_guardian.memory_ranking import MemoryRankingInput, score_memory

    assert MemoryRankingInput.__name__ == "MemoryRankingInput"
    assert callable(score_memory)


def test_brain_shim_import_works():
    from project_guardian.brain.memory_ranking import MemoryRankingInput, score_memory

    assert MemoryRankingInput.__name__ == "MemoryRankingInput"
    assert callable(score_memory)


def test_canonical_and_brain_shim_identity_is_the_same():
    canonical = importlib.import_module("project_guardian.memory_ranking")
    shim = importlib.import_module("project_guardian.brain.memory_ranking")

    assert canonical.MemoryRankingInput is shim.MemoryRankingInput
    assert canonical.MemoryRankingConfig is shim.MemoryRankingConfig
    assert canonical.score_memory is shim.score_memory
    assert canonical.rank_memories is shim.rank_memories
    assert canonical.clear_memory_ranking_config_cache is shim.clear_memory_ranking_config_cache


def test_project_guardian_memory_module_is_not_shadowed(tmp_path):
    spec = importlib.util.find_spec("project_guardian.memory")
    assert spec is not None
    assert spec.origin is not None
    assert Path(spec.origin).name == "memory.py"
    assert spec.submodule_search_locations is None

    memory_module = importlib.import_module("project_guardian.memory")
    assert Path(memory_module.__file__).name == "memory.py"
    assert hasattr(memory_module, "MemoryCore")

    mem = memory_module.MemoryCore(filepath=str(tmp_path / "memory.json"), lazy_load=True)
    assert mem.get_memory_state(load_if_needed=False)["memory_loaded"] is False


def test_brain_pipeline_ranking_uses_canonical_import_without_duplicate_state(monkeypatch):
    canonical = importlib.import_module("project_guardian.memory_ranking")
    shim = importlib.import_module("project_guardian.brain.memory_ranking")
    assert canonical.rank_memories_from_snippets is shim.rank_memories_from_snippets

    calls = []

    def fake_rank(snippets, cfg, *, current_goal_text=""):
        calls.append(
            {
                "snippets": list(snippets),
                "cfg_type": type(cfg).__name__,
                "current_goal_text": current_goal_text,
            }
        )
        return []

    monkeypatch.setattr(canonical, "rank_memories_from_snippets", fake_rank)

    memory = InMemoryBrainStore()
    memory.remember("canonical ranking probe", category="test")
    pipe = BrainPipeline(
        guardian=None,
        memory=memory,
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )

    trace, _ = pipe.run(
        Observation("user", "canonical ranking probe"),
        context={
            "rank_memory": True,
            "use_think_decide_act": False,
            "dry_run": True,
            "persist_trace": False,
        },
    )

    assert calls == [
        {
            "snippets": ["canonical ranking probe"],
            "cfg_type": "MemoryRankingConfig",
            "current_goal_text": "canonical ranking probe",
        }
    ]
    assert trace.run_context["memory_ranking"] == {
        "enabled": True,
        "count": 0,
        "top_ids": [],
        "top_scores": [],
    }


def test_config_cache_clear_works_through_canonical_import(tmp_path):
    from project_guardian.memory_ranking import (
        clear_memory_ranking_config_cache,
        get_memory_ranking_config,
    )

    config_path = tmp_path / "memory_ranking.json"
    config_path.write_text(json.dumps({"memory_ranking": {"enabled": True}}), encoding="utf-8")

    try:
        clear_memory_ranking_config_cache()
        assert get_memory_ranking_config(_path_str=str(config_path)).enabled is True

        config_path.write_text(json.dumps({"memory_ranking": {"enabled": False}}), encoding="utf-8")
        assert get_memory_ranking_config(_path_str=str(config_path)).enabled is True

        clear_memory_ranking_config_cache()
        assert get_memory_ranking_config(_path_str=str(config_path)).enabled is False
    finally:
        clear_memory_ranking_config_cache()


def test_memory_ranking_diagnostic_imports_canonical_module_without_crashing():
    canonical = importlib.import_module("project_guardian.memory_ranking")
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "memory_ranking_diagnostic.py"
    spec = importlib.util.spec_from_file_location("memory_ranking_diagnostic_under_test", script_path)

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.get_memory_ranking_config is canonical.get_memory_ranking_config
    assert module.rank_memories_from_snippets is canonical.rank_memories_from_snippets


def teardown_module():
    clear_memory_ranking_config_cache()
