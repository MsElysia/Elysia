# Governance checkpoint contract handoff — 2026-09-11

## TASK SELECTED

Implement a normative, executable checkpoint-consumption contract for GitHub
Issues #30/#31 under #29's still-active governance gate. Local-only candidate;
publishing and issue/PR comments require the user's external-posting approval.

## WHY THIS TASK

The newest explicit master checkpoint limits safe work to isolated governance
schema/spec/tests. Existing local uncommitted governance ledger work must not be
duplicated. The missing complementary surface is portable checkpoint admission,
particularly omission, inherited scope, and forged owner-attributed release.

## DURABLE START STATE

Read GitHub Issue #11 comment `5636666687`, newest explicit CURRENT ENGINEERING
CHECKPOINT, plus later Supervisor comments `5638883363` and `5639606219`, latest
#29/#30/#31 contracts and verifier comments, #23 Vega/restack handoffs, relevant
draft PR metadata, remote heads, local task/worktree status, and AGENTS.md.
Git fetch succeeded; gh was unauthenticated, so read-only connector calls were
used for GitHub metadata. No token files were read.

Current checkpoint source:
https://github.com/MsElysia/Elysia/issues/11#issuecomment-5636666687

## SOURCE BRANCHES / SHAS

- Base/PR25: `codex/remote-fix-8-claim-policy` at
  `e67deaa0d7a321d261a3ad7f64ee9991e19a469a`.
- PR26: `cursor/reconcile-22-evidence-risk-gates` at
  `3ac32d1f3f90a27788553e7c5aebc7baf779e438`; divergent, not reconciled here.
- Common ancestor of those heads: `40964ee9e334d1974702e419dff28df7c87df587`.
- Frozen #23 restack: `d791084e716dfcfdaa686374276611ebc0e2a0e6`.
- PR27 descriptor: `79b6c6456eae1d6a400c8b08516a8478d769d25e`.
- PR3 seed: `f7c1a4465ce7fed55b78f8d8eecb68de932cccaf`.
- Previously verified CWA product per checkpoint:
  `776647f80f7d08810f1655c7a2b02fe597c385af`; no verdict transfer.

Uncommitted local ledger work was discovered at
`C:/Users/Owner/guardian-remote-fix-29` on base `e67deaa...`, despite GitHub having
no published governance branch. Its governance.py, TaskLedger/bridge/schema/CI
edits and tests were inspected read-only and preserved. A separate analyst
confirmed the complementary scope. The main shared checkout also contains
uncommitted runtime/documentation work and was preserved.

## FAILURE OR GAP

Prose checkpoint recency does not enforce active gates. Owner-attributed App
comments do not establish a human release. No portable, executable snapshot
contract previously specified these distinctions.

## AUTHORITY BOUNDARY

Production must enforce independently admitted scope and trusted durable gate
state atomically at claim/write. This candidate supplies only a diagnostic
contract oracle and strict snapshot schema. It does not implement that service,
change runtime or ledger behavior, or add a release resolver.

## BYPASS ANALYSIS

Attack checkpoint omission/conflict, renamed/multi-parent children, task slicing,
objective-only/lineage-only matches, missing gates/parents, cycles, malformed
fields, duplicate identities, stale or modified snapshots, release generation
replay, broadened scope, app-as-owner and automation-writable proof assertions.
All release validation remains UNAVAILABLE. External writes remain NOT_ENFORCED.
Snapshot source/pin authenticity, admission completeness/classification, and
atomic freshness at mutation are explicit unimplemented trust boundaries.

## IMPLEMENTATION

Add a JSON Schema plus pure reference oracle. Compare a proposed admitted entity
and known action against pinned complete machine state, union ancestor scope,
and compute exact effective gate IDs/generations before using any prose. Invalid
state blocks; active and unverified-released gates both remain effective. No
oracle outcome grants permission. File roundtrip tests model portable state only.

## FILES CHANGED

- `elysia_collective_seed/autopilot/contracts/checkpoint_snapshot.schema.json`
- `elysia_collective_seed/autopilot/contracts/checkpoint_reference.py`
- `elysia_collective_seed/autopilot/contracts/test_checkpoint_contract.py`
- `elysia_collective_seed/autopilot/contracts/__init__.py`
- `elysia_collective_seed/autopilot/contracts/README.md`
- `.github/workflows/elysia-autopilot-ci.yml`: install jsonschema 4.x; exact
  isolated branch push trigger. Existing seed test discovery includes new tests.
- This handoff.

## TESTS

Implementer run: 115 new contract tests; 328 total passed on Python 3.13.15,
pytest 9.1.1, jsonschema 4.26.0. `git diff --check` passed. Local dependencies
installed in this isolated worktree's ignored .venv; no runtime activated.

Required suite:
`python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_autopilot_claim_policy.py --tb=short`

CI is configured, not executed on GitHub because the candidate is unpublished.
The implementer test result is not an independent PASS.

## INDEPENDENT VERIFICATION

Pending a fresh breaker on the exact committed candidate. Must independently
read the diff, test the required suite, search adjacent bypasses, and distinguish
normative oracle semantics from production persistence/authentication/enforcement.

## EXACT PRODUCT SHA

To be recorded in separate exact-candidate independent evidence after commit.
Branch: `codex/governance-checkpoint-contract`.
Worktree: `C:/Users/Owner/guardian-governance-checkpoint-contract`.

## ARCHITECTURE REVIEW

Pending a separate reviewer after independent tests pass.

## LINEAGE / SUPERSESSION EFFECT

No existing implementation, branch, or PASS is superseded. No port between
PR25/PR26/runtime/CWA lineages. This is complementary to unpublished local
governance work and must not be treated as the production interlock.

## REMAINING RISKS

Human trust-anchor selection, real ledger restart/concurrency enforcement,
checkpoint source authenticity/completeness, and external Codex/Cursor/Git
write enforcement remain open. Fixtures do not create authoritative gate IDs.
Release is unconditionally unavailable; no new permissions or credentials.

## HUMAN GOVERNANCE

NONE for this isolated normative contract/test implementation.
HUMAN_GOVERNANCE_REQUIRED remains active for #23 semantic work, release trust
anchor selection, integration/merge/deployment, and external posting/publishing.

## NEXT SMALLEST TASK

After independent verification/review, publish this exact contract candidate
only with user approval. Then reconcile the unpublished local ledger's portable
snapshot export with this contract, preserving deny-only release semantics;
require fresh exact-SHA verification before claiming production enforcement.
