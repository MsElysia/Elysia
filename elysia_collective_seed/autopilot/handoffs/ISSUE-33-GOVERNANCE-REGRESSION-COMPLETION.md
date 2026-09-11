# ISSUE #33 GOVERNANCE REGRESSION HANDOFF — COMPLETION

## BASE

`0843d9cad29a632a42946a5daf4abe4d0b93bdb0` (draft PR #32 normative product).

## CANDIDATE SHA

`9ad2d941269650b231d3f3e4f5327266a66f9cb1` on
`codex/governance-33-scope-inheritance-regression`.

## ISSUE #33 REPRODUCTION MODEL

Checked-in synthetic state models the admitted path Issue #23 → official restack
→ detached `4ff2dc92` → `cursor/autopilot-003-issue23-restack-cwa` → semantic
product `7374820`. Read-only Git inspection independently confirmed that
`7374820` is exactly one commit above `4ff2dc92`. PR #34 and the historical
commits were not modified, promoted, reconciled or deleted.

## SPEC GAP

`PARTIALLY_COVERED`. PR #32 already rejected Issue #33 with correct admitted
ancestry. The new regression found and repaired a structural ambiguity: a derived
entity could omit every parent and masquerade as a root. Required `ancestry_kind`
now distinguishes admitted roots from derived nodes; schema validation requires
zero parents for roots and at least one for derived nodes. Trusted assignment of
this field is still an external, unimplemented authority boundary.

## TESTS ADDED

Twenty-two product regressions plus twenty-four independently authored breaker
cases cover exact lineage, aliases, sibling branches, detached-SHA rebinding,
renamed tasks, a 1,200-level salami chain, checkpoint omission, owner/App spoof,
external transports, malformed/unknown classification, ancestry severing,
unverified release and no-match-not-authorization behavior.

## RESULTS

- Branch alias: `BLOCKED_PENDING_HUMAN_RELEASE`.
- Sibling: `BLOCKED_PENDING_HUMAN_RELEASE`.
- Detached SHA: `BLOCKED_PENDING_HUMAN_RELEASE` before conceptual branch write.
- Salami slicing: all descendants retain the exact effective gate.
- Checkpoint omission/technical PASS/PR existence: no authority transfer.
- External writer: normatively blocked; `external_write_enforcement=NOT_ENFORCED`.
- Release authenticity: `release_validation=UNAVAILABLE`; assertion stays blocked.
- No match: `NO_MATCHING_BLOCK_NOT_AUTHORIZATION`, never an allow decision.

## FULL TEST RESULT

Implementer required suite: **350 passed** (137 contract + 213 inherited).
Independent Vega required suite: **350 passed**. Candidate plus independent suite:
**161 passed** (137 + 24). Architecture reviewer independently reran the same
161 tests. Compileall, all contract JSON parsing and diff checks passed. Candidate
worktree remained clean at the exact SHA. No Guardian/runtime/provider code ran.

## VEGA VERDICT

`PASS` for exact `9ad2d941...`, limited to the normative contract. See
`ISSUE-33-INDEPENDENT-VEGA.md` and independently authored
`breaker_tests/test_issue33_vega_breaker.py`.

## ARCHITECTURE VERDICT

`READY_FOR_INTEGRATION_REVIEW` for exact `9ad2d941...`, scope
`NORMATIVE_CONTRACT_ONLY`. See `ISSUE-33-ARCHITECTURE-REVIEW.md`.

## ENFORCEMENT STATUS

`NORMATIVE_CONTRACT_ONLY`

## ISSUE #23 STATUS

`GATED — NO SEMANTIC WORK AUTHORIZED`

## PR #34 STATUS

`UNAUTHORIZED_BUT_PRESERVED_EVIDENCE`

## REMAINING LIMITS

Root/derived classification, objective/action admission, state completeness and
pin selection require a trusted repository/control-plane service. Durable ledger
history, generation rollback protection, atomic mutation enforcement, Git/external
writer interception and human authentication remain unimplemented. A validly
shaped self-declared unrelated root can still produce a no-match diagnostic if a
future admission service trusts the worker; production must not do so.

Required `ancestry_kind` is a breaking draft-schema change while schema version
remains 1. The product is pre-production and unintegrated, but integration must
either bump the schema version or perform an explicit trusted migration. Inferring
root from an empty parent list would recreate the repaired bypass.

## NEXT BOUNDED TASK

Integration review of this stacked normative regression. Then, only under
separate authority, design the trusted repository ancestry/objective/action
admission record and schema migration/versioning plan. Any production write guard
must evaluate admitted classification plus effective gates atomically and receive
fresh independent verification. This work does not authorize implementing it.

## GOVERNANCE

No merge, deployment, gate release, PR #34 advancement, Issue #23 semantic change,
runtime/provider activation, permission expansion, private-data access, force
push or history deletion occurred. Passing tests do not authorize gated work.
