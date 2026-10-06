# Issue #33 v2 branch-alias regression handoff

Task: operator-requested narrow governance specification/test extension.
Worker: ChatGPT Work / Codex. Status: IMPLEMENTED_LOCAL_TESTS_PASS;
not integration approval or an independent Vega verdict.

Branch: `codex/governance-33-v2-alias-regression-20261006`.
Exact base: `5514315db40fb8f42bd7dea8fc1339d72c40a406` (draft PR #48).
Product identity is the commit containing this handoff; consult its draft PR
for the published exact SHA and subsequent hosted checks.

## Existing work reused

Read Issue #33's four current comments, related #29/#30/#31 discussions,
PR #32/#35/#38/#42/#48 metadata, Issue #40 follow-ups, and newest explicit
Issue #11 checkpoint `6004967846`. #35 already implemented the original exact
alias fixture; #38 added v2 admission/migration. The older #38 PASS is not
controlling after #40. This child uses the repaired governance lineage and
does not duplicate those implementations or change workflow triggers.

Repository reads: `AGENTS.md`, the existing Issue #33 fixture/tests, v2
admission and adversarial tests, `admission.py`, `checkpoint_reference.py`,
`GOVERNANCE_V2_ADMISSION.md`, and Autopilot CI workflow. No semantic Issue #23
files were edited, copied or invoked.

## Changed files

- `contracts/test_issue_33_v2_admission.py`: 20 regressions through the v2
  public admission boundary using the existing exact fixture; JSON reconstruction,
  four independently matching scope routes, both merge-parent orders, worker
  alias/docs/root/owner claims, and invalid/stale admission state.
- `contracts/GOVERNANCE_V2_ADMISSION.md`: precise acceptance obligations and
  scope limits for those regressions.
- This handoff under `elysia_collective_seed/autopilot/handoffs/`.

## Local verification

Python 3.12.14, pytest 9.1.1, jsonschema 4.26.0; plugin autoload disabled.
Focused command: `python -m pytest -q
elysia_collective_seed/autopilot/contracts/test_issue_33_v2_admission.py`.
Result: 20 passed.

Inherited CI-equivalent command: `python -m pytest -q elysia_collective_seed
tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py
tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py
tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py
tests/test_autopilot_evidence_binding.py tests/test_autopilot_claim_policy.py
breaker_tests/test_vega_v2_generation.py`. Result: 539 passed, including the
unchanged six-case generation breaker.
Compileall, parsing all 30 seed JSON artifacts, and diff-check passed.
Hosted exact-head CI and independent review are separate evidence and must
not be inferred from these local results or from the base's verdicts.

## Retained boundaries and remaining blockers

SPECIFICATION_AND_TEST_ONLY. Schema, evaluator, admission implementation,
ledger, workflow, and Guardian runtime remain unchanged.
`production_enforcement=NOT_IMPLEMENTED`,
`external_write_enforcement=NOT_ENFORCED`,
`human_trust_anchor=UNRESOLVED`, `release_validation=UNAVAILABLE`.
Synthetic fixture pins and authority records do not authenticate production
ancestry; JSON reconstruction is not database durability or real enforcement.

#29/#30/#31/#33 remain unreleased. Issue #23 remains gated. PR #34 product
`7374820642fad52a6264c86df8632c3a630df592` and docs descendant
`881608c83fc0ec19261924034eea6e809b4b6ede` remain unauthorized preserved
evidence. No merge, deployment, gate release, permission expansion, runtime
activation, autonomy, history rewrite or deletion is included.

Next bounded step: independent exact-SHA review of this specification/test
delta after hosted checks; do not repeat the completed #35 implementation or
interpret technical PASS as authority. Keep all PRs draft and unmerged.
Usage/credit telemetry was unavailable; no credit purchase was performed.
