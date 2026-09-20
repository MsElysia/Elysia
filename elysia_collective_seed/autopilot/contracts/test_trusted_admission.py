from dataclasses import replace

import pytest

from elysia_collective_seed.autopilot.contracts.trusted_admission import (
    AdmissionRequest,
    AdmissionStatus,
    AuthenticatedPrincipal,
    VerifierEligibility,
    admit_verdict,
)
from elysia_collective_seed.autopilot.contracts.verdict_aggregation import Verdict, VerdictRecord


SHA = "25b34c19975ae281c676fe2b7a0a8d63538e2511"
OTHER_SHA = "6" * 40
NOW = 1_800_000_000


def principal():
    return AuthenticatedPrincipal("vega", "test-auth", "auth:event:1", NOW - 10, 7)


def eligibility():
    return VerifierEligibility("grant-1", "vega", "verifier", ("#46",), (SHA,), 7, NOW + 100, "policy:test")


def request():
    return AdmissionRequest("submission-1", SHA, "#46", Verdict.PASS, "evidence:test")


def admit(p=None, e=None, r=None, **kwargs):
    return admit_verdict(
        principal() if p is None else p,
        eligibility() if e is None else e,
        request() if r is None else r,
        expected_policy_generation=kwargs.pop("expected_policy_generation", 7),
        now_epoch_s=kwargs.pop("now_epoch_s", NOW),
        trusted_authentication_methods=kwargs.pop("trusted_authentication_methods", ("test-auth",)),
        **kwargs,
    )


def test_valid_bindings_produce_one_immutable_typed_record():
    decision = admit()
    assert decision.audit.status is AdmissionStatus.ADMITTED
    assert decision.audit.reason == "all_bindings_valid"
    assert type(decision.record) is VerdictRecord
    assert decision.record.verifier_id == "vega"


@pytest.mark.parametrize("raw", [None, {}, [], "", {"authenticated": True, "trusted": True, "admitted": True}])
def test_raw_or_self_asserted_principal_cannot_enter(raw):
    decision = admit(p=raw)
    assert decision.audit.status is AdmissionStatus.REJECTED
    assert decision.record is None


class ExplodingAttributes:
    def __getattribute__(self, name):
        raise RuntimeError("untrusted attribute access must not execute")


def test_untrusted_objects_reject_without_attribute_access():
    assert admit(p=ExplodingAttributes()).audit.reason == "untrusted_principal_shape"
    assert admit(e=ExplodingAttributes()).audit.reason == "untrusted_eligibility_shape"
    assert admit(r=ExplodingAttributes()).audit.reason == "untrusted_request_shape"


def test_authentication_does_not_grant_wrong_contract_or_sha():
    assert admit(r=replace(request(), contract="#40")).audit.reason == "contract_not_eligible"
    assert admit(r=replace(request(), product_sha=OTHER_SHA)).audit.reason == "product_sha_not_eligible"


def test_identity_policy_and_expiry_fail_closed():
    assert admit(e=replace(eligibility(), principal_id="other")).audit.reason == "principal_eligibility_mismatch"
    assert admit(expected_policy_generation=8).audit.reason == "stale_policy_generation"
    assert admit(e=replace(eligibility(), expires_at_epoch_s=NOW)).audit.reason == "expired_eligibility"
    assert admit(p=replace(principal(), authentication_method="github-owner")).audit.reason == "untrusted_authentication_method"


def test_identical_replay_is_idempotent_and_conflict_rejects():
    first = admit()
    assert admit(prior_decisions=(first,)) == first
    conflicting = replace(request(), verdict=Verdict.FAIL)
    decision = admit(r=conflicting, prior_decisions=(first,))
    assert decision.audit.reason == "conflicting_submission_id"
    assert decision.record is None


def test_conflicting_prior_history_fails_closed_in_every_order():
    first = admit()
    second = admit(r=replace(request(), verdict=Verdict.FAIL))
    for history in ((first, second), (second, first)):
        decision = admit(prior_decisions=history)
        assert decision.audit.reason == "conflicting_submission_id"
        assert decision.record is None


class ThrowingStr(str):
    def strip(self, *args, **kwargs):
        raise RuntimeError("untrusted method must not execute")

    def encode(self, *args, **kwargs):
        raise RuntimeError("untrusted method must not execute")


@pytest.mark.parametrize(
    "bad",
    [
        lambda: (replace(principal(), principal_id=ThrowingStr("vega")), eligibility(), request()),
        lambda: (replace(principal(), authentication_event_ref=ThrowingStr("event")), eligibility(), request()),
        lambda: (principal(), replace(eligibility(), grant_id=ThrowingStr("grant")), request()),
        lambda: (principal(), replace(eligibility(), contracts=(ThrowingStr("#46"),)), request()),
        lambda: (principal(), replace(eligibility(), product_shas=(ThrowingStr(SHA),)), request()),
        lambda: (principal(), eligibility(), replace(request(), submission_id=ThrowingStr("submission"))),
        lambda: (principal(), eligibility(), replace(request(), evidence_ref=ThrowingStr("evidence"))),
    ],
)
def test_hostile_string_subclasses_reject_without_execution(bad):
    p, e, r = bad()
    decision = admit(p=p, e=e, r=r)
    assert decision.audit.status is AdmissionStatus.REJECTED
    assert decision.record is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"expected_policy_generation": True},
        {"now_epoch_s": "now"},
        {"trusted_authentication_methods": ["test-auth"]},
        {"trusted_authentication_methods": ()},
        {"prior_decisions": []},
        {"prior_decisions": ({"status": "ADMITTED"},)},
    ],
)
def test_malformed_policy_and_history_inputs_reject(kwargs):
    decision = admit(**kwargs)
    assert decision.audit.status is AdmissionStatus.REJECTED
    assert decision.record is None


def test_future_authentication_and_non_verifier_role_reject():
    assert admit(p=replace(principal(), authenticated_at_epoch_s=NOW + 1)).audit.reason == "future_authentication_event"
    assert admit(e=replace(eligibility(), role="owner")).audit.reason == "ineligible_role"


def test_contract_has_no_routing_or_runtime_entrypoint():
    import elysia_collective_seed.autopilot.contracts.trusted_admission as module

    assert not hasattr(module, "aggregate_verdict")
    assert not hasattr(module, "aggregate_candidate_gate")
    assert not hasattr(module, "route")
    assert not hasattr(module, "activate")
