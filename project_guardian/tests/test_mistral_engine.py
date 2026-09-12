# project_guardian/tests/test_mistral_engine.py
# Test Mistral decision engine (requires Ollama running with mistral model)

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.mistral_engine import (
    _clean_learning_history_values,
    _compact_learning_context,
)


@pytest.mark.skip(reason="Requires Ollama running with mistral model - run manually when available")
def test_mistral_decide():
    """Test MistralEngine.decide returns valid JSON structure."""
    from project_guardian.mistral_engine import MistralEngine

    engine = MistralEngine()
    result = engine.decide(
        goal="Fix failing system loop",
        state={"failures": 3},
        tools=[
            {"name": "run_diagnostic"},
            {"name": "create_task"},
            {"name": "ask_user"},
        ],
        module_name="router",
    )
    assert "decision" in result
    assert "actions" in result
    assert isinstance(result["actions"], list)
    for a in result["actions"]:
        assert "tool" in a
        assert "args" in a
    # Tool should be from allowed set
    allowed = {"run_diagnostic", "create_task", "ask_user"}
    for a in result["actions"]:
        assert a["tool"] in allowed, f"Tool {a['tool']} not in allowed set"


@pytest.mark.skip(reason="Requires Ollama - run manually when available")
def test_mistral_decide_next_action():
    """Test MistralEngine.decide_next_action returns structured routing decision."""
    from project_guardian.mistral_engine import MistralEngine

    engine = MistralEngine(model="mistral:7b")
    state = {
        "candidates": [
            {"action": "consider_learning", "source": "introspection", "reason": "Learn", "priority_score": 5},
            {"action": "consider_prompt_evolution", "source": "evolver", "reason": "Evolve", "priority_score": 4},
        ],
        "active_goal": None,
        "recent_actions": [],
        "memory_pressure_high": False,
        "stagnation_count": 0,
    }
    result = engine.decide_next_action(state, module_name="planner", agent_name="orchestrator")
    assert "chosen_action" in result
    assert "reasoning" in result
    assert "confidence" in result
    assert result["chosen_action"] in {"consider_learning", "consider_prompt_evolution", "continue_monitoring"}
    assert 0 <= result["confidence"] <= 1


def test_compact_learning_context_preserves_recent_round_history():
    head = "ChatGPT exports (snippets for planning):\n" + ("Elysia mission context. " * 260)
    tail = "\n\n--- After round 1 ---\nPlanner: investigate X demand\nFetched titles: reddit:Planner latency thread"
    compacted = _compact_learning_context(head + tail, max_chars=1200)

    assert len(compacted) <= 1200
    assert "ChatGPT exports" in compacted
    assert "After round 1" in compacted
    assert "Planner latency thread" in compacted


def test_decide_fallback_empty_sets_transport_flag_when_requested():
    from project_guardian.mistral_engine import MistralEngine

    eng = MistralEngine(model="mistral:7b")
    d = eng._decide_fallback_empty({"candidates": []}, planner_transport_failed=True)
    assert d.get("_planner_transport_failed") is True
    d2 = eng._decide_fallback_empty({"candidates": []})
    assert "_planner_transport_failed" not in d2
    d3 = eng._decide_fallback_empty(
        {"candidates": []},
        planner_transport_failed=False,
        broker_upstream_transport_hint=True,
    )
    assert d3.get("_planner_transport_failed") is True


def test_clean_learning_history_values_dedupes_and_trims():
    cleaned = _clean_learning_history_values(
        [
            "  AI agents for customer complaints   ",
            "AI agents for customer complaints",
            "",
            "compute credits for AI developers " * 12,
        ],
        max_items=6,
        max_chars=40,
    )

    assert cleaned[0] == "AI agents for customer complaints"
    assert cleaned[1].startswith("compute credits for AI developers")
    assert len(cleaned[1]) == 40
