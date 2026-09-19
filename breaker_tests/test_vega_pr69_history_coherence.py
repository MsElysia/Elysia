from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    AggregationResult,
    RoutingState,
    Verdict,
    VerdictRecord,
    aggregate_candidate_gate,
)


SHA = "1435c6cfcd0cf76cfe561a4e1c39ece7062ab793"


def test_candidate_pass_cannot_override_preserved_fail_history():
    failure = VerdictRecord("record-fail", SHA, "#39", "independent-verifier", Verdict.FAIL, "proof")
    contradictory = AggregationResult(SHA, "#39", RoutingState.PASS, False, (failure,), ())
    ordinary = AggregationResult(SHA, "#40", RoutingState.PASS, False, (), ())
    assert aggregate_candidate_gate(
        (contradictory, ordinary),
        human_governance_required=False,
        expected_product_sha=SHA,
        required_contracts=("#39", "#40"),
    ) == "BLOCKED_BY_TECHNICAL_VERDICT"
