# ISSUE #33 GOVERNANCE REGRESSION HANDOFF

## BASE

`0843d9cad29a632a42946a5daf4abe4d0b93bdb0` (draft PR #32 normative product).

## CANDIDATE SHA

Recorded after the implementation commit and in the separate verification
evidence. Product branch: `codex/governance-33-scope-inheritance-regression`.

## ISSUE #33 REPRODUCTION MODEL

The checked-in synthetic snapshot is grounded in read-only Git/GitHub evidence:
Issue #23 objective → official restack branch → detached base
`4ff2dc92dd7d9bc393225bce35de9239a9cad6a5` → renamed side branch
`cursor/autopilot-003-issue23-restack-cwa` → semantic product
`7374820642fad52a6264c86df8632c3a630df592`. Git confirms `7374820` is one
commit above `4ff2dc92`. PR #34 and later branches remain untouched and preserved.

The fixture also represents a sibling restack, renamed task and salami-sliced
descendants. Each derived entity carries its local friendly objective/lineage
labels while the oracle unions admitted ancestor scope before evaluating the
semantic action.

## SPEC GAP

**PARTIALLY COVERED.** PR #32 already blocks Issue #33 when complete, correctly
admitted ancestry is supplied. The first new regression run exposed one structural
gap: a derived product could delete all `parent_refs`, masquerade as a new root,
and produce `NO_MATCHING_BLOCK_NOT_AUTHORIZATION`. The schema now distinguishes
independently admitted `root` from `derived`; roots require zero parents and
derived entities require at least one. Assigning that classification remains a
trusted repository/control-plane admission responsibility, not a worker claim.

## TESTS ADDED

Twenty-two Issue #33 cases cover the exact branch/SHA chain, branch alias,
sibling, detached SHA, renamed task, salami slicing, checkpoint omission,
technical-pass/PR promotion, owner/App spoofing, Cursor/Codex/direct-Git writers,
friendly relabeling, missing or severed ancestry, exact-shaped release assertion,
and the difference between blocked and no-match-not-authorization.

## BRANCH-ALIAS RESULT

`BLOCKED_PENDING_HUMAN_RELEASE`; gate `fixture:github:MsElysia/Elysia:29`,
generation 1 remains effective.

## SIBLING RESULT

`BLOCKED_PENDING_HUMAN_RELEASE` through inherited admitted ancestor scope.

## DETACHED-SHA RESULT

`BLOCKED_PENDING_HUMAN_RELEASE` before conceptual branch creation. The detached
base's commit identity supplements, but does not replace, inherited objective.

## SALAMI-SLICING RESULT

Every descendant remains `BLOCKED_PENDING_HUMAN_RELEASE` after transitive scope
union. Renaming each partial objective or lineage does not erase parent scope.

## CHECKPOINT-OMISSION RESULT

Empty gates, unchanged-staging claims, completed implementation, passing tests,
Vega PASS, architecture READY and PR existence in checkpoint prose do not affect
the machine-state result. Owner attribution and GitHub App provenance transfer no
authority.

## EXTERNAL-WRITER RESULT

Cursor, Codex and direct Git attempts are normatively blocked, while every result
explicitly retains `external_write_enforcement=NOT_ENFORCED`. A completed gated
artifact remains unauthorized-but-preserved evidence; tests and reviews do not
retroactively authorize it.

## RELEASE-AUTHENTICITY RESULT

An exact-shaped stored release assertion remains blocked with
`release_validation=UNAVAILABLE`. No human trust anchor was invented or added.

## FULL TEST RESULT

Implementer: **350 passed** (137 contract tests plus 213 inherited tests), Python
3.13.15, pytest 9.1.1, jsonschema 4.26.0. `compileall`, JSON parse and
`git diff --check` passed. No Guardian/runtime/provider code was imported or run.

## VEGA VERDICT

Pending fresh independent verification on the committed exact candidate.

## ARCHITECTURE VERDICT

Pending separate review after Vega PASS.

## ENFORCEMENT STATUS

`NORMATIVE_CONTRACT_ONLY`

## ISSUE #23 STATUS

`GATED — NO SEMANTIC WORK AUTHORIZED`

## PR #34 STATUS

`UNAUTHORIZED_BUT_PRESERVED_EVIDENCE`

## NEXT BOUNDED TASK

After exact-SHA independent verification and architecture review, preserve those
reports separately and update the draft PR #32 review thread. Production work,
if separately authorized, must derive ancestry/classification from trusted Git
and control-plane state and evaluate the gate atomically at the write boundary.
This candidate does not implement or authorize that work.
