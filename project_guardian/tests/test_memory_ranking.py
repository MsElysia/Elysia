from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from project_guardian.brain.contracts import Observation
from project_guardian.brain.memory_module import InMemoryBrainStore
from project_guardian.brain.pipeline import BrainPipeline
from project_guardian.memory_ranking import (
    MemoryRankingInput,
    RankedMemory,
    clear_memory_ranking_config_cache,
    get_memory_ranking_config,
    load_memory_ranking_config,
    memory_dict_to_input,
    optional_remember_extras_for_pipeline,
    propose_compression_from_dicts,
    propose_memory_compression,
    rank_memories,
    redact_memory_text,
    review_memory_scores_with_llm,
    score_memory,
    summarize_memory_for_compression,
)


NOW = "2026-05-14T12:00:00+00:00"


class StaticLLMRouter:
    def choose_backend(self, *, user_text, router_task_type, risk_level, registry=None):
        return "fake-local", "offline"


class NoopSelfImprovement:
    def enqueue(self, outcome, trace):
        return None


def test_missing_fields_use_safe_defaults():
    cfg = get_memory_ranking_config()
    scores, val = score_memory(MemoryRankingInput(), cfg)
    assert 0.0 <= val <= 1.0
    assert 0.0 <= scores.relevance_score <= 1.0


def test_recent_important_memory_ranks_higher_than_old_low_use():
    cfg = get_memory_ranking_config()
    important = MemoryRankingInput(
        memory_id="important",
        text="User prefers Project Guardian status updates in concise bullets.",
        last_used_at="2026-05-14T11:00:00+00:00",
        access_count=12,
        user_marked_important=True,
        linked_goal="guardian",
    )
    old = MemoryRankingInput(
        memory_id="old",
        text="Routine heartbeat ping with no changes.",
        last_used_at="2024-01-01T00:00:00+00:00",
        access_count=0,
    )
    ranked = rank_memories([old, important], cfg, now=datetime.fromisoformat(NOW.replace("Z", "+00:00")))
    assert ranked[0].memory_id == "important"
    assert ranked[0].memory_value_score > ranked[-1].memory_value_score


def test_failure_prevention_memory_gets_boosted():
    cfg = get_memory_ranking_config()
    text = "General note about the UI color."
    s_fail, _ = score_memory(
        MemoryRankingInput(text=text, failure_related=True, category="error"),
        cfg,
    )
    s_neutral, _ = score_memory(MemoryRankingInput(text=text), cfg)
    assert s_fail.failure_prevention_score > s_neutral.failure_prevention_score


def test_low_value_long_memory_gets_compression_proposal():
    cfg = get_memory_ranking_config()
    mem = MemoryRankingInput(
        memory_id="long-low",
        text=("Routine heartbeat status unchanged. " * 40).strip(),
        last_used_at="2024-01-01T00:00:00+00:00",
        access_count=0,
        confidence=0.2,
    )
    ranked = rank_memories([mem], cfg)
    props = propose_memory_compression(ranked, cfg)
    assert props[0].action == "compress"
    assert props[0].dry_run is True


def test_high_value_memory_keeps_full_detail():
    cfg = get_memory_ranking_config()
    mem = MemoryRankingInput(
        memory_id="high",
        text="Important decision: keep operator chat BrainPipeline traces dry-run only.",
        user_marked_important=True,
        access_count=20,
        last_used_at="2026-05-14T11:00:00+00:00",
    )
    ranked = rank_memories([mem], cfg)
    props = propose_memory_compression(ranked, cfg)
    assert props[0].action == "keep_full"


def test_compression_summary_preserves_key_entities_dates_preferences():
    memory = {
        "thought": (
            "On 2026-05-14, Maya Chen decided Project Guardian should keep operator chat dry-run. "
            "User prefers concise implementation reports. "
            "The failure cause was a missing risk validation handoff."
        )
    }
    summary = summarize_memory_for_compression(memory, max_chars=500)
    assert "Maya Chen" in summary
    assert "2026-05-14" in summary
    assert "prefers concise implementation reports" in summary
    assert "decided" in summary
    assert "failure cause" in summary


def test_secrets_redacted_in_summary_and_redact_memory_text():
    raw = (
        "api_key=abc123 token=tok123 password=hunter2 Authorization: Bearer secretbearer "
        "sk-live123456789 should never be retained."
    )
    summary = summarize_memory_for_compression(raw)
    redacted = redact_memory_text(raw)
    assert "[REDACTED]" in summary or "REDACT" in summary
    assert "[REDACTED]" in redacted or "REDACT" in redacted
    for secret in ("abc123", "tok123", "hunter2", "secretbearer", "sk-live123456789"):
        assert secret not in summary
        assert secret not in redacted


def test_dry_run_does_not_mutate_memory_store():
    cfg = get_memory_ranking_config()
    memory = {"id": "m1", "thought": "Routine heartbeat status unchanged. " * 30, "metadata": {"nested": ["x"]}}
    original = deepcopy(memory)
    report = propose_compression_from_dicts([memory], cfg=cfg, context={"now": NOW})
    assert memory == original
    assert all(p.dry_run for p in report.proposals)


def test_delete_never_proposed():
    cfg = get_memory_ranking_config()
    memories = [
        {"id": "m1", "thought": "Routine heartbeat status unchanged. " * 30, "priority": 0.0},
        {"id": "m2", "thought": "Important decision: keep this.", "priority": 0.9},
    ]
    report = propose_compression_from_dicts(memories, cfg=cfg, context={"now": NOW})
    assert all(p.action != "delete" for p in report.proposals)


def test_config_defaults_are_safe():
    cfg = load_memory_ranking_config()
    assert cfg["enabled"] is False
    assert cfg["dry_run"] is True
    assert cfg.get("deletion_enabled", False) is False


def test_fake_llm_reviewer_cannot_bypass_commitment_review():
    cfg = get_memory_ranking_config()

    def reviewer(ranked: list[RankedMemory]) -> list[RankedMemory]:
        return [
            RankedMemory(
                memory_id=r.memory_id,
                text=r.text,
                scores=r.scores,
                memory_value_score=min(1.0, r.memory_value_score + 0.5),
            )
            for r in ranked
        ]

    mem = MemoryRankingInput(
        memory_id="c1",
        text="Commitment: send Maya the report by 2026-05-20.",
        last_used_at="2020-01-01T00:00:00+00:00",
        access_count=0,
    )
    items = [mem]
    ranked = rank_memories(items, cfg)
    ranked2 = review_memory_scores_with_llm(ranked, reviewer=reviewer)
    props = propose_memory_compression(ranked2, cfg)
    assert props[0].action == "review_manually"


def test_brain_pipeline_remember_attaches_ranking_when_rank_memory_in_context():
    clear_memory_ranking_config_cache()
    mem = InMemoryBrainStore()
    pipe = BrainPipeline(
        guardian=None,
        memory=mem,
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )
    trace, _ = pipe.run(
        Observation("user", "noop probe"),
        context={"rank_memory": True, "use_think_decide_act": False, "dry_run": True},
    )
    assert "planner_finished" in trace.transitions
    entry = mem.entries[-1]
    assert "memory_ranking" in entry
    assert "value_score" in entry["memory_ranking"]


def test_brain_pipeline_ranking_failure_does_not_break_pipeline(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("ranking failed")

    monkeypatch.setattr("project_guardian.memory_ranking.rank_memories_from_snippets", boom)
    memory = InMemoryBrainStore()
    memory.remember("safe request memory", category="test")
    pipe = BrainPipeline(
        guardian=None,
        memory=memory,
        llm_router=StaticLLMRouter(),
        self_improvement=NoopSelfImprovement(),
    )

    trace, _ = pipe.run(
        Observation("user", "safe request"),
        context={"rank_memory": True, "use_think_decide_act": False, "dry_run": True},
    )

    assert "planner_finished" in trace.transitions
    assert trace.run_context["memory_ranking"]["error"] == "ranking failed"


def test_optional_remember_extras_never_raises():
    assert optional_remember_extras_for_pipeline("x", None) == {}
    assert optional_remember_extras_for_pipeline("x", {"rank_memory": False}) == {}


def test_memory_dict_to_input_maps_rows():
    d = memory_dict_to_input(
        {
            "id": "a",
            "thought": "hello",
            "time": NOW,
            "access_count": 3,
            "category": "note",
        },
        0,
    )
    assert d.memory_id == "a"
    assert d.text == "hello"
