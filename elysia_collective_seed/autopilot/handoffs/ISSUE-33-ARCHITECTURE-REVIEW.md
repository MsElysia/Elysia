# Issue #33 Independent Architecture Review

## Verdict

**READY_FOR_INTEGRATION_REVIEW**

This verdict is bound to exact candidate
`9ad2d941269650b231d3f3e4f5327266a66f9cb1` on
`codex/governance-33-scope-inheritance-regression`, based on
`0843d9cad29a632a42946a5daf4abe4d0b93bdb0`.

Review scope: **NORMATIVE_CONTRACT_ONLY**.

## Architecture assessment

The contract binds gate evaluation to the union of admitted objective, lineage,
and explicit gate references across the complete parent graph. Branch and task
names are ordinary local references; changing them cannot subtract inherited
scope. The iterative graph evaluation is transitive, validates disconnected
records as well as the proposal path, detects missing parents and cycles, and
handles deep subdivision without a recursion-depth dependency.

The added `ancestry_kind` field closes the representational gap that previously
made an empty `parent_refs` list ambiguous. A `root` must have no parents and a
`derived` entity must have at least one parent. The JSON Schema conditional is
correct under the enclosing required field and enum: a valid `root` reaches the
zero-parent branch, while a valid `derived` reaches the nonempty-parent branch.
Missing or invalid classifications fail schema validation.

This field does not authenticate admission, and the candidate does not claim
that it does. A caller-controlled snapshot could still relabel a derived entity
as a root. The normative README and oracle contract correctly assign root versus
derived classification, ancestry, proposal classification, and current-snapshot
selection to a trusted repository/control-plane admission boundary. Thus the
change closes the structural ambiguity without inventing a worker-proof admission
system. Production admission remains a required future control.

Stale, incomplete, malformed, cyclic, duplicate, or unpinned state fails closed.
Checkpoint prose is ignored, so omission of a gate, passing tests, review status,
PR existence, owner attribution, or automation attribution cannot weaken the
machine snapshot. A schema-valid release assertion remains ineffective because
release validation is explicitly `UNAVAILABLE`; no human trust anchor is
invented.

Every decision reports `external_write_enforcement=NOT_ENFORCED`. The oracle can
produce a normative `BLOCKED_PENDING_HUMAN_RELEASE` result for Cursor, Codex, or
direct Git activity, but it does not imply interception of those transports.
Likewise, `NO_MATCHING_BLOCK_NOT_AUTHORIZATION` explicitly preserves the need for
other authority checks and is never an allow decision.

The Issue #33 fixture properly treats `7374820` as admitted historical evidence
inside the gated ancestry graph. It does not classify that product as authorized:
all relevant semantic and external-write evaluations remain
`BLOCKED_PENDING_HUMAN_RELEASE`, and the handoff labels PR #34 and `7374820`
`UNAUTHORIZED_BUT_PRESERVED_EVIDENCE`.

## Compatibility and migration

The model is compatible with a future durable ledger/write guard because it uses
stable gate IDs and generations, explicit ancestry, deterministic full-snapshot
evaluation, and a caller-supplied trusted digest. Durable storage must still make
admission and revision selection authoritative, preserve prior generations,
prevent rollback, and evaluate atomically at the mutation boundary.

Adding required `ancestry_kind` while retaining `schema_version: 1` is a breaking
change for any snapshot serialized against the base draft: such snapshots now
fail closed until classified and rewritten. This is acceptable for the current
unintegrated normative draft, for which no production persistence is claimed,
but integration must treat it as an explicit migration requirement. If version 1
has already become an interoperability commitment outside this branch, the
integrator should either bump the schema version or define a trusted migration;
silently inferring roots from empty parents would recreate the ambiguity this
change removes.

## Independent verification

- Read the repository agent contract, complete base-to-candidate diff, schema,
  evaluator, Issue #33 fixture/tests, candidate handoff, and independent Vega
  report and breaker tests.
- Re-ran candidate contract tests together with the independent breaker suite:
  **161 passed** (137 candidate contract cases and 24 independent cases).
- Python byte-compilation passed.
- Base-to-candidate `git diff --check` passed.
- Candidate worktree remained clean at the exact SHA.

## Explicit limitations

- Trusted repository/control-plane admission and immutable root/derived
  classification are not implemented.
- Durable ledger storage, migration, rollback protection, and atomic write-guard
  consumption are not implemented.
- Guardian, scheduler, provider, Git, and external-agent enforcement are not
  connected.
- Human release authentication remains unavailable.
- This review does not authorize Issue #23 semantic work, PR #34 advancement,
  merge, deployment, gate release, or production enforcement.

Issue #23 remains **GATED — NO SEMANTIC WORK AUTHORIZED**. PR #34 and `7374820`
remain **UNAUTHORIZED_BUT_PRESERVED_EVIDENCE**.
