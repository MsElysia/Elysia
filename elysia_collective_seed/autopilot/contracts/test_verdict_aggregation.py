import itertools
import pytest
from elysia_collective_seed.autopilot.contracts.verdict_aggregation import AuditRecord, AggregationResult, RoutingState, Verdict, VerdictRecord, aggregate_candidate_gate, aggregate_verdict

FAILED_SHA = "7b076548751e72879d0632c1ec687e087e43a7b8"
CURRENT_SHA = "5d0824448656b7e066e8115c92d001a0d9b0237a"
OTHER_SHA = "6" * 40

def vr(record_id, sha, contract, verdict, verifier="vega"):
    return VerdictRecord(record_id, sha, contract, verifier, verdict, f"evidence:{record_id}")

def gate(results, governance=False, sha=CURRENT_SHA, contracts=("#39", "#40")):
    return aggregate_candidate_gate(
        results,
        human_governance_required=governance,
        expected_product_sha=sha,
        required_contracts=contracts,
    )

def test_7b_fail_dominates_prior_pass_in_every_order():
    records = [vr("old-pass", FAILED_SHA, "#40", Verdict.PASS), vr("later-fail", FAILED_SHA, "#40", Verdict.FAIL, "integration-verifier")]
    for order in itertools.permutations(records):
        result = aggregate_verdict(order, product_sha=FAILED_SHA, contract="#40")
        assert result.routing_state is RoutingState.FAIL and result.conflict
        assert {r.record_id for r in result.history} == {"old-pass", "later-fail"}

def test_5d_pass_is_monotonic_per_contract():
    for contract in ("#39", "#40"):
        records = [vr(f"{contract}-pass", CURRENT_SHA, contract, Verdict.PASS), vr(f"{contract}-pending", CURRENT_SHA, contract, Verdict.PENDING), vr(f"{contract}-review", CURRENT_SHA, contract, Verdict.NEEDS_REVIEW)]
        assert aggregate_verdict(records, product_sha=CURRENT_SHA, contract=contract).routing_state is RoutingState.PASS

def test_contract_and_child_sha_isolation():
    parent = vr("39-pass", CURRENT_SHA, "#39", Verdict.PASS)
    assert aggregate_verdict([parent], product_sha=CURRENT_SHA, contract="#40").routing_state is RoutingState.PENDING
    assert aggregate_verdict([parent], product_sha=OTHER_SHA, contract="#39").routing_state is RoutingState.PENDING

def test_unsupported_invalidation_is_audit_only():
    records = [vr("fail", FAILED_SHA, "#40", Verdict.FAIL), AuditRecord("erase", FAILED_SHA, "#40", "invalidate", "fail", "evidence:erase")]
    result = aggregate_verdict(records, product_sha=FAILED_SHA, contract="#40")
    assert result.routing_state is RoutingState.FAIL
    assert {r.record_id for r in result.history} == {"erase", "fail"}

def test_conflicting_duplicate_identity_fails_closed():
    records = [vr("same-id", CURRENT_SHA, "#39", Verdict.PASS), vr("same-id", CURRENT_SHA, "#40", Verdict.PASS)]
    assert aggregate_verdict(records, product_sha=CURRENT_SHA, contract="#39").routing_state is RoutingState.FAIL_CLOSED

def test_raw_mapping_cannot_self_assert_admission():
    forged = {"record_id": "forged", "product_sha": CURRENT_SHA, "contract": "#39", "verdict": "PASS", "admitted": True, "trusted": True, "role": "verifier", "github_owner": True}
    result = aggregate_verdict([forged], product_sha=CURRENT_SHA, contract="#39")
    assert result.routing_state is RoutingState.FAIL_CLOSED
    assert result.history == ()

def test_unknown_verdict_fails_closed_without_sort_dereference():
    bad = VerdictRecord("bad", CURRENT_SHA, "#39", "vega", "PASS", "evidence:bad")  # type: ignore[arg-type]
    result = aggregate_verdict([bad], product_sha=CURRENT_SHA, contract="#39")
    assert result.routing_state is RoutingState.FAIL_CLOSED
    assert "unknown_verdict" in result.reasons
    assert result.history == ()

def test_malformed_record_sha_fails_closed_before_sort():
    bad = vr("bad-sha", "not-a-sha", "#39", Verdict.PASS)
    result = aggregate_verdict([bad], product_sha=CURRENT_SHA, contract="#39")
    assert result.routing_state is RoutingState.FAIL_CLOSED
    assert "malformed_product_sha" in result.reasons
    assert result.history == ()

def test_target_requires_exact_lowercase_40_hex_sha():
    for bad_sha in ("", "abc", "g" * 40, CURRENT_SHA.upper(), CURRENT_SHA + "0"):
        with pytest.raises(ValueError):
            aggregate_verdict([], product_sha=bad_sha, contract="#39")

def test_invalid_history_is_deterministic_across_input_order():
    valid = vr("good", CURRENT_SHA, "#39", Verdict.PASS)
    bad_verdict = VerdictRecord("bad-v", CURRENT_SHA, "#39", "vega", "PASS", "evidence:bad-v")  # type: ignore[arg-type]
    bad_sha = vr("bad-s", "short", "#39", Verdict.FAIL)
    expected = aggregate_verdict([valid, bad_verdict, bad_sha], product_sha=CURRENT_SHA, contract="#39")
    for order in itertools.permutations([valid, bad_verdict, bad_sha]):
        assert aggregate_verdict(order, product_sha=CURRENT_SHA, contract="#39") == expected
    assert expected.routing_state is RoutingState.FAIL_CLOSED
    assert expected.history == (valid,)

def test_permutation_and_replay_are_deterministic():
    records = [vr("b", CURRENT_SHA, "#39", Verdict.PENDING), vr("a", CURRENT_SHA, "#39", Verdict.PASS), AuditRecord("c", CURRENT_SHA, "#39", "retract", "a", "evidence:c")]
    expected = aggregate_verdict(records, product_sha=CURRENT_SHA, contract="#39")
    for order in itertools.permutations(records):
        assert aggregate_verdict(order, product_sha=CURRENT_SHA, contract="#39") == expected
    assert aggregate_verdict(expected.history, product_sha=CURRENT_SHA, contract="#39") == expected

def passing_results(sha=CURRENT_SHA):
    return [
        aggregate_verdict([vr("39", sha, "#39", Verdict.PASS)], product_sha=sha, contract="#39"),
        aggregate_verdict([vr("40", sha, "#40", Verdict.PASS)], product_sha=sha, contract="#40"),
    ]

def test_human_gate_is_separate_and_dominant():
    results = passing_results()
    assert gate(results, governance=True) == "BLOCKED_BY_HUMAN_GOVERNANCE"
    assert gate(results, governance=False) == "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"

@pytest.mark.parametrize("malformed", [0, 0.0, "", [], {}, None, 1, "false"])
def test_malformed_human_governance_flag_fails_closed(malformed):
    assert gate(passing_results(), governance=malformed) == "BLOCKED_BY_HUMAN_GOVERNANCE"  # type: ignore[arg-type]

class ExplodingTechnicalResults:
    def __iter__(self):
        raise AssertionError("technical results must not be consumed before governance")

class CountingTechnicalResults:
    def __init__(self):
        self.consumed = 0

    def __iter__(self):
        self.consumed += 1
        yield from passing_results()

@pytest.mark.parametrize("governance", [True, None, 0, 1, "false", [], {}])
def test_human_governance_blocks_before_throwing_technical_iterable(governance):
    assert gate(ExplodingTechnicalResults(), governance=governance) == "BLOCKED_BY_HUMAN_GOVERNANCE"  # type: ignore[arg-type]

@pytest.mark.parametrize("governance", [True, None, 0, 1, "false", [], {}])
def test_human_governance_blocks_with_zero_technical_consumption(governance):
    results = CountingTechnicalResults()
    assert gate(results, governance=governance) == "BLOCKED_BY_HUMAN_GOVERNANCE"  # type: ignore[arg-type]
    assert results.consumed == 0

def test_false_human_governance_still_consumes_and_routes_complete_results():
    results = CountingTechnicalResults()
    assert gate(results, governance=False) == "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"
    assert results.consumed == 1

def test_mixed_product_pass_results_cannot_compose():
    mixed = [
        aggregate_verdict([vr("39", CURRENT_SHA, "#39", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#39"),
        aggregate_verdict([vr("40", OTHER_SHA, "#40", Verdict.PASS)], product_sha=OTHER_SHA, contract="#40"),
    ]
    assert gate(mixed) == "BLOCKED_BY_TECHNICAL_VERDICT"

def test_duplicate_contract_cannot_substitute_for_missing_required_contract():
    one = aggregate_verdict([vr("39", CURRENT_SHA, "#39", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#39")
    assert gate([one, one]) == "BLOCKED_BY_TECHNICAL_VERDICT"

def test_unexpected_contract_fails_closed():
    unexpected = aggregate_verdict([vr("41", CURRENT_SHA, "#41", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#41")
    assert gate(passing_results() + [unexpected]) == "BLOCKED_BY_TECHNICAL_VERDICT"

def test_missing_required_contract_remains_pending():
    one = aggregate_verdict([vr("39", CURRENT_SHA, "#39", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#39")
    assert gate([one]) == "PENDING"

def test_exact_identity_complete_unique_pass_set_routes_technical_pass():
    assert gate(passing_results()) == "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"

@pytest.mark.parametrize("state", [RoutingState.FAIL, RoutingState.FAIL_CLOSED])
def test_fail_states_remain_dominant(state):
    results = passing_results()
    results[1] = AggregationResult(CURRENT_SHA, "#40", state, state is RoutingState.FAIL_CLOSED, (), ())
    assert gate(results) == "BLOCKED_BY_TECHNICAL_VERDICT"

@pytest.mark.parametrize("bad_sha", ["", "abc", "g" * 40, CURRENT_SHA.upper()])
def test_candidate_expected_sha_must_be_exact(bad_sha):
    assert gate(passing_results(), sha=bad_sha) == "BLOCKED_BY_TECHNICAL_VERDICT"

@pytest.mark.parametrize("contracts", [(), ("",), ("#39", "#39")])
def test_required_contract_set_must_be_nonempty_unique_and_well_formed(contracts):
    assert gate(passing_results(), contracts=contracts) == "BLOCKED_BY_TECHNICAL_VERDICT"

@pytest.mark.parametrize("bad_contract", [[], {}, 0, None, ""])
def test_malformed_result_contract_fails_closed_without_exception(bad_contract):
    bad = AggregationResult(CURRENT_SHA, bad_contract, RoutingState.PASS, False, (), ())  # type: ignore[arg-type]
    assert gate([bad]) == "BLOCKED_BY_TECHNICAL_VERDICT"

@pytest.mark.parametrize("bad_sha", [[], {}, 0, None, "short"])
def test_malformed_result_product_sha_fails_closed_without_exception(bad_sha):
    bad = AggregationResult(bad_sha, "#39", RoutingState.PASS, False, (), ())  # type: ignore[arg-type]
    assert gate([bad]) == "BLOCKED_BY_TECHNICAL_VERDICT"

@pytest.mark.parametrize("bad_state", ["PASS", 0, None, [], {}])
def test_malformed_result_routing_state_fails_closed_without_exception(bad_state):
    bad = AggregationResult(CURRENT_SHA, "#39", bad_state, False, (), ())  # type: ignore[arg-type]
    assert gate([bad]) == "BLOCKED_BY_TECHNICAL_VERDICT"

def test_pass_with_conflict_fails_closed():
    results = passing_results()
    results[0] = AggregationResult(CURRENT_SHA, "#39", RoutingState.PASS, True, (), ())
    assert gate(results) == "BLOCKED_BY_TECHNICAL_VERDICT"

def test_pass_with_failure_reason_fails_closed():
    results = passing_results()
    results[0] = AggregationResult(CURRENT_SHA, "#39", RoutingState.PASS, False, (), ("unknown_verdict",))
    assert gate(results) == "BLOCKED_BY_TECHNICAL_VERDICT"

@pytest.mark.parametrize("bad_conflict", [0, 1, None, "", [], {}])
def test_malformed_result_conflict_fails_closed(bad_conflict):
    bad = AggregationResult(CURRENT_SHA, "#39", RoutingState.PASS, bad_conflict, (), ())  # type: ignore[arg-type]
    assert gate([bad]) == "BLOCKED_BY_TECHNICAL_VERDICT"

@pytest.mark.parametrize("bad_reasons", [None, "", [], {}, (0,), ("",)])
def test_malformed_result_reasons_fail_closed(bad_reasons):
    bad = AggregationResult(CURRENT_SHA, "#39", RoutingState.PASS, False, (), bad_reasons)  # type: ignore[arg-type]
    assert gate([bad]) == "BLOCKED_BY_TECHNICAL_VERDICT"

class FalseyReasons(tuple):
    def __bool__(self):
        return False

def test_falsey_tuple_subclass_failure_reasons_fail_closed():
    results = passing_results()
    results[0] = AggregationResult(
        CURRENT_SHA,
        "#39",
        RoutingState.PASS,
        False,
        (),
        FalseyReasons(("unknown_verdict",)),
    )
    assert gate(results) == "BLOCKED_BY_TECHNICAL_VERDICT"


class FalseyHistory(tuple):
    def __bool__(self):
        return False


def test_candidate_pass_cannot_contradict_same_scope_fail_history():
    results = passing_results()
    contradictory_history = (
        vr("39-pass-history", CURRENT_SHA, "#39", Verdict.PASS),
        vr("39-fail-history", CURRENT_SHA, "#39", Verdict.FAIL, "integration-verifier"),
    )
    results[0] = AggregationResult(
        CURRENT_SHA,
        "#39",
        RoutingState.PASS,
        False,
        contradictory_history,
        (),
    )
    assert gate(results) == "BLOCKED_BY_TECHNICAL_VERDICT"


def test_candidate_header_must_match_canonical_history_reduction():
    results = passing_results()
    pass_history = (vr("39-pass-history", CURRENT_SHA, "#39", Verdict.PASS),)
    results[0] = AggregationResult(
        CURRENT_SHA,
        "#39",
        RoutingState.PENDING,
        False,
        pass_history,
        (),
    )
    assert gate(results) == "BLOCKED_BY_TECHNICAL_VERDICT"


@pytest.mark.parametrize("bad_history", [None, [], {}, "history"])
def test_malformed_candidate_history_container_fails_closed(bad_history):
    bad = AggregationResult(
        CURRENT_SHA,
        "#39",
        RoutingState.PASS,
        False,
        bad_history,  # type: ignore[arg-type]
        (),
    )
    assert gate([bad]) == "BLOCKED_BY_TECHNICAL_VERDICT"


def test_history_tuple_subclass_fails_closed():
    bad = AggregationResult(
        CURRENT_SHA,
        "#39",
        RoutingState.PASS,
        False,
        FalseyHistory((vr("39", CURRENT_SHA, "#39", Verdict.PASS),)),
        (),
    )
    assert gate([bad]) == "BLOCKED_BY_TECHNICAL_VERDICT"
