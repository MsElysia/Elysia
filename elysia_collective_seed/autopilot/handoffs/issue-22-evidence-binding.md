# Issue #22 implementer handoff

Task: persist and independently accept the exact completion submission.
Worker: Codex Agent B; branch `codex/remote-fix-22-evidence-binding`.
Base: `6649b89adea44e3e7f41d37b55a7c82485beb6e6`.
State: implementation complete; independent breaker/reviewer pending.

Read: AGENTS.md, task ledger, dry-run bridge, completion validator, verifier,
lifecycle/migration/dry-run/Vega tests, CI and lifecycle contract.
Changed: task ledger and bridge, lifecycle contract, CI inclusion, fixture
upgrades, new evidence regression tests and this handoff. The six upstream
`test_vega_evidence_binding.py` tests are byte-identical to their source branch.

Validation: expanded seed/lifecycle/Vega suite 130 passed locally with existing
workspace venv Python 3.13. Original 92 passed at base (parent verification).
After security changes and before fixture upgrades, original tests had six
conflicting failures while all six unchanged issue-22 repros passed:
- dryrun stale-payload test accepted arbitrary review without proof/binding;
- dryrun completion test supplied no evidence;
- lifecycle live-owner test accepted arbitrary review without proof/binding;
- Vega validated-completion test accepted arbitrary review without proof/binding;
- bridge provenance test accepted arbitrary review without proof/binding;
- legacy identity test required self-hash to appear as sole evidence.

The four successful acceptance fixtures now independently resolve actual local
artifact bytes/check attestations bound to the exact persisted digest. Existing
lifecycle assertions remain. Two bridge fixtures now supply explicit evidence;
legacy identity asserts its digest remains identity, absent from evidence. New
negative tests preserve rejection of the unsafe old behavior. No test skip,
xfail, assertion removal, or synthetic production bypass was added.

Guarantees: atomic acceptance binds producer/attempt/policy/packet/check/evidence
snapshot and verifier claim digest; current registry and live lease remain
mandatory. Verifier notes are separate. Direct legacy unverified submissions
remain inspectable/rejectable but cannot pass acceptance without verified proof.
Legacy missing snapshots fail closed; migration preserves events.

Limits: the constructor evidence validator is explicitly trusted setup. There
is no built-in runtime proof adapter. Missing/unavailable resolver prevents
completion. A digest is integrity/identity, not proof or signature. Provider,
runtime, network, deployment and merge authority remain disabled. SQLite hostile
administrator tampering with all data/authority is outside this local integrity
contract. Execution claim admission human/dependency bypass is a separate next
repair; acceptance itself preserves those human/protected-risk boundaries.

Next role: Agent C independently reproduce/falsify exact committed candidate;
Agent D only after breaker PASS. Do not push/merge from implementer.

## Independent breaker repair (candidate 7c2a51a rejected)

Agent C found that direct submit could store a full packet contradicting the
separate envelope checks; an actual local proof resolver then validated only
the envelope. Task ID, packet ID and outcome conflicts were also reproduced.
The ledger now semantically validates every supplied full packet and requires
exact task/packet/attempt identity, completed outcome, complete check equality,
and source/evidence equality at both submit and accept. No-packet legacy direct
submission remains audit-compatible. Preexisting inconsistent snapshots fail
closed after reopen even with a valid digest and actual local attestation.

Validation after repair: 142 seed/lifecycle/evidence tests passed, including 12
additional consistency cases. No prior tests weakened. Next: independent breaker
re-run against the new exact commit, then reviewer only upon PASS.
