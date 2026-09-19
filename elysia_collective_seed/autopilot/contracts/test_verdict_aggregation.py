import itertools
import pytest
from elysia_collective_seed.autopilot.contracts.verdict_aggregation import AuditRecord, RoutingState, Verdict, VerdictRecord, aggregate_candidate_gate, aggregate_verdict

FAILED_SHA = "7b076548751e72879d0632c1ec687e087e43a7b8"
CURRENT_SHA = "5d0824448656b7e066e8115c92d001a0d9b0237a"

def vr(record_id, sha, contract, verdict, verifier="vega"):
    return VerdictRecord(record_id, sha, contract, verifier, verdict, f"evidence:{record_id}")

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
    assert aggregate_verdict([parent], product_sha="6" * 40, contract="#39").routing_state is RoutingState.PENDING

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

def test_human_gate_is_separate_and_dominant():
    results = [aggregate_verdict([vr("39", CURRENT_SHA, "#39", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#39"), aggregate_verdict([vr("40", CURRENT_SHA, "#40", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#40")]
    assert aggregate_candidate_gate(results, human_governance_required=True) == "BLOCKED_BY_HUMAN_GOVERNANCE"
    assert aggregate_candidate_gate(results, human_governance_required=False) == "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"

@pytest.mark.parametrize("malformed", [0, 0.0, "", [], {}, None, 1, "false"])
def test_malformed_human_governance_flag_fails_closed(malformed):
    results = [aggregate_verdict([vr("39", CURRENT_SHA, "#39", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#39")]
    assert aggregate_candidate_gate(results, human_governance_required=malformed) == "BLOCKED_BY_HUMAN_GOVERNANCE"  # type: ignore[arg-type]

class ExplodingTechnicalResults:
    def __iter__(self):
        raise AssertionError("technical results must not be consumed before governance")

class CountingTechnicalResults:
    def __init__(self):
        self.consumed = 0

    def __iter__(self):
        self.consumed += 1
        yield aggregate_verdict([vr("39", CURRENT_SHA, "#39", Verdict.PASS)], product_sha=CURRENT_SHA, contract="#39")

@pytest.mark.parametrize("governance", [True, None, 0, 1, "false", [], {}])
def test_human_governance_blocks_before_throwing_technical_iterable(governance):
    assert aggregate_candidate_gate(ExplodingTechnicalResults(), human_governance_required=governance) == "BLOCKED_BY_HUMAN_GOVERNANCE"  # type: ignore[arg-type]

@pytest.mark.parametrize("governance", [True, None, 0, 1, "false", [], {}])
def test_human_governance_blocks_with_zero_technical_consumption(governance):
    results = CountingTechnicalResults()
    assert aggregate_candidate_gate(results, human_governance_required=governance) == "BLOCKED_BY_HUMAN_GOVERNANCE"  # type: ignore[arg-type]
    assert results.consumed == 0

def test_false_human_governance_still_consumes_and_routes_technical_results():
    results = CountingTechnicalResults()
    assert aggregate_candidate_gate(results, human_governance_required=False) == "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"
    assert results.consumed == 1
