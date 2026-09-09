from project_guardian.feedback_loop import FeedbackLoopAdapter, FeedbackLoopCore


def _result_by_module(report, module_fragment):
    for result in report["detailed_results"]:
        if module_fragment in result["module"]:
            return result
    raise AssertionError(f"Missing feedback module containing {module_fragment!r}")


def test_legacy_feedback_flags_missing_terms_and_unsupported_claims():
    loop = FeedbackLoopCore()

    report = loop.evaluate_output(
        "Studies show everyone knows 92% of launches always work, with 84% uptime and 73% fewer incidents.",
        context={
            "required_terms": ["cleanup threshold"],
            "requires_citation": True,
        },
    )

    accuracy = _result_by_module(report, "accuracy")
    assert accuracy["score"] <= 2
    assert "cleanup threshold" in accuracy["advice"]
    assert "source" in accuracy["advice"].lower()
    assert report["needs_revision"] is True
    assert "feedbackloop.accuracy_evaluator" in report["lowest_modules"]


def test_legacy_feedback_respects_preferences_and_context_formatting():
    loop = FeedbackLoopCore()
    loop.log_user_preference("operator", "format", "bullets")
    loop.log_user_preference("operator", "avoid", "placeholder")

    report = loop.evaluate_output(
        "This placeholder response is a plain paragraph and cannot match the requested tone.",
        context={
            "user_id": "operator",
            "target_tone": "casual",
            "required_format": "bullets",
        },
    )

    preference = _result_by_module(report, "preference")
    style = _result_by_module(report, "style")
    assert preference["score"] < 4
    assert "placeholder" in preference["advice"]
    assert style["score"] < 5
    assert any("bullet" in item.lower() for item in report["action_items"])


def test_feedback_loop_adapter_handles_non_dict_payload_context_and_limit():
    loop = FeedbackLoopCore()
    adapter = FeedbackLoopAdapter(loop)

    eval_result = adapter.execute(
        "evaluate_output",
        {"output": "A concise answer with one concrete next step.", "context": "bad-context"},
    )
    history_result = adapter.execute("get_evaluation_history", {"limit": "1"})

    assert eval_result["success"] is True
    assert "feedback_report" in eval_result
    assert history_result["success"] is True
    assert len(history_result["history"]) == 1
