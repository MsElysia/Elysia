"""Falsification tests for the composed bridge blueprint, never live enforcement."""
from copy import deepcopy

import pytest

from .blueprint import (
    BlueprintError,
    COMPOSED_MEDIATED_BOUNDARIES,
    assess_composed_boundary_plan,
    attach_task_or_queue_record,
    bridge_record_digest,
    carry_execution_context,
    classify_authoritatively,
    classify_unmediated_output,
    consume_mutation_authorization_ticket,
    issue_mutation_authorization_ticket,
    issue_trusted_admission_record,
    progress_transition,
    restore_task_or_queue_attachment,
    ticket_bound_actual_effect,
    ticket_current_state,
)
from .checkpoint_reference import snapshot_digest


AUTHORITY = {
    "authority_id": "repository-admission-service",
    "authority_kind": "trusted_repository_control_plane",
    "authority_generation": 5,
    "source_refs": ["fixture:authority-registry"],
}
AUTHORITY_REF = {
    "authority_id": AUTHORITY["authority_id"],
    "authority_generation": AUTHORITY["authority_generation"],
}
CLASSIFIER = {
    "classifier_id": "trusted-effect-classifier",
    "classifier_generation": 2,
    "classifier_version": "effect-classifier-v2",
    "provenance": ["fixture:classifier-registry"],
}
ALL_ACTIONS = [
    "static_read", "test_only", "docs_only", "schema_spec_write",
    "semantic_code_write", "repo_write", "integration", "merge", "deploy",
    "external_write", "permission_change", "private_data_access",
]
BLOCKED_ACTIONS = [
    "semantic_code_write", "repo_write", "integration", "merge", "deploy",
    "external_write", "permission_change", "private_data_access",
]


def snapshot(*, gated=False):
    objective = "issue:23" if gated else "issue:999"
    governance = "governance:23" if gated else "governance:999"
    gate_refs = ["gate:23"] if gated else []
    gates = []
    if gated:
        gates.append({
            "gate_id": "gate:23", "generation": 4,
            "kind": "human_governance_required", "state": "active",
            "scope": {"objective_refs": [objective], "lineage_refs": [governance]},
            "inherit_to_children": True, "blocked_actions": BLOCKED_ACTIONS[:],
            "reason": "human release required", "source_refs": ["issue:29"],
            "release": None,
        })
    return {
        "schema_version": 2,
        "snapshot_generation": 10,
        "source_refs": ["fixture:current-state"],
        "admission_authorities": [deepcopy(AUTHORITY)],
        "gates": gates,
        "admissions": [
            {
                "entity_id": "root", "entity_kind": "objective",
                "ancestry_kind": "root", "parent_refs": [],
                "repository_lineage_refs": ["commit:root"],
                "governance_lineage_refs": [governance],
                "objective_refs": [objective], "action_classes": ALL_ACTIONS[:],
                "admission_generation": 8, "admitted_by": deepcopy(AUTHORITY_REF),
                "admission_source": ["fixture:trusted-admission"],
                "admission_evidence": ["fixture:root-proof"],
                "admitted_at": "2026-09-12T10:00:00Z",
                "governance_gate_refs": gate_refs,
            },
            {
                "entity_id": "child", "entity_kind": "task",
                "ancestry_kind": "derived", "parent_refs": ["root"],
                "repository_lineage_refs": ["commit:unrelated-git-port"],
                "governance_lineage_refs": ["port:semantic-copy"],
                "objective_refs": ["task:renamed-maintenance"],
                "action_classes": ALL_ACTIONS[:],
                "admission_generation": 9, "admitted_by": deepcopy(AUTHORITY_REF),
                "admission_source": ["fixture:trusted-admission"],
                "admission_evidence": ["fixture:port-review"],
                "admitted_at": "2026-09-12T10:01:00Z",
                "governance_gate_refs": [],
            },
        ],
        "migration_provenance": None,
    }


def effect(*, facts=("documentation_text",), objectives=None,
           surface="repository_file_write", ambiguous_action=False,
           ambiguous_objective=False, path="docs/design.md", operation="update",
           dynamic_mode="exact_staged_patch", approved_namespaces=()):
    action_map = {
        "documentation_text": "docs_only", "test_code": "test_only",
        "schema_contract": "schema_spec_write", "runtime_code": "semantic_code_write",
        "generated_runtime_code": "semantic_code_write",
        "repository_ref_update": "repo_write", "integration_change": "integration",
        "merge_operation": "merge", "deploy_operation": "deploy",
        "external_effect": "external_write", "permission_change": "permission_change",
        "private_data_access": "private_data_access", "static_read": "static_read",
    }
    objective_values = list(objectives or ["issue:999", "task:renamed-maintenance"])
    governance_root = "governance:23" if "issue:23" in objective_values else "governance:999"
    return {
        "classifier_id": CLASSIFIER["classifier_id"],
        "classifier_generation": CLASSIFIER["classifier_generation"],
        "classifier_version": CLASSIFIER["classifier_version"],
        "classifier_provenance": deepcopy(CLASSIFIER["provenance"]),
        "admitted_entity_id": "child",
        "admission_generation": 9,
        "objective_refs": objective_values,
        "governance_lineage_refs": [governance_root, "port:semantic-copy"],
        "content_facts": list(facts),
        "classified_write_set": [{
            "path": path, "operation": operation, "effect_digest": "d" * 64,
            "action_classes": sorted({action_map.get(fact, "unknown") for fact in facts}),
        }],
        "staged_patch_digest": "e" * 64,
        "dynamic_effect_policy": {
            "mode": dynamic_mode, "approved_namespaces": list(approved_namespaces),
        },
        "mutation_target": target(surface),
        "ambiguous_action": ambiguous_action,
        "ambiguous_objective": ambiguous_objective,
        "evidence_refs": ["fixture:trusted-content-inspection"],
    }


def target(surface="repository_file_write"):
    return {
        "surface": surface,
        "repository": "MsElysia/Elysia",
        "worktree": "worktree:isolated",
        "ref": "refs/heads/candidate",
        "expected_base_sha": "a" * 40,
        "expected_head_sha": "b" * 40,
    }


def classification(**kwargs):
    return classify_authoritatively(
        effect(**kwargs), trusted_classifiers=[CLASSIFIER],
        worker_proposal={"action": "docs_only", "objective": "worker:new-root"},
    )


def admission_and_ticket(*, facts=("documentation_text",), surface="repository_file_write"):
    state = snapshot()
    classified = classification(facts=facts, surface=surface)
    record = issue_trusted_admission_record(
        state, "child", classified,
        trusted_mutation_target=target(surface),
        trusted_current_digest=snapshot_digest(state),
        trusted_classification_digest=classified["classification_digest"],
        issuance_generation=12,
        issued_at="2026-09-12T12:00:00Z",
        expires_at="2026-09-12T13:00:00Z",
        issuer=AUTHORITY_REF,
        issuer_provenance=["fixture:issuance-event"],
    )
    ticket = issue_mutation_authorization_ticket(
        state, record,
        trusted_current_digest=snapshot_digest(state),
        trusted_admission_record_digest=bridge_record_digest(record),
        ticket_id="ticket:1", nonce="nonce:1",
        issued_at="2026-09-12T12:05:00Z",
        expires_at="2026-09-12T12:30:00Z",
        issuer_provenance=["fixture:ticket-event"],
    )
    return state, record, ticket


def consume(ticket, current=None, *, actions=None, consumed=()):
    return consume_mutation_authorization_ticket(
        ticket, current or ticket_current_state(ticket),
        requested_actions=actions or ticket["action_classes"],
        current_time="2026-09-12T12:10:00Z",
        actual_effect=ticket_bound_actual_effect(ticket),
        consumed_nonces=consumed,
    )


def test_direct_apply_guard_alone_is_partial_and_insufficient():
    result = assess_composed_boundary_plan(["mutation_engine._direct_apply_mutation"])
    assert result.disposition == "INCOMPLETE_NOT_ENFORCED"
    assert "live_mutation" in result.reason
    assert result.production_enforcement == "NOT_IMPLEMENTED"


def test_repo_adapter_needs_its_own_mediated_boundary():
    plan = COMPOSED_MEDIATED_BOUNDARIES - {"repository_file_write"}
    result = assess_composed_boundary_plan(plan)
    assert result.disposition == "INCOMPLETE_NOT_ENFORCED"
    assert result.reason == "missing:repository_file_write"
    complete = assess_composed_boundary_plan(COMPOSED_MEDIATED_BOUNDARIES)
    assert complete.disposition == "COMPOSED_MULTI_BOUNDARY_DESIGN"
    assert complete.cross_universe_enforcement == "NOT_IMPLEMENTED"


def test_task_or_queue_root_minting_requires_trusted_admission():
    fake = {"task_id": "st_worker_minted", "ancestry_kind": "root", "objective": "new"}
    with pytest.raises(BlueprintError, match="trusted_admission_required"):
        attach_task_or_queue_record(fake, fake)


@pytest.mark.parametrize(
    ("facts", "worker_label", "expected"),
    [
        (("runtime_code",), "docs_only", ["semantic_code_write"]),
        (("generated_runtime_code",), "maintenance", ["semantic_code_write"]),
        (("test_code", "runtime_code"), "test_only", ["semantic_code_write", "test_only"]),
        (("documentation_text", "runtime_code"), "refactor", ["docs_only", "semantic_code_write"]),
    ],
)
def test_worker_action_labels_cannot_downgrade_observed_effects(facts, worker_label, expected):
    result = classify_authoritatively(
        effect(facts=facts, path="docs/friendly.md"),
        trusted_classifiers=[CLASSIFIER],
        worker_proposal={"action": worker_label},
    )
    assert result["action_classes"] == expected


def test_file_extension_cannot_replace_content_classification():
    with pytest.raises(BlueprintError, match="ambiguous_classification"):
        classification(facts=("unknown_content",), path="docs/apparently-safe.md")


def test_worker_objective_name_cannot_replace_trusted_objective_attachment():
    result = classify_authoritatively(
        effect(), trusted_classifiers=[CLASSIFIER],
        worker_proposal={"objective_refs": ["constructor-cleanup"]},
    )
    assert result["objective_refs"] == ["issue:999", "task:renamed-maintenance"]
    state = snapshot(gated=True)
    mismatched = classification(objectives=["constructor-cleanup"])
    with pytest.raises(BlueprintError, match="objective_attachment_mismatch"):
        issue_trusted_admission_record(
            state, "child", mismatched,
            trusted_mutation_target=target(),
            trusted_current_digest=snapshot_digest(state),
            trusted_classification_digest=mismatched["classification_digest"],
            issuance_generation=12, issued_at="2026-09-12T12:00:00Z",
            expires_at="2026-09-12T13:00:00Z", issuer=AUTHORITY_REF,
            issuer_provenance=["fixture:issuance-event"],
        )


def test_classification_and_admission_records_require_independent_current_pins():
    state = snapshot()
    classified = classification()
    trusted_classification_digest = classified["classification_digest"]
    classified["action_classes"] = ["semantic_code_write"]
    with pytest.raises(BlueprintError, match="classification_not_current_or_not_pinned"):
        issue_trusted_admission_record(
            state, "child", classified,
            trusted_mutation_target=target(),
            trusted_current_digest=snapshot_digest(state),
            trusted_classification_digest=trusted_classification_digest,
            issuance_generation=12, issued_at="2026-09-12T12:00:00Z",
            expires_at="2026-09-12T13:00:00Z", issuer=AUTHORITY_REF,
            issuer_provenance=["fixture:issuance-event"],
        )

    _, record, _ = admission_and_ticket()
    trusted_admission_digest = bridge_record_digest(record)
    record["objective_refs"] = ["objective:worker-rewrite"]
    with pytest.raises(BlueprintError, match="admission_record_not_current_or_not_pinned"):
        issue_mutation_authorization_ticket(
            state, record, trusted_current_digest=snapshot_digest(state),
            trusted_admission_record_digest=trusted_admission_digest,
            ticket_id="ticket:forged", nonce="nonce:forged",
            issued_at="2026-09-12T12:05:00Z",
            expires_at="2026-09-12T12:30:00Z",
            issuer_provenance=["fixture:ticket-event"],
        )


def test_ticket_is_stale_after_exact_applicable_gate_generation_change():
    state = snapshot(gated=True)
    classified = classification(
        objectives=["issue:23", "task:renamed-maintenance"],
        facts=("documentation_text",),
    )
    record = issue_trusted_admission_record(
        state, "child", classified,
        trusted_mutation_target=target(),
        trusted_current_digest=snapshot_digest(state),
        trusted_classification_digest=classified["classification_digest"],
        issuance_generation=12, issued_at="2026-09-12T12:00:00Z",
        expires_at="2026-09-12T13:00:00Z", issuer=AUTHORITY_REF,
        issuer_provenance=["fixture:issuance-event"],
    )
    ticket = issue_mutation_authorization_ticket(
        state, record, trusted_current_digest=snapshot_digest(state),
        trusted_admission_record_digest=bridge_record_digest(record),
        ticket_id="ticket:docs", nonce="nonce:docs",
        issued_at="2026-09-12T12:05:00Z",
        expires_at="2026-09-12T12:30:00Z",
        issuer_provenance=["fixture:ticket-event"],
    )
    current = ticket_current_state(ticket)
    current["applicable_gate_generations"][0]["generation"] = 5
    decision, _ = consume(ticket, current)
    assert decision.reason == "gate_generation_changed"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda current: current.update(snapshot_generation=11), "gate_generation_changed"),
        (lambda current: current["mutation_target"].update(expected_head_sha="c" * 40), "mutation_target_or_head_changed"),
        (lambda current: current.update(admission_generation=99), "admission_generation_changed"),
        (lambda current: current.update(objective_refs=["objective:renamed"]), "objective_changed"),
        (lambda current: current.update(governance_lineage_refs=["lineage:severed"]), "governance_lineage_changed"),
        (lambda current: current["mutation_target"].update(surface="live_mutation"), "mutation_target_or_head_changed"),
        (lambda current: current.update(snapshot_digest="0" * 64), "snapshot_stale"),
        (lambda current: current.update(release_generations=[1]), "human_release_revoked_or_superseded"),
    ],
)
def test_ticket_rejects_changed_checked_state(mutation, reason):
    _, _, ticket = admission_and_ticket()
    current = ticket_current_state(ticket)
    mutation(current)
    decision, _ = consume(ticket, current)
    assert decision.disposition == "REJECTED_NOT_AUTHORIZED"
    assert decision.reason == reason


def test_ticket_replay_fails():
    _, _, ticket = admission_and_ticket()
    decision, consumed = consume(ticket)
    assert decision.disposition == "CONSUMABLE_REFERENCE_TICKET_NOT_PRODUCTION_AUTHORITY"
    replay, same = consume(ticket, consumed=consumed)
    assert replay.reason == "ticket_replay"
    assert same == consumed


def test_ticket_scope_cannot_widen_and_claim_does_not_imply_merge_or_deploy():
    _, _, ticket = admission_and_ticket(facts=("repository_ref_update",), surface="task_claim")
    assert ticket["action_classes"] == ["repo_write"]
    for action in ("merge", "deploy"):
        decision, _ = consume(ticket, actions=[action])
        assert decision.reason == "ticket_scope_exceeded"


def test_expired_ticket_fails_without_worker_refresh():
    _, _, ticket = admission_and_ticket()
    decision, _ = consume_mutation_authorization_ticket(
        ticket, ticket_current_state(ticket), requested_actions=ticket["action_classes"],
        current_time="2026-09-12T12:30:00Z",
        actual_effect=ticket_bound_actual_effect(ticket), consumed_nonces=(),
    )
    assert decision.reason == "ticket_expired_or_not_yet_valid"


def test_verification_pass_does_not_create_authorized_progress():
    state = progress_transition("PRESERVED_EVIDENCE", "verify_pass")
    assert state == "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION"
    with pytest.raises(BlueprintError, match="verification_is_not_authorization"):
        progress_transition(state, "authorize_progress")


def test_unauthorized_commit_can_be_preserved_without_promotion():
    state = progress_transition("OBSERVED_UNTRUSTED", "preserve")
    assert state == "PRESERVED_EVIDENCE"
    state = progress_transition(state, "verify_pass")
    assert state == "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION"
    assert state != "AUTHORIZED_PROGRESS"


def test_external_writer_remains_not_enforced_even_after_verification():
    output = classify_unmediated_output(verification_pass=True)
    assert output == {
        "state": "VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION",
        "external_write_enforcement": "NOT_ENFORCED",
        "authorized_progress": False,
    }


def test_restart_missing_lineage_fails_closed_to_quarantine():
    restored = restore_task_or_queue_attachment({
        "worker_proposal": {"task_id": "st_reload", "objective": "maintenance"}
    })
    assert restored.disposition == "QUARANTINED_MISSING_TRUSTED_LINEAGE"


def test_provider_or_session_switch_preserves_admitted_identity():
    _, record, ticket = admission_and_ticket()
    context = {
        "admitted_entity_id": record["entity_id"],
        "admission_record_digest": ticket["admission_record_digest"],
        "ticket_id": ticket["ticket_id"],
        "nonce": ticket["nonce"],
        "classification_digest": ticket["classification_digest"],
        "write_set_digest": ticket["write_set_digest"],
        "objective_refs": record["objective_refs"],
        "repository_lineage_refs": record["repository_lineage_refs"],
        "governance_lineage_refs": record["governance_lineage_refs"],
        "applicable_gate_generations": record["applicable_gate_generations"],
        "admission_generation": record["admission_generation"],
        "snapshot_generation": record["trusted_snapshot_generation"],
        "snapshot_digest": record["trusted_snapshot_digest"],
        "provider": "cursor", "session": "old",
    }
    switched = carry_execution_context(context, provider="codex", session="new")
    for field in set(context) - {"provider", "session"}:
        assert switched[field] == context[field]


def test_semantic_port_with_unrelated_git_ancestry_retains_governance_lineage():
    state = snapshot(gated=True)
    classified = classification(
        facts=("runtime_code",),
        objectives=["issue:23", "task:renamed-maintenance"],
    )
    record = issue_trusted_admission_record(
        state, "child", classified,
        trusted_mutation_target=target(),
        trusted_current_digest=snapshot_digest(state),
        trusted_classification_digest=classified["classification_digest"],
        issuance_generation=12, issued_at="2026-09-12T12:00:00Z",
        expires_at="2026-09-12T13:00:00Z", issuer=AUTHORITY_REF,
        issuer_provenance=["fixture:issuance-event"],
    )
    assert "commit:unrelated-git-port" in record["repository_lineage_refs"]
    assert "governance:23" in record["governance_lineage_refs"]
    assert record["applicable_gate_generations"] == [{"gate_id": "gate:23", "generation": 4}]


@pytest.mark.parametrize("field", ["ambiguous_action", "ambiguous_objective"])
def test_ambiguous_action_or_objective_classification_fails_closed(field):
    kwargs = {field: True}
    with pytest.raises(BlueprintError, match="ambiguous_classification"):
        classification(**kwargs)


def test_task_split_inherits_parent_objective_lineage_and_gate():
    state = snapshot(gated=True)
    classified = classification(
        facts=("runtime_code",),
        objectives=["issue:23", "task:renamed-maintenance"],
    )
    record = issue_trusted_admission_record(
        state, "child", classified,
        trusted_mutation_target=target(),
        trusted_current_digest=snapshot_digest(state),
        trusted_classification_digest=classified["classification_digest"],
        issuance_generation=12, issued_at="2026-09-12T12:00:00Z",
        expires_at="2026-09-12T13:00:00Z", issuer=AUTHORITY_REF,
        issuer_provenance=["fixture:issuance-event"],
    )
    assert record["objective_refs"] == ["issue:23", "task:renamed-maintenance"]
    assert record["applicable_gate_generations"] == [{"gate_id": "gate:23", "generation": 4}]


def test_issue31_unavailable_release_blocks_ticket_issuance():
    state = snapshot(gated=True)
    state["gates"][0]["state"] = "released"
    state["gates"][0]["release"] = {
        "gate_id": "gate:23", "generation": 4,
        "scope": deepcopy(state["gates"][0]["scope"]),
        "actions": BLOCKED_ACTIONS[:], "asserted_human": "owner",
        "transport": "github-app", "application": "connector",
        "evidence_refs": ["fixture:automation-writable"],
    }
    classified = classification(
        facts=("runtime_code",),
        objectives=["issue:23", "task:renamed-maintenance"],
    )
    record = issue_trusted_admission_record(
        state, "child", classified,
        trusted_mutation_target=target(),
        trusted_current_digest=snapshot_digest(state),
        trusted_classification_digest=classified["classification_digest"],
        issuance_generation=12, issued_at="2026-09-12T12:00:00Z",
        expires_at="2026-09-12T13:00:00Z", issuer=AUTHORITY_REF,
        issuer_provenance=["fixture:issuance-event"],
    )
    assert record["release_validation"] == "UNAVAILABLE"
    with pytest.raises(BlueprintError, match="blocked_pending_human_release"):
        issue_mutation_authorization_ticket(
            state, record, trusted_current_digest=snapshot_digest(state),
            trusted_admission_record_digest=bridge_record_digest(record),
            ticket_id="ticket:gated", nonce="nonce:gated",
            issued_at="2026-09-12T12:05:00Z",
            expires_at="2026-09-12T12:30:00Z",
            issuer_provenance=["fixture:ticket-event"],
        )
