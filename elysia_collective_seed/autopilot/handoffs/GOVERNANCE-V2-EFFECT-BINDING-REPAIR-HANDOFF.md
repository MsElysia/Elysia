# GOVERNANCE V2 EFFECT-BINDING REPAIR HANDOFF

## BASE

`65c7feae50633f772caec6d0cbe58de2cfba8971`

Prior evidence tip `5abd432f47694a8a69a623e9087c250f0e09a477` was inspected
but is not the product base. Earlier Vega and architecture verdicts do not
transfer.

## REPAIRED CANDIDATE SHA

Pending exact commit.

Intermediate candidate `180d17d692efd1229e29deff1b99e08916d7968b`
received fresh Vega `FAIL`: nonce-only consumption allowed cross-ticket
substitution, verifier records lacked a trusted registry, progression lacked an
authenticated decision, and task ownership was prose-only. That verdict is
preserved and does not transfer to the pending repaired candidate.

## CLASSIFIED WRITE-SET MODEL

The authoritative classifier emits a canonical nonempty list of exact effects.
Each entry binds a normalized repository-relative path, create/update/delete/
rename operation, content/effect digest and per-path action classes. Paths are
unique and deterministically sorted. Malformed, duplicate, unsorted, absolute,
backslash, dot-segment or traversal forms fail closed.

Semantic mutations prefer an exact staged patch. The exact classified write set,
not a worker description or aggregate label, is the authority scope.

## CLASSIFICATION DIGEST

SHA-256 over compact UTF-8 contract-canonical JSON binds entity/admission
generation, objective, governance lineage, target repository/ref/worktree and
base/head, normalized write set/digest, aggregate actions, classifier
ID/generation/version, patch digest, dynamic policy and evidence. The ticket ID
is excluded to avoid a cycle. Classification and admission are independently
pinned.

## TICKET EFFECT BINDING

`MUTATION_AUTHORIZATION_TICKET` now carries classification digest, complete
classified write set, write-set digest and staged-patch digest alongside its
existing identity, scope, target, gates and generations. Consumption compares an
independently derived actual effect. Any extra/omitted/changed path, operation,
content digest, patch, classifier digest, surface or target is
`BLOCKED_EFFECT_MISMATCH`.

Issuance requires authoritative ticket-ID and nonce uniqueness state. Consumption
and result receipts bind a digest of `(ticket ID, nonce, ticket state digest)`, so
consuming one ticket cannot authorize a sibling that reuses its nonce.

## DYNAMIC EFFECT HANDLING

Unknown expansion cannot weaken the ticket. Dynamic generation must occur in a
non-durable sandbox, materialize, be reclassified and receive a new exact ticket.
Approved namespaces are an additional constraint. Namespace escape blocks, and
`reclassify_after_materialization` cannot issue an execution ticket. Semantic
writes should authorize an exact staged-patch digest wherever practical.

## TASK ↔ ADMISSION BINDING

Attachment binds matching task/admitted-entity IDs, exact parent refs,
objectives, governance lineage, admission generation and admission-record digest.
A separately trusted task record also binds the complete worker-payload digest
and authoritative owner from a unique task-owner registry. A task cannot borrow
a foreign admission, reuse an attached identity or swap its semantic body.
Restart revalidates the immutable binding and quarantines missing or changed provenance.

## CYCLE CONTEXT BINDING

The immutable cycle context includes admission-record digest, entity, active
ticket ID/nonce, classification/write-set digests, objectives, repository and
governance lineage, gates, admission generation and snapshot identity. Provider,
session, retry and restart may carry this context but cannot replace it. Missing
context quarantines the cycle.

## RESULT IDENTITY

`MUTATION_RESULT` requires the ticket nonce to be consumed and binds that nonce,
ticket state, admission/classification/write-set/patch
digests, actual mutation outcome, evidence-persistence outcome, and an immutable
commit/tree/patch/changed-file identity plus repository head and write-set
digest.

## VERIFICATION PROVENANCE

`VERIFICATION_EVIDENCE` binds PASS/FAIL to the exact mutation-result digest,
ticket ID and result identity. Its verifier identity/generation/provenance must
resolve exactly once in an independently trusted verifier registry. A bare PASS
boolean, worker-authored structured verdict, completion flag or verdict for
another result has no progression authority.

## AUTHORIZED-PROGRESS CHAIN

Admission → Classification → Ticket → Effect → Result → Verification →
Progression Authorization → Authorized Progress. Every record references the
previous immutable identity. A separately trusted progression authority issues a
content-addressed decision for that exact chain. Progression revalidates the
entire chain, current result identity, and authority registry; a missing,
worker-authored, tampered, substituted or stale link is
`BLOCKED_PROVENANCE_MISMATCH`.

## MUTATE/EVIDENCE FAILURE MODEL

Tickets are single-consumption once an attempt starts. Failure, partial write or
crash cannot replay the token. Mutation success with failed receipt persistence
is `QUARANTINED_INCOMPLETE_EVIDENCE`; partial mutation is
`QUARANTINED_PARTIAL_MUTATION`; evidence claiming success for a failed mutation
cannot advance. A crash requires independent state inspection and trusted
reconciliation with a new chain. Ordinary filesystem/Git writes are not claimed
to be transactional.

## PHASE B WRITER INVENTORY

Known mediated writers are `mutation.py.apply`,
`mutation_engine._direct_apply_mutation`,
`implementer/repo_adapter.apply_patch`, `MutationPublisher.publish_mutation`
including its direct `Path.write_text` effects, and `MetaCoder.apply_mutation`.
All remain `NOT_ENFORCED`. The inventory is explicitly non-exhaustive; every
unknown or unintegrated writer remains `NOT_ENFORCED` until registered, reviewed
and directly integrated.

## PHASE A DRY-RUN DESIGN

Phase A provides only a reference/dry-run admission store, task/queue attachment,
objective/action/write-set classification, deterministic digests, ticket
lifecycle, nonce/generation high-water proofs and simulated quarantine/progression.
No live writer consumes a ticket. Phase B integrates all inventoried mediated
writers; Phase C enables full-chain authorized progress; Phase D adds repository-
side transport/ref/credential enforcement and separately authorized Issue #31
trust anchoring.

## TEST RESULTS

Implementer: **482 passed** in the required aggregate suite, including **269
governance-contract tests**, **36 effect-binding repair tests**, all 32 prior
blueprint tests and the inherited Issue #33/autopilot/Vega evidence regressions.
Python 3.13.15, pytest 9.1.1 and jsonschema 4.26.0 were used. Contract
`compileall`, AST parsing of all changed Python, all 66 repository JSON parses,
all 3 schema meta-validations and `git diff --check` passed. No Guardian runtime,
provider or mutation path was activated.

## VEGA VERDICT

Pending fresh independent exact-SHA review.

## ARCHITECTURE VERDICT

Pending separate exact-SHA review after Vega.

## CROSS-UNIVERSE ENFORCEMENT

`NOT_IMPLEMENTED`

## PRODUCTION ENFORCEMENT

`NOT_IMPLEMENTED`

All operational mutation surfaces remain `NOT_ENFORCED`.

## HUMAN TRUST ANCHOR

`UNRESOLVED`

Issue #31 release validation remains `UNAVAILABLE`.

## ISSUE #23

`GATED — NO SEMANTIC WORK AUTHORIZED`

`7374820`, `0a2d135` and PR #34 remain preserved evidence and are not modified,
promoted or authorized by this repair.

## READY FOR CURSOR RE-ATTACK?

Pending exact-SHA validation and both fresh reviews.
