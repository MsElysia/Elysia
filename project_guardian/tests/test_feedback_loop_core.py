"""Focused tests for feedback_loop_core heuristics and AI parsing."""

from project_guardian.ask_ai import AIResponse
from project_guardian.feedback_loop_core import (
    AccuracyEvaluator,
    CreativityEvaluator,
    FeedbackLoopCore,
    StyleEvaluator,
)


class _StubAskAI:
    def __init__(self, response: AIResponse):
        self._response = response
        self.calls = []

    def ask(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return self._response


def test_accuracy_evaluator_uses_structured_ai_payload():
    ask_ai = _StubAskAI(
        AIResponse(
            content='```json\n{"score": 0.91, "feedback": "Well-supported answer", "confidence": 0.82}\n```',
            provider="openai",
            model="gpt-4",
            success=True,
        )
    )

    result = AccuracyEvaluator(ask_ai=ask_ai).evaluate(
        "What causes tides?",
        "Tides are driven mostly by the Moon's gravity.",
    )

    assert result["score"] == 0.91
    assert result["confidence"] == 0.82
    assert result["feedback"] == "Well-supported answer"
    assert result["source"] == "ai"
    assert len(ask_ai.calls) == 1


def test_accuracy_evaluator_falls_back_to_real_heuristics_when_ai_payload_invalid():
    ask_ai = _StubAskAI(
        AIResponse(
            content="This is not JSON at all.",
            provider="openai",
            model="gpt-4",
            success=True,
        )
    )

    result = AccuracyEvaluator(ask_ai=ask_ai).evaluate(
        "Explain photosynthesis.",
        "Studies show it always works and everyone knows that.",
        context={"required_terms": ["sunlight", "chlorophyll"]},
    )

    assert result["score"] < 0.72
    assert "placeholder" not in result["feedback"].lower()
    assert result["missing_terms"] == ["sunlight", "chlorophyll"]
    assert result["heuristic_flags"]["vague_claims"] >= 1


def test_creativity_and_style_evaluators_return_non_placeholder_feedback():
    creativity = CreativityEvaluator().evaluate(
        "Write an opening paragraph.",
        "Imagine a city breathing at dawn, every rooftop catching a different note of light.",
    )
    style = StyleEvaluator().evaluate(
        "Summarize the deployment notes.",
        "Therefore the rollout remains stable. Furthermore, the API latency stayed within target.",
        target_style="formal",
    )

    assert "placeholder" not in creativity["feedback"].lower()
    assert creativity["creative_indicator_count"] >= 1
    assert "placeholder" not in style["feedback"].lower()
    assert style["detected_style"] in {"formal", "technical"}


def test_feedback_loop_core_persists_breakdown_entries(tmp_path):
    storage_path = tmp_path / "feedback_loop.json"
    loop = FeedbackLoopCore(storage_path=str(storage_path))

    result = loop.evaluate_output(
        prompt="Summarize the launch update.",
        response="The launch update is clear, concise, and names the main blockers.",
    )

    assert "overall_score" in result
    assert "breakdown" in result
    assert set(result["breakdown"].keys()) == {"accuracy", "creativity", "style"}
    assert len(loop.feedback_entries) == 3
    assert storage_path.exists()
