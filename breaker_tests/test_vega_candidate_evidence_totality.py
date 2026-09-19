"""Vega falsification for PR #67 candidate evidence validation."""

from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    AggregationResult,
    RoutingState,
    aggregate_candidate_gate,
)


SHA = "608fe671822387c977a7dc9e435d4bbf41e5afed"


def _gate(results):
    return aggregate_candidate_gate(
        results,
        human_governance_required=False,
        expected_product_sha=SHA,
        required_contracts=("#39", "#40"),
    )


def test_conflicted_pass_result_cannot_earn_candidate_pass():
    conflicted = AggregationResult(SHA, "#39", RoutingState.PASS, True, (), ())
    ordinary = AggregationResult(SHA, "#40", RoutingState.PASS, False, (), ())
    assert _gate((conflicted, ordinary)) == "BLOCKED_BY_TECHNICAL_VERDICT"


def test_pass_result_with_fail_closed_reason_cannot_earn_candidate_pass():
    invalid = AggregationResult(SHA, "#39", RoutingState.PASS, False, (), ("unknown_verdict",))
    ordinary = AggregationResult(SHA, "#40", RoutingState.PASS, False, (), ())
    assert _gate((invalid, ordinary)) == "BLOCKED_BY_TECHNICAL_VERDICT"
