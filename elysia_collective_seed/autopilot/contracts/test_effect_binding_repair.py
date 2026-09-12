"""Normative exact-effect and immutable-provenance repair tests."""
from copy import deepcopy

import pytest

from .blueprint import (
    BlueprintError,
    attach_task_or_queue_record,
    authorize_progress_chain,
    bridge_record_digest,
    carry_execution_context,
    classify_authoritatively,
    classify_unmediated_output,
    consume_mutation_authorization_ticket,
    issue_mutation_authorization_ticket,
    issue_trusted_admission_record,
    mediated_writer_status,
    progress_transition,
    record_mutation_result,
    record_verification_evidence,
    ticket_bound_actual_effect,
    ticket_current_state,
)
from .checkpoint_reference import snapshot_digest
from .test_blueprint_repair import (
    AUTHORITY_REF,
    CLASSIFIER,
    admission_and_ticket,
    classification,
    effect,
    snapshot,
    target,
)


def result_identity(ticket, value="c" * 40):
    return {
        "kind": "commit_sha",
        "value": value,
        "repository_head_sha": value,
        "write_set_digest": ticket["write_set_digest"],
    }


def consume(ticket, actual_effect, consumed=()):
    return consume_mutation_authorization_ticket(
        ticket,
        ticket_current_state(ticket),
        requested_actions=ticket["action_classes"],
        current_time="2026-09-12T12:10:00Z",
        actual_effect=actual_effect,
        consumed_nonces=consumed,
    )


def successful_chain():
    _, record, ticket = admission_and_ticket()
    identity = result_identity(ticket)
    _, consumed = consume(ticket, ticket_bound_actual_effect(ticket))
    result = record_mutation_result(
        ticket, ticket_bound_actual_effect(ticket), result_identity=identity,
        mutation_status="succeeded", evidence_persisted=True,
        consumed_nonces=consumed,
    )
    verification = record_verification_evidence(
        result, observed_result_identity=identity, verdict="PASS",
        verifier_id="verifier:vega", verifier_provenance=["fixture:verification"],
    )
    return record, ticket, result, verification, identity


def test_complete_exact_chain_authorizes_reference_progress():
    record, ticket, result, verification, identity = successful_chain()
    decision = authorize_progress_chain(
        record, ticket, result, verification, current_result_identity=identity,
    )
    assert decision.disposition == "AUTHORIZED_PROGRESS"
    assert decision.production_enforcement == "NOT_IMPLEMENTED"


def test_legacy_bridge_record_version_fails_closed():
    _, record, ticket = admission_and_ticket()
    record["record_version"] = 1
    ticket["record_version"] = 1
    with pytest.raises(BlueprintError, match="trusted_admission_required"):
        attach_task_or_queue_record(task_for(record), record)
    decision, _ = consume(ticket, ticket_bound_actual_effect(ticket))
    assert decision.reason == "invalid_ticket"


def test_result_cannot_exist_without_consumed_ticket_identity():
    _, _, ticket = admission_and_ticket()
    with pytest.raises(BlueprintError, match="consumed_ticket_required"):
        record_mutation_result(
            ticket, ticket_bound_actual_effect(ticket),
            result_identity=result_identity(ticket), mutation_status="succeeded",
            evidence_persisted=True, consumed_nonces=(),
        )


def task_for(record):
    return {
        "task_id": record["entity_id"],
        "admitted_entity_id": record["entity_id"],
        "parent_entity_refs": deepcopy(record["parent_refs"]),
        "objective_refs": deepcopy(record["objective_refs"]),
        "governance_lineage_refs": deepcopy(record["governance_lineage_refs"]),
        "admission_generation": record["admission_generation"],
    }


def test_classify_path_a_attempt_path_b_is_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["classified_write_set"][0]["path"] = "project_guardian/core.py"
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_same_path_different_operation_is_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["classified_write_set"][0]["operation"] = "delete"
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_same_action_class_different_write_set_is_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["classified_write_set"][0]["effect_digest"] = "a" * 64
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_classification_digest_tamper_is_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["classification_digest"] = "0" * 64
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_classifier_version_mismatch_fails_closed():
    proposed = effect()
    proposed["classifier_version"] = "worker-selected-version"
    with pytest.raises(BlueprintError, match="classifier_version_mismatch"):
        classify_authoritatively(proposed, trusted_classifiers=[CLASSIFIER])


def test_ticket_at_another_mutation_surface_is_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["mutation_target"]["surface"] = "live_mutation"
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_extra_file_after_ticket_issuance_is_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["classified_write_set"].append({
        "path": "project_guardian/core.py", "operation": "update",
        "effect_digest": "a" * 64, "action_classes": ["docs_only"],
    })
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_omitted_file_is_deterministically_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["classified_write_set"] = []
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_changed_staged_patch_is_blocked():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    actual["staged_patch_digest"] = "f" * 64
    decision, _ = consume(ticket, actual)
    assert decision.reason == "BLOCKED_EFFECT_MISMATCH"


def test_generated_effect_escape_is_blocked():
    with pytest.raises(BlueprintError, match="generated_effect_outside_approved_namespace"):
        classification(
            facts=("generated_runtime_code",), path="project_guardian/core.py",
            approved_namespaces=("generated",),
        )


def test_ambiguous_generated_write_set_requires_reclassification():
    with pytest.raises(BlueprintError, match="generated_effect_reclassification_required"):
        classification(
            facts=("generated_runtime_code",), path="generated/core.py",
            dynamic_mode="reclassify_after_materialization",
            approved_namespaces=("generated",),
        )


def test_task_cannot_attach_another_entity_admission():
    _, record, _ = admission_and_ticket()
    worker_task = task_for(record)
    worker_task["task_id"] = "unrelated-task"
    with pytest.raises(BlueprintError, match="task_admission_identity_mismatch"):
        attach_task_or_queue_record(worker_task, record)


def test_task_parent_admission_mismatch_is_blocked():
    _, record, _ = admission_and_ticket()
    worker_task = task_for(record)
    worker_task["parent_entity_refs"] = ["foreign-parent"]
    with pytest.raises(BlueprintError, match="task_admission_provenance_mismatch"):
        attach_task_or_queue_record(worker_task, record)


def test_progression_verification_for_different_ticket_is_blocked():
    record, ticket, result, _, identity = successful_chain()
    state = snapshot()
    ticket2 = issue_mutation_authorization_ticket(
        state, record, trusted_current_digest=snapshot_digest(state),
        trusted_admission_record_digest=ticket["admission_record_digest"],
        ticket_id="ticket:2", nonce="nonce:2",
        issued_at="2026-09-12T12:06:00Z", expires_at="2026-09-12T12:30:00Z",
        issuer_provenance=["fixture:ticket-2"],
    )
    result2 = record_mutation_result(
        ticket2, ticket_bound_actual_effect(ticket2), result_identity=identity,
        mutation_status="succeeded", evidence_persisted=True,
        consumed_nonces=consume(ticket2, ticket_bound_actual_effect(ticket2))[1],
    )
    verification2 = record_verification_evidence(
        result2, observed_result_identity=identity, verdict="PASS",
        verifier_id="verifier:vega", verifier_provenance=["fixture:verification-2"],
    )
    decision = authorize_progress_chain(
        record, ticket, result, verification2, current_result_identity=identity,
    )
    assert decision.disposition == "BLOCKED_PROVENANCE_MISMATCH"


def test_progression_verification_for_different_result_is_blocked():
    record, ticket, result, _, identity = successful_chain()
    other = result_identity(ticket, "d" * 40)
    verification = record_verification_evidence(
        result, observed_result_identity=other, verdict="PASS",
        verifier_id="verifier:vega", verifier_provenance=["fixture:wrong-result"],
    )
    decision = authorize_progress_chain(
        record, ticket, result, verification, current_result_identity=identity,
    )
    assert decision.reason == "stale_or_different_result_identity"


def test_pass_boolean_without_provenance_chain_is_insufficient():
    with pytest.raises(BlueprintError, match="verification_is_not_authorization"):
        progress_transition(
            "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION",
            "authorize_progress", provenance_chain={"passed": True},
        )


def test_provider_switch_retains_ticket_and_admission_identity():
    record, ticket, _, _, _ = successful_chain()
    context = {
        "admitted_entity_id": record["entity_id"],
        "admission_record_digest": ticket["admission_record_digest"],
        "ticket_id": ticket["ticket_id"], "nonce": ticket["nonce"],
        "classification_digest": ticket["classification_digest"],
        "write_set_digest": ticket["write_set_digest"],
        "objective_refs": ticket["objective_refs"],
        "repository_lineage_refs": ticket["repository_lineage_refs"],
        "governance_lineage_refs": ticket["governance_lineage_refs"],
        "applicable_gate_generations": ticket["applicable_gate_generations"],
        "admission_generation": ticket["admission_generation"],
        "snapshot_generation": ticket["gate_snapshot_generation"],
        "snapshot_digest": ticket["gate_snapshot_digest"],
        "provider": "cursor", "session": "one",
    }
    switched = carry_execution_context(context, provider="codex", session="two")
    for field in set(context) - {"provider", "session"}:
        assert switched[field] == context[field]


def test_restart_without_immutable_cycle_context_is_quarantined():
    with pytest.raises(BlueprintError, match="missing_execution_admission_context"):
        carry_execution_context(
            {"admitted_entity_id": "child", "provider": "cursor"},
            provider="codex", session="restart",
        )


@pytest.mark.parametrize("mutation_status", ["failed", "partial"])
def test_ticket_replay_after_failed_or_partial_mutation_is_blocked(mutation_status):
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    first, consumed = consume(ticket, actual)
    assert first.disposition == "CONSUMABLE_REFERENCE_TICKET_NOT_PRODUCTION_AUTHORITY"
    record_mutation_result(
        ticket, actual, result_identity=result_identity(ticket),
        mutation_status=mutation_status, evidence_persisted=True,
        consumed_nonces=consumed,
    )
    replay, _ = consume(ticket, actual, consumed)
    assert replay.reason == "ticket_replay"


def test_mutation_success_evidence_failure_is_not_authorized_progress():
    _, _, ticket = admission_and_ticket()
    actual = ticket_bound_actual_effect(ticket)
    _, consumed = consume(ticket, actual)
    result = record_mutation_result(
        ticket, actual, result_identity=result_identity(ticket),
        mutation_status="succeeded", evidence_persisted=False,
        consumed_nonces=consumed,
    )
    assert result["authority_state"] == "QUARANTINED_INCOMPLETE_EVIDENCE"


def test_evidence_pass_mutation_failure_is_not_authorized_progress():
    record, ticket, _, _, identity = successful_chain()
    actual = ticket_bound_actual_effect(ticket)
    _, consumed = consume(ticket, actual)
    result = record_mutation_result(
        ticket, actual, result_identity=identity,
        mutation_status="failed", evidence_persisted=True,
        consumed_nonces=consumed,
    )
    verification = record_verification_evidence(
        result, observed_result_identity=identity, verdict="PASS",
        verifier_id="verifier:vega", verifier_provenance=["fixture:false-positive"],
    )
    decision = authorize_progress_chain(
        record, ticket, result, verification, current_result_identity=identity,
    )
    assert decision.disposition == "QUARANTINED_INCOMPLETE_EVIDENCE"


def test_partial_mutation_is_not_authorized_progress():
    record, ticket, _, _, identity = successful_chain()
    actual = ticket_bound_actual_effect(ticket)
    _, consumed = consume(ticket, actual)
    result = record_mutation_result(
        ticket, actual, result_identity=identity,
        mutation_status="partial", evidence_persisted=True,
        consumed_nonces=consumed,
    )
    verification = record_verification_evidence(
        result, observed_result_identity=identity, verdict="PASS",
        verifier_id="verifier:vega", verifier_provenance=["fixture:partial"],
    )
    decision = authorize_progress_chain(
        record, ticket, result, verification, current_result_identity=identity,
    )
    assert decision.disposition == "QUARANTINED_INCOMPLETE_EVIDENCE"


def test_stale_result_identity_is_blocked():
    record, ticket, result, verification, _ = successful_chain()
    decision = authorize_progress_chain(
        record, ticket, result, verification,
        current_result_identity=result_identity(ticket, "e" * 40),
    )
    assert decision.reason == "stale_or_different_result_identity"


@pytest.mark.parametrize(
    "writer",
    ["MutationPublisher.write_text", "MetaCoder.apply_mutation", "unknown.writer"],
)
def test_unintegrated_mediated_writer_is_not_enforced(writer):
    decision = mediated_writer_status(writer)
    assert decision.disposition == "NOT_ENFORCED"


def test_issue23_stays_blocked_despite_technical_verification():
    output = classify_unmediated_output(verification_pass=True)
    assert output["authorized_progress"] is False
    assert output["state"] == "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION"


def test_issue31_unavailable_release_cannot_issue_gated_ticket():
    state = snapshot(gated=True)
    classified = classification(
        facts=("runtime_code",), objectives=["issue:23", "task:renamed-maintenance"],
    )
    record = issue_trusted_admission_record(
        state, "child", classified, trusted_mutation_target=target(),
        trusted_current_digest=snapshot_digest(state),
        trusted_classification_digest=classified["classification_digest"],
        issuance_generation=12, issued_at="2026-09-12T12:00:00Z",
        expires_at="2026-09-12T13:00:00Z", issuer=AUTHORITY_REF,
        issuer_provenance=["fixture:issuance-event"],
    )
    with pytest.raises(BlueprintError, match="blocked_pending_human_release"):
        issue_mutation_authorization_ticket(
            state, record, trusted_current_digest=snapshot_digest(state),
            trusted_admission_record_digest=bridge_record_digest(record),
            ticket_id="ticket:gated", nonce="nonce:gated",
            issued_at="2026-09-12T12:05:00Z",
            expires_at="2026-09-12T12:30:00Z",
            issuer_provenance=["fixture:ticket-event"],
        )
