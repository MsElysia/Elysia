from dataclasses import replace

from elysia_collective_seed.autopilot.contracts.authenticated_sources import (
    AuthenticationReceipt, EligibilityReceipt, HistoryEntry, HistorySnapshot,
    resolve_admission_sources,
)

SHA = "a" * 40
NOW = 100


def valid_sources():
    auth = AuthenticationReceipt("vega", "oidc", "event:1", "issuer:auth", 90, 110)
    elig = EligibilityReceipt("vega", "verifier", "c1", SHA, 7, "grant:1", "issuer:policy", 110)
    hist = HistorySnapshot("history:1", 7, (
        HistoryEntry(1, "s1", "d1", SHA, "c1", "vega", 7),
    ))
    return auth, elig, hist


def resolve(auth=None, elig=None, hist=None, **scope):
    a, e, h = valid_sources()
    return resolve_admission_sources(
        a if auth is None else auth,
        e if elig is None else elig,
        h if hist is None else hist,
        product_sha=scope.get("product_sha", SHA),
        contract=scope.get("contract", "c1"),
        policy_generation=scope.get("policy_generation", 7),
        now_epoch_s=scope.get("now_epoch_s", NOW),
    )


def test_valid_snapshot_binds_exact_scope():
    result = resolve()
    assert result.accepted is True
    assert result.reason == "sources_bound"
    assert result.snapshot.product_sha == SHA


def test_github_identity_is_not_authentication():
    a, _, _ = valid_sources()
    result = resolve(auth=replace(a, method="github-app"))
    assert (result.accepted, result.reason) == (False, "github_identity_is_not_authentication")


def test_expired_and_future_authentication_fail_closed():
    a, _, _ = valid_sources()
    assert resolve(auth=replace(a, expires_at_epoch_s=NOW)).reason == "expired_authentication"
    assert resolve(auth=replace(a, authenticated_at_epoch_s=NOW + 1)).reason == "future_authentication"


def test_eligibility_must_bind_principal_role_scope_generation_and_expiry():
    a, e, _ = valid_sources()
    cases = [
        (replace(e, principal_id="other"), "principal_or_role_mismatch"),
        (replace(e, role="owner"), "principal_or_role_mismatch"),
        (replace(e, contract="other"), "eligibility_scope_mismatch"),
        (replace(e, product_sha="b" * 40), "eligibility_scope_mismatch"),
        (replace(e, policy_generation=6), "stale_policy_generation"),
        (replace(e, expires_at_epoch_s=NOW), "expired_eligibility"),
    ]
    for candidate, reason in cases:
        result = resolve(auth=a, elig=candidate)
        assert (result.accepted, result.reason) == (False, reason)


def test_history_must_be_tuple_scoped_and_append_only():
    _, _, h = valid_sources()
    assert resolve(hist=HistorySnapshot("h", 7, list(h.entries))).reason == "malformed_history_snapshot"
    wrong = replace(h.entries[0], contract="other")
    assert resolve(hist=replace(h, entries=(wrong,))).reason == "history_scope_mismatch"
    later = replace(h.entries[0], sequence=1, submission_id="s2")
    assert resolve(hist=replace(h, entries=(h.entries[0], later))).reason == "non_append_only_history"


def test_hostile_typed_fields_fail_before_comparison():
    class HostileStr(str):
        def __eq__(self, other):
            raise RuntimeError("comparison executed")
        def strip(self, *args, **kwargs):
            return self
    a, e, h = valid_sources()
    hostile_auth = replace(a, principal_id=HostileStr("vega"))
    hostile_elig = replace(e, contract=HostileStr("c1"))
    hostile_entry = replace(h.entries[0], submission_id=HostileStr("s1"))
    for result in (
        resolve(auth=hostile_auth),
        resolve(elig=hostile_elig),
        resolve(hist=replace(h, entries=(hostile_entry,))),
    ):
        assert result.accepted is False
        assert result.reason.startswith("malformed_")


def test_raw_or_subclassed_source_objects_are_rejected():
    class AuthSubclass(AuthenticationReceipt):
        pass
    a, _, _ = valid_sources()
    sub = AuthSubclass(a.principal_id, a.method, a.event_ref, a.issuer_ref,
                       a.authenticated_at_epoch_s, a.expires_at_epoch_s)
    assert resolve(auth={"principal_id": "vega"}).reason == "untrusted_authentication_source"
    assert resolve(auth=sub).reason == "untrusted_authentication_source"


def test_expected_scope_rejects_bool_generation_and_nonexact_sha():
    assert resolve(policy_generation=True).reason == "invalid_expected_scope"
    assert resolve(product_sha="a" * 39).reason == "invalid_expected_scope"
