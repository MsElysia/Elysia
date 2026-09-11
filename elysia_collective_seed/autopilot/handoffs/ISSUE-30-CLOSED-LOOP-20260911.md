# Completed local engineering cycle: checkpoint governance contract

Task: normative schema, executable checkpoint-consumption contract, and
falsification tests for GitHub #30/#31 under the active #29 gate.

**Exact product SHA:** `0843d9cad29a632a42946a5daf4abe4d0b93bdb0`.
Product branch: `codex/governance-checkpoint-contract`.
Product base: `e67deaa0d7a321d261a3ad7f64ee9991e19a469a` (PR25).
Evidence branch: `codex/governance-checkpoint-evidence`.

## Result

- Independent verification: **PASS** for this exact normative product only.
- Required suite: **328 passed**, including 115 new contract tests.
- Independent falsification: **47 passed**, including 480 generated DAG
  comparisons, deep ancestry, stale pins, missing state, and released-state spoof.
- Separate architecture review: **READY_FOR_INTEGRATION_REVIEW**, limited to
  this normative candidate; reviewer independently reran **115 passing tests**.
- Product worktree remained clean and unchanged throughout both reviews.
- Local Python 3.13.15; GitHub Python 3.12 CI is configured but has not run.

The implementer did not certify itself. Reports and the independently authored
tests are preserved on the evidence branch. Evidence commits are not new product
verification targets and receive no inferred PASS. The reports identify the
exact product tested. The earlier implementation handoff's pending sections are
resolved by this record, without rewriting the frozen product commit.

## What changed and why

A strict complete-snapshot schema and pure diagnostic oracle now specify gate
carry-forward before checkpoint prose. Ancestor objective/lineage/gate references
are unioned; malformed or stale state blocks; asserted releases remain effective
because human release validation is unavailable. No comparison grants authority.
CI installs jsonschema 4.x and discovers the new contract tests.

This complements the existing unpublished local ledger implementation, which
was inspected but not modified. It adds no duplicate ledger or registry, no
runtime/#23 semantic changes, no human resolver or credential mechanism, and no
claim that direct external Git writers are controlled.

For the complete initial engineering map, source branch inventory, boundary,
bypass analysis, changed files and required test command, see
[implementation handoff](ISSUE-30-CHECKPOINT-CONTRACT-20260911.md).

## Durable evidence

- [Independent verification](ISSUE-30-INDEPENDENT-VERIFICATION.md)
- [Independent architecture review](ISSUE-30-ARCHITECTURE-REVIEW.md)
- Independent executable tests: repository `breaker_tests/test_independent_checkpoint.py`.
  SHA-256 of preserved file:
  `80624bf164263d2ee9a461ae9bbd9a3582c0ad2b1adcf88d3f50127162de7593`.
- [Remote state refresh](ISSUE-30-REMOTE-REFRESH-20260911.md)
- [Prepared draft PR](ISSUE-30-DRAFT-PR.md)

After the cycle began, new #11 checkpoint `5639976542` reported Cursor's
`7374820...` CWA candidate while omitting gate carry-forward. #29 still had no
release, and official staging remained `d791084...`. The observation is preserved
without treating omission/recency as authority or duplicating Cursor's work.

## Remaining risks and next smallest task

Issues #29/#30/#31 remain open. Production gate storage, source authenticity,
complete admission/classification, atomic freshness through mutation, human
trust, and external write enforcement are not delivered by a normative oracle.
JSON roundtrips are not SQLite restart or concurrent mutation verification.

The next engineering task is a bounded mapping/invariant design between the local
ledger and this contract, before implementing an exporter or runtime wiring:

1. Resolve stable gate identity versus the ledger's new ID per generation.
2. Preserve multi-parent objective/lineage scope without invented placeholders.
3. Export all applicable gates and asserted releases; do not wrap the ledger's
   latest-unreleased-only query and thereby erase effective gates.
4. Keep the existing configurable resolver and stored release claims untrusted
   until the separate human trust-anchor decision and revalidation design.
5. Define atomic snapshot/admission/mutation and actual external write boundaries.

Preserve both source candidates, union relevant adversarial tests, and require
fresh verification of any implementation/reconciliation SHA. No original
branch, implementation, history, or existing verdict is superseded here.

## Human governance

**NONE** for the completed isolated local specification/test/review cycle.
**HUMAN_GOVERNANCE_REQUIRED** remains for #23 gated semantics, release trust
selection, merge/deployment and other protected actions. User approval is needed
to publish the prepared branches/draft PR because the attached request reserves
external posting for approval. No remote push, PR, issue comment, merge, deployment,
provider activation, gate release, permission expansion or history deletion was
performed by this cycle.
