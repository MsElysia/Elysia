from dataclasses import replace

import pytest

from elysia_collective_seed.autopilot.contracts.trusted_admission import (
    AdmissionRequest, AdmissionStatus, AuthenticatedPrincipal, VerifierEligibility, admit_verdict,
)
from elysia_collective_seed.autopilot.contracts.verdict_aggregation import Verdict


SHA = "8a61c49d3e8c19496fe63fe386c1e3262d5b2472"
NOW = 1_800_000_000


def inputs():
    principal = AuthenticatedPrincipal("vega", "test-auth", "auth:event:1", NOW - 1, 7)
    eligibility = VerifierEligibility("grant", "vega", "verifier", ("#46",), (SHA,), 7, NOW + 1, "issuer")
    request = AdmissionRequest("submission", SHA, "#46", Verdict.PASS, "evidence")
    return principal, eligibility, request


def admit(prior_decisions=()):
    principal, eligibility, request = inputs()
    return admit_verdict(
        principal, eligibility, request,
        expected_policy_generation=7, now_epoch_s=NOW,
        trusted_authentication_methods=("test-auth",), prior_decisions=prior_decisions,
    )


@pytest.mark.parametrize("field,bad", (
    ("record_id", "other"), ("product_sha", "6" * 40), ("contract", "#40"),
    ("verifier_id", "other"), ("verdict", Verdict.FAIL), ("evidence_ref", "other"),
))
def test_forged_prior_record_cannot_hide_after_valid_replay(field, bad):
    first = admit()
    assert first.audit.status is AdmissionStatus.ADMITTED
    forged = replace(first, record=replace(first.record, **{field: bad}))
    for history in ((first, forged), (forged, first)):
        result = admit(prior_decisions=history)
        assert result.audit.status is AdmissionStatus.REJECTED
        assert result.record is None
