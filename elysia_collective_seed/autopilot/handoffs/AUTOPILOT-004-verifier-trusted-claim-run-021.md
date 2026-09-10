# AUTOPILOT-004 trusted verifier-claim handoff — run 021

## Task

- Sources: issues #8, #17; draft PR #15; master control issue #11.
- Starting SHA: `a6ae745f1063a5dc80a1f073bd60174462726e35`.
- Objective: perform the final authority review requested by run 020 and repair
  any falsifiable verifier-claim bypass without enabling the runtime.

## Independent findings

Two independent reviewers reproduced that the prior public
`VerificationDecision` could be fabricated or replayed and that
`select_verifier()` trusted a spoofable producer-group argument. A first
process-local tag proposal was rejected during review because callers could
launder fabricated registry data through the signing function and because
eligibility could become stale before claim.

## Implementation

- `TaskLedger` now owns the verifier worker registry and independence-group
  mapping used for claims.
- `claim_verification()` recomputes eligibility inside the ledger transaction
  against the complete current registry. It requires the requester to be the
  deterministic selected worker and rechecks availability, independence,
  task-required capabilities, and task risk class at claim/renewal time.
- `select_verifier()` fails closed when the claimed producer group is absent
  from or disagrees with the supplied registry.
- Caller-supplied authorization decisions were removed from the authoritative
  claim API, closing fabricated and stale-decision replay paths.
- Tests now cover spoofed producer metadata, current-registry changes,
  task-specific capability/risk requirements, exhausted retry routing to
  `human_review`, protected task metadata, and persisted audit reconstruction.

The registries are trusted local orchestrator configuration, not a hostile
same-process security boundary. This remains runtime-disabled SQLite state
transition code and grants no provider, merge, deploy, external-post,
credential, private-data, or Guardian runtime authority.

## Verification

- Focused verifier/migration/lifecycle suite: 17 passed.
- CI-equivalent `python -m pytest -q elysia_collective_seed`: 43 passed.
- Compileall for implementation and test surfaces: passed.
- `git diff --check`: passed; Git emitted line-ending conversion warnings only.
- Independent adversarial review was requested after the final patch.

## Next gate

Push this isolated branch and obtain exact-head CI. Keep PR #15 draft and
unmerged until the final independent review and exact-head workflow are green.
No integration, provider activation, deployment, or protected action is
authorized by this handoff.
