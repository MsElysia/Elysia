from dataclasses import replace

import pytest

from elysia_collective_seed.autopilot.contracts.verdict_aggregation import (
    AggregationResult,
    AuditRecord,
    RoutingState,
    Verdict,
    VerdictRecord,
    aggregate_candidate_gate,
)


SHA = "25b34c19975ae281c676fe2b7a0a8d63538e2511"


class ThrowingString(str):
    def strip(self):
        raise RuntimeError("hostile string")


def gate(record):
    result = AggregationResult(SHA, "#39", RoutingState.PASS, False, (record,), ())
    return aggregate_candidate_gate(
        (result,),
        human_governance_required=False,
        expected_product_sha=SHA,
        required_contracts=("#39",),
    )


@pytest.mark.parametrize("field", ("record_id", "contract", "evidence_ref", "verifier_id", "product_sha"))
def test_throwing_verdict_record_fields_fail_closed(field):
    record = VerdictRecord("id", SHA, "#39", "verifier", Verdict.PASS, "proof")
    assert gate(replace(record, **{field: ThrowingString(getattr(record, field))})) == "BLOCKED_BY_TECHNICAL_VERDICT"


@pytest.mark.parametrize("field", ("record_id", "contract", "evidence_ref", "action", "target_record_id", "product_sha"))
def test_throwing_audit_record_fields_fail_closed(field):
    record = AuditRecord("id", SHA, "#39", "retract", "target", "proof")
    assert gate(replace(record, **{field: ThrowingString(getattr(record, field))})) == "BLOCKED_BY_TECHNICAL_VERDICT"
