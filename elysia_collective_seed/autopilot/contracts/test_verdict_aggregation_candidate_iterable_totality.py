from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    RoutingState,
    Verdict,
    VerdictRecord,
    aggregate_candidate_gate,
    aggregate_verdict,
)

SHA = "5d0824448656b7e066e8115c92d001a0d9b0237a"


class RuntimeThrowingIterable:
    def __iter__(self):
        raise RuntimeError("preserved candidate-iterable breaker")


def _pass(contract: str):
    record = VerdictRecord(
        f"{contract}-pass",
        SHA,
        contract,
        "vega",
        Verdict.PASS,
        f"evidence:{contract}",
    )
    return aggregate_verdict([record], product_sha=SHA, contract=contract)


def _gate(results, *, governance=False, contracts=("#39", "#40")):
    return aggregate_candidate_gate(
        results,
        human_governance_required=governance,
        expected_product_sha=SHA,
        required_contracts=contracts,
    )


def test_required_contract_materialization_runtime_error_fails_closed():
    assert _gate([], contracts=RuntimeThrowingIterable()) == "BLOCKED_BY_TECHNICAL_VERDICT"


def test_technical_result_materialization_runtime_error_fails_closed():
    assert _gate(RuntimeThrowingIterable()) == "BLOCKED_BY_TECHNICAL_VERDICT"


def test_governance_remains_zero_touch_over_runtime_throwing_iterables():
    assert _gate(
        RuntimeThrowingIterable(),
        governance=True,
        contracts=RuntimeThrowingIterable(),
    ) == "BLOCKED_BY_HUMAN_GOVERNANCE"


def test_ordinary_complete_candidate_still_routes_technical_pass():
    assert _gate([_pass("#39"), _pass("#40")]) == "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"
