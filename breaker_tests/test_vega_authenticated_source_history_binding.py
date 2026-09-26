from dataclasses import replace

from elysia_collective_seed.autopilot.contracts.authenticated_sources import (
    AuthenticationReceipt,
    EligibilityReceipt,
    HistoryEntry,
    HistorySnapshot,
    resolve_admission_sources,
)


SHA = "a" * 40


def _resolve(entries):
    return resolve_admission_sources(
        AuthenticationReceipt("vega", "oidc", "event:1", "issuer:auth", 90, 110),
        EligibilityReceipt(
            "vega", "verifier", "c1", SHA, 7, "grant:1", "issuer:policy", 110
        ),
        HistorySnapshot("history:1", 7, tuple(entries)),
        product_sha=SHA,
        contract="c1",
        policy_generation=7,
        now_epoch_s=100,
    )


def test_history_principal_must_match_authenticated_eligible_principal():
    forged = HistoryEntry(1, "s1", "d1", SHA, "c1", "attacker", 7)

    result = _resolve((forged,))

    assert result.accepted is False
    assert result.snapshot is None


def test_same_submission_cannot_replay_with_a_different_decision_reference():
    first = HistoryEntry(1, "s1", "decision:accepted", SHA, "c1", "vega", 7)
    conflicting = replace(first, sequence=2, decision_ref="decision:rejected")

    result = _resolve((first, conflicting))

    assert result.accepted is False
    assert result.snapshot is None
