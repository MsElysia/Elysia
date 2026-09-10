# Issue #22 independent review

Verdict: READY_FOR_INTEGRATION_REVIEW

Reviewed implementation: 40964ee9e334d1974702e419dff28df7c87df587
Branch: codex/remote-fix-22-evidence-binding; draft PR #24.
Base: 6649b89adea44e3e7f41d37b55a7c82485beb6e6.
Reviewer: independent Agent D, detached guardian-remote-review-22 worktree.

No blocking findings in the bounded issue-22 repair.

The original defect treated packet identity as proof and allowed a verifier lease
to complete unbound producer evidence. The repair enforces acceptance in the
public SQLite ledger, including direct submissions. Canonical packet/check/
evidence/policy/producer/attempt state is bound to the review claim and explicit
expected digest. A supplied full packet must agree with its envelope. Acceptance
revalidates independent registry eligibility, required checks, authority policy,
live lease, and trusted evidence resolution in the same immediate transaction as
the durable transition and event. Supplemental references remain separate.

The default evidence authority is absent and denies completion. Its documented
constructor-installed resolver is trusted application code, not producer proof.
The local test authorities read actual artifact bytes and separately persisted
reports bound to the exact snapshot. Digests and reference spelling alone cannot
complete a task. No second runtime, provider adapter, network lookup, permission
expansion, or unrelated architecture was introduced. Additive migration preserves
legacy evidence/events; legacy submissions without snapshots cannot be accepted.

Read AGENTS.md, original issue requirements supplied by coordinator, full base-to-
head diff, implementation handoff, lifecycle contract, ledger/bridge/validator/
verifier, modified fixtures, regression suites, independent executable probes and
Agent C report. C explicitly passed this SHA with 142 required plus 12 independent
tests (154 total); prior candidate 7c2a51a failed four packet conflicts and its PASS
was not carried forward. Coordinator reports GitHub run 34538842193 passed the
same head; reviewer did not independently query GitHub because local gh is not
authenticated.

Reviewer validation at this exact SHA:

```powershell
& 'C:/Users/Owner/Project guardian/.venv/Scripts/python.exe' -m pytest -q tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_autopilot_verifier_ledger_migration.py
# 52 passed in 1.13s (Python 3.13.15)
git diff --check 6649b89 HEAD
# clean
```

The six original Vega repros retain blob
48ce7e0de67579ed916f069a688d25d462a5dd88. Existing positive fixtures now supply
required proof/binding; their lifecycle assertions remain. The self-hash evidence
assertion was corrected to the repaired invariant and backed by unchanged
negative Vega repros, rather than hidden with skips or xfails.

Remaining limitations: this is a runtime-disabled local contract, not a production
proof service. Trusted task admission/process/SQLite authority and correct resolver
installation remain prerequisites. Execution admission governance is a separate
tracked repair; this review does not claim it is fixed. Human/role/protected-risk
acceptance remains denied until its authority mechanism exists.

Next action: human integration review of PR #24 at the stated SHA. No merge,
deployment, runtime activation, or production modification performed by reviewer.
