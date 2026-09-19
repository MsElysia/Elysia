from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    AggregationResult,
    RoutingState,
    aggregate_candidate_gate,
)


SHA = "7ead936ff6728fab640b3438ce6d454b62f1354c"


class FalseyReasons(tuple):
    def __bool__(self):
        return False


def test_pass_cannot_hide_failure_reason_in_falsey_tuple_subclass():
    contradictory = AggregationResult(
        SHA, "#39", RoutingState.PASS, False, (), FalseyReasons(("unknown_verdict",))
    )
    ordinary = AggregationResult(SHA, "#40", RoutingState.PASS, False, (), ())
    assert aggregate_candidate_gate(
        (contradictory, ordinary),
        human_governance_required=False,
        expected_product_sha=SHA,
        required_contracts=("#39", "#40"),
    ) == "BLOCKED_BY_TECHNICAL_VERDICT"
