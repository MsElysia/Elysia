"""Vega falsification tests for PR #47 exact-SHA verdict aggregation."""

from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    RoutingState,
    Verdict,
    VerdictRecord,
    aggregate_verdict,
)


SHA = "65353acf450ad6bf801d2fd476454c283b3a38b0"


def _pass(record_id: str = "pass", *, sha: str = SHA) -> VerdictRecord:
    return VerdictRecord(record_id, sha, "#46", "vega", Verdict.PASS, "evidence:vega")


def test_unknown_verdict_fails_closed_without_exception() -> None:
    record = VerdictRecord("bad", SHA, "#46", "vega", "PASS", "evidence:bad")  # type: ignore[arg-type]
    result = aggregate_verdict([record], product_sha=SHA, contract="#46")
    assert result.routing_state is RoutingState.FAIL_CLOSED


def test_untyped_history_is_deterministic_across_discovery_order() -> None:
    forged = {"record_id": "forged", "product_sha": SHA, "contract": "#46"}
    forward = aggregate_verdict([_pass(), forged], product_sha=SHA, contract="#46")
    reverse = aggregate_verdict([forged, _pass()], product_sha=SHA, contract="#46")
    assert forward == reverse


def test_malformed_product_sha_cannot_become_pass() -> None:
    malformed = "not-an-exact-git-sha"
    result = aggregate_verdict([_pass(sha=malformed)], product_sha=malformed, contract="#46")
    assert result.routing_state is RoutingState.FAIL_CLOSED
