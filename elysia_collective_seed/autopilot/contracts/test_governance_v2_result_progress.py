"""Adversarial tests for the governance-v2 reference transaction (not wiring)."""
from copy import deepcopy

import pytest

from .blueprint import (
    BlueprintError, bridge_record_digest, canonical_git_result_identity,
    classify_unmediated_output, consume_progress_token_v2,
    finalize_effect_transaction, issue_progress_token_v2, issue_verifier_claim,
    observe_effect_transaction, prepare_effect_transaction, record_verification_v2,
    ticket_bound_actual_effect, ticket_consumption_identity,
)
from .test_blueprint_repair import admission_and_ticket


PRODUCER = {"principal_id": "worker:one", "principal_generation": 1}
OBSERVER = {"principal_id": "adapter:git", "principal_generation": 2}
VERIFIER = {"principal_id": "verifier:one", "principal_generation": 3}
AUTHORITY = {"principal_id": "progress:one", "principal_generation": 4}
OBSERVED_AT = "2026-09-13T11:59:00Z"


def claim_context():
    return {"task_id": "task:A", "evidence_refs": ["evidence:tests"],
            "test_run_id": "test-run:1", "verification_generation": 1}


def control(ticket, *, generation=7, principals=None):
    principals = principals or [
        {**PRODUCER, "independence_group": "workers", "roles": ["producer"], "provenance": ["registry"]},
        {**OBSERVER, "independence_group": "adapters", "roles": ["effect_observer"], "provenance": ["registry"]},
        {**VERIFIER, "independence_group": "verification", "roles": ["verifier"], "provenance": ["registry"]},
        {**AUTHORITY, "independence_group": "governance", "roles": ["progression_authority"], "provenance": ["registry"]},
    ]
    return {
        "record_type": "BRIDGE_CONTROL_STATE", "record_version": 2,
        "governance_generation": generation, "state_generation": 1,
        "previous_state_digest": "0" * 64, "state_history": [],
        "source_refs": ["checkpoint:11#5653254076"], "principals": principals,
        "issued_ticket_identities": [ticket_consumption_identity(ticket)],
        "consumed_ticket_identities": [], "transactions": [],
        "issued_claim_ids": [], "verifier_claims": [], "consumed_claim_ids": [],
        "verification_records": [],
        "issued_progress_ids": [], "issued_progress_nonces": [], "progress_tokens": [],
        "consumed_progress_identities": [],
    }


def kw(state):
    return {"bridge_control_state": state,
            "trusted_control_state_digest": bridge_record_digest(state)}


def post(identity):
    return {key: identity[key] for key in (
        "commit_sha", "tree_sha", "repository_head_sha", "write_set_digest", "effect_digest")}


def prepared():
    _, record, ticket = admission_and_ticket()
    state = control(ticket)
    actual = ticket_bound_actual_effect(ticket)
    tx, state = prepare_effect_transaction(
        ticket, actual, transaction_id="tx:1", producer=PRODUCER,
        repository_pre_state_sha=ticket["mutation_target"]["expected_head_sha"], **kw(state))
    identity = canonical_git_result_identity(
        commit_sha="c" * 40, tree_sha="d" * 40, repository_head_sha="c" * 40,
        write_set_digest=ticket["write_set_digest"], effect_digest=bridge_record_digest(actual))
    return record, ticket, tx, identity, state


def finalized():
    record, ticket, tx, identity, state = prepared()
    tx, state = observe_effect_transaction(
        tx, observer=OBSERVER, outcome="succeeded",
        observed_pre_state_sha=tx["repository_pre_state_sha"],
        observed_post_state=post(identity), result_identity=identity, observed_at=OBSERVED_AT,
        evidence_persisted=True, **kw(state))
    result, tx, state = finalize_effect_transaction(
        tx, ticket_finalization_succeeded=True, **kw(state))
    return record, ticket, result, identity, state


def verified():
    record, ticket, result, identity, state = finalized()
    claim, state = issue_verifier_claim(
        result, claim_id="claim:1", verifier=VERIFIER, **claim_context(),
        issued_at="2026-09-13T12:00:00Z", expires_at="2026-09-13T12:10:00Z", **kw(state))
    verification, state = record_verification_v2(
        result, claim, verdict="PASS", observed_result_identity=identity,
        verified_at="2026-09-13T12:05:00Z", **kw(state))
    return record, ticket, result, verification, identity, state


def test_01_worker_report_cannot_become_trusted_result():
    _, _, _, _, state = prepared()
    with pytest.raises(BlueprintError, match="transaction_not_current"):
        finalize_effect_transaction({"transaction_id": "worker-report"},
            ticket_finalization_succeeded=True, **kw(state))


def test_02_result_observer_must_be_trusted():
    _, _, tx, identity, state = prepared()
    with pytest.raises(BlueprintError, match="untrusted_principal"):
        observe_effect_transaction(tx, observer={"principal_id": "worker:one", "principal_generation": 1},
            outcome="succeeded", observed_pre_state_sha=tx["repository_pre_state_sha"],
            observed_post_state=post(identity), result_identity=identity, observed_at=OBSERVED_AT,
            evidence_persisted=True, **kw(state))


def test_03_result_from_ticket_a_cannot_satisfy_ticket_b():
    _, _, tx, identity, state = prepared()
    forged = deepcopy(tx); forged["ticket_id"] = "ticket:B"
    with pytest.raises(BlueprintError, match="transaction_not_current_prepared"):
        observe_effect_transaction(forged, observer=OBSERVER, outcome="succeeded",
            observed_pre_state_sha=tx["repository_pre_state_sha"], observed_post_state=post(identity), result_identity=identity, observed_at=OBSERVED_AT,
            evidence_persisted=True, **kw(state))


def test_04_commit_tree_mismatch_is_blocked():
    _, _, tx, identity, state = prepared()
    observed = post(identity); observed["tree_sha"] = "e" * 40
    with pytest.raises(BlueprintError, match="commit_tree_or_effect_observation_mismatch"):
        observe_effect_transaction(tx, observer=OBSERVER, outcome="succeeded",
            observed_pre_state_sha=tx["repository_pre_state_sha"], observed_post_state=observed,
            result_identity=identity, observed_at=OBSERVED_AT, evidence_persisted=True, **kw(state))


def test_05_effect_result_digest_mismatch_is_blocked():
    _, _, tx, identity, state = prepared(); identity["effect_digest"] = "f"*64
    with pytest.raises(BlueprintError, match="effect_result_digest_mismatch"):
        observe_effect_transaction(tx, observer=OBSERVER, outcome="succeeded",
            observed_pre_state_sha=tx["repository_pre_state_sha"], observed_post_state=post(identity), result_identity=identity, observed_at=OBSERVED_AT,
            evidence_persisted=True, **kw(state))


def test_06_stale_repository_pre_state_is_blocked():
    _, _, ticket = admission_and_ticket(); state = control(ticket)
    with pytest.raises(BlueprintError, match="stale_repository_pre_state"):
        prepare_effect_transaction(ticket, ticket_bound_actual_effect(ticket), transaction_id="tx:1",
            producer=PRODUCER, repository_pre_state_sha="f"*40, **kw(state))


def test_07_concurrent_repository_mutation_invalidates_transaction():
    _, _, tx, identity, state = prepared()
    with pytest.raises(BlueprintError, match="concurrent_repository_mutation"):
        observe_effect_transaction(tx, observer=OBSERVER, outcome="succeeded",
            observed_pre_state_sha="f"*40, observed_post_state=post(identity), result_identity=identity, observed_at=OBSERVED_AT,
            evidence_persisted=True, **kw(state))


def test_08_success_without_evidence_persistence_quarantines():
    _, _, tx, identity, state = prepared()
    tx, _ = observe_effect_transaction(tx, observer=OBSERVER, outcome="succeeded",
        observed_pre_state_sha=tx["repository_pre_state_sha"], observed_post_state=post(identity), result_identity=identity, observed_at=OBSERVED_AT,
        evidence_persisted=False, **kw(state))
    assert tx["state"] == "QUARANTINED"


def test_09_evidence_persisted_finalization_failure_requires_reconciliation():
    _, _, tx, identity, state = prepared()
    tx, state = observe_effect_transaction(tx, observer=OBSERVER, outcome="succeeded",
        observed_pre_state_sha=tx["repository_pre_state_sha"], observed_post_state=post(identity), result_identity=identity, observed_at=OBSERVED_AT,
        evidence_persisted=True, **kw(state))
    _, tx, _ = finalize_effect_transaction(tx, ticket_finalization_succeeded=False, **kw(state))
    assert tx["state"] == "RECONCILIATION_REQUIRED"


def test_10_partial_mutation_quarantines():
    _, _, tx, _, state = prepared()
    tx, _ = observe_effect_transaction(tx, observer=OBSERVER, outcome="partial",
        observed_pre_state_sha=tx["repository_pre_state_sha"], observed_post_state=None, result_identity=None, observed_at=OBSERVED_AT,
        evidence_persisted=True, **kw(state))
    assert tx["state"] == "QUARANTINED"


def test_11_ambiguous_crash_cannot_auto_replay_ticket():
    _, ticket, tx, _, state = prepared()
    tx, state = observe_effect_transaction(tx, observer=OBSERVER, outcome="ambiguous",
        observed_pre_state_sha=tx["repository_pre_state_sha"], observed_post_state=None, result_identity=None, observed_at=OBSERVED_AT,
        evidence_persisted=True, **kw(state))
    assert tx["state"] == "RECONCILIATION_REQUIRED"
    with pytest.raises(BlueprintError, match="ticket_replay"):
        prepare_effect_transaction(ticket, ticket_bound_actual_effect(ticket), transaction_id="tx:2",
            producer=PRODUCER, repository_pre_state_sha=tx["repository_pre_state_sha"], **kw(state))


def test_12_producer_cannot_verify_own_result():
    _, _, result, _, state = finalized()
    principals = deepcopy(state["principals"])
    principals[0]["roles"].append("verifier")
    state["principals"] = principals
    with pytest.raises(BlueprintError, match="producer_cannot_verify"):
        issue_verifier_claim(result, claim_id="claim:self", verifier=PRODUCER, **claim_context(),
            issued_at="2026-09-13T12:00:00Z", expires_at="2026-09-13T12:10:00Z", **kw(state))


def test_13_same_independence_group_is_blocked():
    _, _, result, _, state = finalized()
    state["principals"][2]["independence_group"] = "workers"
    with pytest.raises(BlueprintError, match="verifier_not_independent"):
        issue_verifier_claim(result, claim_id="claim:group", verifier=VERIFIER, **claim_context(),
            issued_at="2026-09-13T12:00:00Z", expires_at="2026-09-13T12:10:00Z", **kw(state))


def test_14_stale_verifier_claim_is_blocked():
    _, _, result, identity, state = finalized()
    claim, state = issue_verifier_claim(result, claim_id="claim:old", verifier=VERIFIER, **claim_context(),
        issued_at="2026-09-13T12:00:00Z", expires_at="2026-09-13T12:01:00Z", **kw(state))
    with pytest.raises(BlueprintError, match="stale_verifier_claim"):
        record_verification_v2(result, claim, verdict="PASS", observed_result_identity=identity,
            verified_at="2026-09-13T12:05:00Z", **kw(state))


def test_15_pass_boolean_without_verification_record_is_insufficient():
    _, _, result, _, _, state = verified()
    with pytest.raises(BlueprintError, match="verification_record_required"):
        issue_progress_token_v2(result, {"verdict": "PASS"}, token_id="p:1", nonce="n:1",
            task_id="task:A", destination_state="AUTHORIZED_PROGRESS", authority=AUTHORITY,
            gate_snapshot_digest="a"*64, **kw(state))


def test_16_verification_for_result_a_cannot_verify_result_b():
    _, _, result, identity, state = finalized()
    claim, state = issue_verifier_claim(result, claim_id="claim:A", verifier=VERIFIER, **claim_context(),
        issued_at="2026-09-13T12:00:00Z", expires_at="2026-09-13T12:10:00Z", **kw(state))
    other = deepcopy(result)
    other["transaction_id"] = "tx:other"
    other["result_record_digest"] = bridge_record_digest(
        {key: value for key, value in other.items() if key != "result_record_digest"})
    with pytest.raises(BlueprintError, match="verification_result_mismatch"):
        record_verification_v2(other, claim, verdict="PASS", observed_result_identity=identity,
            verified_at="2026-09-13T12:05:00Z", **kw(state))


def test_17_verification_claim_replay_cannot_record_twice():
    _, _, result, identity, state = finalized()
    claim, state = issue_verifier_claim(result, claim_id="claim:once", verifier=VERIFIER, **claim_context(),
        issued_at="2026-09-13T12:00:00Z", expires_at="2026-09-13T12:10:00Z", **kw(state))
    _, state = record_verification_v2(result, claim, verdict="PASS", observed_result_identity=identity,
        verified_at="2026-09-13T12:05:00Z", **kw(state))
    with pytest.raises(BlueprintError, match="verification_claim_replay"):
        record_verification_v2(result, claim, verdict="PASS", observed_result_identity=identity,
            verified_at="2026-09-13T12:06:00Z", **kw(state))


def tokenized():
    _, _, result, verification, _, state = verified()
    token, state = issue_progress_token_v2(result, verification, token_id="p:1", nonce="n:1",
        task_id="task:A", destination_state="AUTHORIZED_PROGRESS", authority=AUTHORITY,
        gate_snapshot_digest="a"*64, **kw(state))
    return token, state


def test_18_progress_token_cannot_advance_sibling_task():
    token, state = tokenized()
    with pytest.raises(BlueprintError, match="progress_task_mismatch"):
        consume_progress_token_v2(token, task_id="task:B", destination_state="AUTHORIZED_PROGRESS",
            current_governance_generation=7, current_gate_snapshot_digest="a"*64, **kw(state))


def test_19_governance_generation_change_invalidates_progression():
    token, state = tokenized(); state["governance_generation"] = 8
    with pytest.raises(BlueprintError, match="stale_progress_governance"):
        consume_progress_token_v2(token, task_id="task:A", destination_state="AUTHORIZED_PROGRESS",
            current_governance_generation=8, current_gate_snapshot_digest="a"*64, **kw(state))


def test_20_progress_transition_is_single_consume():
    token, state = tokenized()
    decision, state = consume_progress_token_v2(token, task_id="task:A", destination_state="AUTHORIZED_PROGRESS",
        current_governance_generation=7, current_gate_snapshot_digest="a"*64, **kw(state))
    assert decision.disposition == "AUTHORIZED_PROGRESS"
    with pytest.raises(BlueprintError, match="progress_token_replay"):
        consume_progress_token_v2(token, task_id="task:A", destination_state="AUTHORIZED_PROGRESS",
            current_governance_generation=7, current_gate_snapshot_digest="a"*64, **kw(state))


def test_21_authorized_progress_does_not_imply_merge_or_deploy():
    _, _, result, verification, _, state = verified()
    with pytest.raises(BlueprintError, match="not_merge_or_deploy"):
        issue_progress_token_v2(result, verification, token_id="p:m", nonce="n:m", task_id="task:A",
            destination_state="MERGED", authority=AUTHORITY, gate_snapshot_digest="a"*64,
            trust_anchor_status="AVAILABLE", **kw(state))


def test_22_unmediated_external_result_is_evidence_not_progress():
    output = classify_unmediated_output(verification_pass=True)
    assert output["authorized_progress"] is False


def test_23_issue_23_remains_blocked_despite_technical_pass():
    _, _, result, verification, _, state = verified()
    with pytest.raises(BlueprintError, match="issue_23_human_governance_gate"):
        issue_progress_token_v2(result, verification, token_id="p:23", nonce="n:23", task_id="task:A",
            destination_state="AUTHORIZED_PROGRESS", authority=AUTHORITY, gate_snapshot_digest="a"*64,
            issue_refs=["issue:23"], **kw(state))


def test_24_unavailable_issue_31_trust_anchor_blocks_release_progression():
    _, _, result, verification, _, state = verified()
    with pytest.raises(BlueprintError, match="issue_31_trust_anchor_unresolved"):
        issue_progress_token_v2(result, verification, token_id="p:31", nonce="n:31", task_id="task:A",
            destination_state="RELEASED", authority=AUTHORITY, gate_snapshot_digest="a"*64,
            trust_anchor_status="UNRESOLVED", **kw(state))


def test_v2_transaction_receipt_and_result_carry_full_immutable_chain():
    _, ticket, result, _, state = finalized()
    tx = state["transactions"][0]
    receipt = tx["receipt"]
    for record in (tx, receipt, result):
        assert record["ticket_id"] == ticket["ticket_id"]
        assert record["ticket_state_digest"] == ticket["state_digest"]
        assert record["ticket_consumption_identity"] == ticket_consumption_identity(ticket)
        assert record["admission_record_digest"] == ticket["admission_record_digest"]
        assert record["classification_digest"] == ticket["classification_digest"]
        assert record["write_set_digest"] == ticket["write_set_digest"]
        assert record["staged_patch_digest"] == ticket["staged_patch_digest"]
        assert record["mutation_target"] == ticket["mutation_target"]
    assert receipt["observer_provenance"] == ["registry"]
    assert receipt["observed_at"] == OBSERVED_AT
    assert receipt["observation_generation"] == result["observation_generation"]


def test_verifier_must_be_independent_from_trusted_observer():
    _, _, result, _, state = finalized()
    state["principals"][2]["independence_group"] = "adapters"
    with pytest.raises(BlueprintError, match="independent_from_observer"):
        issue_verifier_claim(result, claim_id="claim:observer-group", verifier=VERIFIER,
            **claim_context(), issued_at="2026-09-13T12:00:00Z",
            expires_at="2026-09-13T12:10:00Z", **kw(state))


def test_claim_chain_substitution_is_not_current_claim():
    _, _, result, identity, state = finalized()
    claim, state = issue_verifier_claim(result, claim_id="claim:bound", verifier=VERIFIER,
        **claim_context(), issued_at="2026-09-13T12:00:00Z",
        expires_at="2026-09-13T12:10:00Z", **kw(state))
    forged = deepcopy(claim)
    forged["test_run_id"] = "test-run:substituted"
    forged["claim_digest"] = bridge_record_digest(
        {key: value for key, value in forged.items() if key != "claim_digest"})
    with pytest.raises(BlueprintError, match="trusted_verifier_claim_required"):
        record_verification_v2(result, forged, verdict="PASS",
            observed_result_identity=identity, verified_at="2026-09-13T12:05:00Z", **kw(state))


def test_verification_record_evidence_substitution_is_not_current():
    _, _, result, verification, _, state = verified()
    forged = deepcopy(verification)
    forged["evidence_refs"] = ["evidence:substituted"]
    forged["verification_digest"] = bridge_record_digest(
        {key: value for key, value in forged.items() if key != "verification_digest"})
    with pytest.raises(BlueprintError, match="verification_record_not_current"):
        issue_progress_token_v2(result, forged, token_id="p:forged", nonce="n:forged",
            task_id="task:A", destination_state="AUTHORIZED_PROGRESS", authority=AUTHORITY,
            gate_snapshot_digest="a"*64, **kw(state))


def test_progress_token_full_chain_substitution_is_not_current():
    token, state = tokenized()
    forged = deepcopy(token)
    forged["task_id"] = "task:B"
    forged["token_digest"] = bridge_record_digest(
        {key: value for key, value in forged.items() if key != "token_digest"})
    with pytest.raises(BlueprintError, match="trusted_progress_token_required"):
        consume_progress_token_v2(forged, task_id="task:B",
            destination_state="AUTHORIZED_PROGRESS", current_governance_generation=7,
            current_gate_snapshot_digest="a"*64, **kw(state))


def test_progress_requires_current_consumed_verifier_claim():
    _, _, result, verification, _, state = verified()
    state["consumed_claim_ids"] = []
    with pytest.raises(BlueprintError, match="chain_not_current_or_not_consumed"):
        issue_progress_token_v2(result, verification, token_id="p:no-claim", nonce="n:no-claim",
            task_id="task:A", destination_state="AUTHORIZED_PROGRESS", authority=AUTHORITY,
            gate_snapshot_digest="a"*64, **kw(state))


def test_progress_requires_current_finalized_transaction():
    _, _, result, verification, _, state = verified()
    state["transactions"] = []
    with pytest.raises(BlueprintError, match="finalized_transaction_required"):
        issue_progress_token_v2(result, verification, token_id="p:no-tx", nonce="n:no-tx",
            task_id="task:A", destination_state="AUTHORIZED_PROGRESS", authority=AUTHORITY,
            gate_snapshot_digest="a"*64, **kw(state))


def test_control_state_previous_digest_splice_fails_closed():
    _, _, _, _, state = prepared()
    state["previous_state_digest"] = "f" * 64
    with pytest.raises(BlueprintError, match="control_state_ancestry_discontinuous"):
        prepare_effect_transaction({}, {}, transaction_id="tx:fork", producer=PRODUCER,
            repository_pre_state_sha="f"*40, **kw(state))


def test_control_state_history_generation_fork_fails_closed():
    _, _, _, _, state = prepared()
    state["state_history"][0]["state_generation"] = 2
    with pytest.raises(BlueprintError, match="control_state_ancestry_discontinuous"):
        prepare_effect_transaction({}, {}, transaction_id="tx:fork", producer=PRODUCER,
            repository_pre_state_sha="f"*40, **kw(state))


def test_progress_token_carries_full_result_and_verification_chain():
    token, _ = tokenized()
    required = {"transaction_id", "ticket_id", "ticket_state_digest",
        "ticket_consumption_identity", "admission_record_digest", "classification_digest",
        "mutation_target", "write_set_digest", "staged_patch_digest", "actual_effect_digest",
        "effect_receipt_digest", "claim_id", "claim_digest", "verification_generation",
        "test_run_id", "evidence_refs", "verification_digest", "result_identity",
        "task_id", "destination_state", "governance_generation", "gate_snapshot_digest"}
    assert required <= set(token)
