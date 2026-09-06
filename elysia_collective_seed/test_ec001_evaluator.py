from elysia_collective_seed.ec001_evaluator import RunScores, evaluate


BASE = {
    "accuracy": 0.70,
    "completeness": 0.65,
    "originality": 0.55,
    "risk_detection": 0.60,
    "implementation_feasibility": 0.65,
    "self_correction": 0.50,
    "provenance_quality": 0.70,
}


def test_positive_collective_lift():
    control = RunScores("control", BASE, cost_units=1.0)
    collective_dims = {k: min(1.0, v + 0.10) for k, v in BASE.items()}
    collective = RunScores("collective", collective_dims, cost_units=1.5)

    result = evaluate(control, collective)

    assert result.absolute_lift > 0
    assert len(result.collective_wins) == len(BASE)
    assert "no_positive_collective_lift" not in result.guardrail_flags


def test_detects_costly_non_improvement_and_more_errors():
    control = RunScores("control", BASE, cost_units=1.0, severe_error_count=0)
    collective = RunScores(
        "collective",
        BASE,
        cost_units=3.0,
        severe_error_count=1,
        unsupported_claim_count=2,
    )

    result = evaluate(control, collective)

    assert "no_positive_collective_lift" in result.guardrail_flags
    assert "weak_lift_for_cost" in result.guardrail_flags
    assert "collective_increased_severe_errors" in result.guardrail_flags
    assert "collective_increased_unsupported_claims" in result.guardrail_flags


def test_rejects_out_of_range_scores():
    bad = dict(BASE)
    bad["accuracy"] = 1.2
    try:
        evaluate(RunScores("control", bad, 1.0), RunScores("collective", BASE, 1.0))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
