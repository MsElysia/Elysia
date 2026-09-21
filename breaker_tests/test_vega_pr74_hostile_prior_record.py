from dataclasses import replace

from elysia_collective_seed.autopilot.contracts.trusted_admission import (
    AdmissionRequest,
    AdmissionStatus,
    AuthenticatedPrincipal,
    VerifierEligibility,
    admit_verdict,
)
from elysia_collective_seed.autopilot.contracts.verdict_aggregation import Verdict


SHA = "664201f9e40a025c57bc65c4575b7137b00e64a7"
NOW = 1_800_000_000


class ThrowingString(str):
    def __ne__(self, other):
        raise RuntimeError("hostile prior record equality")


def test_hostile_prior_record_field_rejects_without_exception():
    principal = AuthenticatedPrincipal("vega", "test-auth", "auth:event:1", NOW - 1, 7)
    eligibility = VerifierEligibility("grant", "vega", "verifier", ("#46",), (SHA,), 7, NOW + 1, "issuer")
    request = AdmissionRequest("submission", SHA, "#46", Verdict.PASS, "evidence")
    kwargs = dict(expected_policy_generation=7, now_epoch_s=NOW, trusted_authentication_methods=("test-auth",))
    first = admit_verdict(principal, eligibility, request, **kwargs)
    assert first.audit.status is AdmissionStatus.ADMITTED
    hostile = replace(first, record=replace(first.record, record_id=ThrowingString("submission")))
    replay = admit_verdict(principal, eligibility, request, prior_decisions=(hostile,), **kwargs)
    assert replay.audit.status is AdmissionStatus.REJECTED
    assert replay.record is None
