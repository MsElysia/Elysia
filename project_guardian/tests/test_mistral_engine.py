# project_guardian/tests/test_mistral_engine.py
# Test Mistral decision engine (requires Ollama running with mistral model)

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


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
