import itertools
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
    assert aggregate_verdict([forged], product_sha=CURRENT_SHA, contract="#39").routing_state is RoutingState.FAIL_CLOSED

def test_unknown_verdict_fails_closed():
    bad = VerdictRecord("bad", CURRENT_SHA, "#39", "vega", "PASS", "evidence:bad")  # type: ignore[arg-type]
    assert aggregate_verdict([bad], product_sha=CURRENT_SHA, contract="#39").routing_state is RoutingState.FAIL_CLOSED

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
