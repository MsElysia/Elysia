from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    AggregationResult,
    RoutingState,
    Verdict,
    VerdictRecord,
    aggregate_candidate_gate,
)


SHA = "e7efbd060d7255cd7b09dd6cd0ada13dec364ae0"


class ThrowingString(str):
    def strip(self):
        raise RuntimeError("hostile history field")


def test_throwing_typed_history_field_fails_closed_without_exception():
    record = VerdictRecord(ThrowingString("record"), SHA, "#39", "verifier", Verdict.PASS, "proof")
    candidate = AggregationResult(SHA, "#39", RoutingState.PASS, False, (record,), ())
    assert aggregate_candidate_gate(
        (candidate,),
        human_governance_required=False,
        expected_product_sha=SHA,
        required_contracts=("#39",),
    ) == "BLOCKED_BY_TECHNICAL_VERDICT"
