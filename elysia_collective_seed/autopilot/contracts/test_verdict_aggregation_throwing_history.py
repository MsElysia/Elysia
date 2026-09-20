from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    AggregationResult,
    RoutingState,
    Verdict,
    VerdictRecord,
    aggregate_candidate_gate,
    aggregate_verdict,
)

SHA = "5d0824448656b7e066e8115c92d001a0d9b0237a"


def _result(contract: str) -> AggregationResult:
    record = VerdictRecord(f"{contract}-pass", SHA, contract, "vega", Verdict.PASS, "evidence:pass")
    return aggregate_verdict((record,), product_sha=SHA, contract=contract)


def _gate(results, governance=False):
    return aggregate_candidate_gate(
        results,
        human_governance_required=governance,
        expected_product_sha=SHA,
        required_contracts=("#39", "#40"),
    )


class ThrowingStr(str):
    def strip(self, *args, **kwargs):
        raise RuntimeError("attacker-controlled strip must not escape")


def test_throwing_str_subclass_in_history_fails_closed():
    results = [_result("#39"), _result("#40")]
    bad = VerdictRecord(ThrowingStr("record"), SHA, "#39", "vega", Verdict.PASS, "evidence:bad")
    results[0] = AggregationResult(SHA, "#39", RoutingState.PASS, False, (bad,), ())
    assert _gate(results) == "BLOCKED_BY_TECHNICAL_VERDICT"


def test_exact_builtin_history_strings_still_pass():
    assert _gate([_result("#39"), _result("#40")]) == "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"


def test_human_governance_remains_zero_touch():
    class Exploding:
        def __iter__(self):
            raise AssertionError("technical results consumed before governance")

    assert _gate(Exploding(), governance=True) == "BLOCKED_BY_HUMAN_GOVERNANCE"
