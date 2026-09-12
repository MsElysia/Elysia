# GOVERNANCE V2 BLUEPRINT REPAIR HANDOFF

## BASE

`7b076548751e72879d0632c1ec687e087e43a7b8`

## REPAIRED CANDIDATE SHA

`65c7feae50633f772caec6d0cbe58de2cfba8971`

Both fresh verdicts below are bound to this exact candidate. They do not transfer
from the base or to later product changes.

## RED-TEAM INPUT

`V2_DESIGN_NEEDS_REPAIR`

Source: Cursor's independent
`docs/GOVERNANCE-V2-OPERATIONAL-RED-TEAM-REPORT-20260912.md`. The repair consumes
that reconnaissance rather than duplicating it.

## TWO-UNIVERSES FINDING

Governance schemas, evaluators, admission contracts and tests may exist on a
governance-oriented lineage while live mutation, repository adapters, task
queues, Guardian cycles and Git writes execute on an operational lineage that
does not contain or consume them. Governance availability and passing governance
tests therefore do not establish runtime protection. The universes meet only
when an authoritative operational boundary consumes a trusted admitted record
and current effective gate state before mutation.

## OPERATIONAL MUTATION SURFACES

`mutation_engine._direct_apply_mutation`, `implementer/repo_adapter`,
`self_task_queue` and `guardian_cursor_cycle` are concrete future integration and
bypass surfaces. Each remains `NOT_ENFORCED`. A future authorization attempt at
any of them must receive admitted entity identity, root/derived classification,
ancestry, governance lineage, objective, authoritative action class, applicable
gate generation, trusted snapshot generation/digest and validated human-release
evidence when required.

## CURRENT CROSS-UNIVERSE ENFORCEMENT

`NOT_IMPLEMENTED`

Existing operational output is not authorized progress merely because it exists
or passes CI, Vega or architecture review.

## REQUIRED GOVERNANCE→RUNTIME BRIDGE

The bridge must provide one authoritative admission format and one trusted
current gate snapshot; classify objective and action before mutation; preserve
ancestry and governance-lineage inheritance; fail closed on unknowns; perform an
atomic check-and-mutate transaction or equivalent fencing; prevent
worker-created roots plus branch-name, detached-SHA, adapter, queue and cycle
bypasses; persist restart-safe state; and reject generation rollback.

## FIRST FUTURE MUTATION BOUNDARY TO INTEGRATE

The smallest credible first slice is the Phase A control-plane sequence: trusted
admission issuance, claim/queue attachment, authoritative classification and a
fenced single-use authorization ticket, kept dry-run/reference-only until its
persistence and replay properties are proven. No single mutation function is a
sufficient first boundary. Live `mutation.py.apply` and
`repo_adapter.apply_patch` must consume the same ticket together in the later
mediated-write phase.

## `_direct_apply_mutation` STATUS

`PARTIAL_BOUNDARY`

Operational inspection shows it is a fallback skipped when the configured live
`mutation.py.apply` backend exists. It is absent on the governance product tip and
bypassed by `repo_adapter`, publisher/MetaCoder, queue/cycle orchestration and raw
Git/GitHub/external writers. The earlier single-first-boundary recommendation is
retracted. Runtime enforcement remains `NOT_ENFORCED`.

## COMPOSED BOUNDARY MODEL

`COMPOSED_MULTI_BOUNDARY_DESIGN`

The smallest credible future bridge spans trusted admission issuance; objective
and governance-lineage attachment; task/claim and queue attachment; authoritative
effect classification; a single-use fenced authorization ticket; mediated checks
at both the live mutation and repository-file-write paths; atomic ticket
consumption plus evidence capture; and a distinct authorized-progress transition.
Later repository-side enforcement is required for external transports.

`assess_composed_boundary_plan` rejects a direct-apply-only plan and any plan
missing live mutation, repository file write, task claim, queue/objective attach,
or authorized-progress boundaries. This is an executable normative assessment,
not proof those boundaries exist in production.

## TRUSTED ADMISSION ISSUANCE

`WORKER_PROPOSAL` is descriptive and grants nothing. The future trusted service
issues `TRUSTED_ADMISSION_RECORD`, binding entity identity, root/derived status,
parents, repository/governance lineage, inherited objectives, action classes,
applicable gate generations, trusted snapshot generation/digest, exact mutation
target, admission/issuance generations, freshness, issuer identity/provenance,
classifier evidence and required release status. Workers cannot create, refresh
or widen these fields. Classification and issued-record content must match
independently trusted current digests at the next boundary; worker-chosen pins
prove nothing. Schema validity does not authenticate the issuer.

## AUTHORITATIVE ACTION CLASSIFICATION

Classification must derive from the actual intended surface, operation and
content-derived facts where practical, under a separately trusted classifier.
Worker docs/test/refactor/maintenance labels and file extensions are ignored as
authority. Semantic/generated runtime code stays semantic; compound effects keep
all action classes. Unknown, conflicting or ambiguous facts fail closed. The pure
reference classifier models this contract but does not perform authenticated
production inspection.

## OBJECTIVE ATTACHMENT

Inherited objective references union across every admitted parent before claim or
mutation. Issue #23 cannot become constructor cleanup, bootstrap repair, lifecycle
normalization, runtime hygiene, monitoring refactor or a fresh objective through
worker relabeling. Reclassification requires a higher-generation trusted record
and evidence. Uncertain semantic equivalence fails closed or routes to human
governance; no perfect automatic semantic understanding is claimed.

## AUTHORIZATION TICKET

`MUTATION_AUTHORIZATION_TICKET` binds ticket ID/nonce, admitted entity,
objectives, repository and governance lineage, all permitted actions, exact
surface/repository/worktree/ref/base/head, gate snapshot generation/digest,
applicable gate generations, admission/issuance generations, release generations,
freshness, issuer provenance and complete-state digest. Release generations stay
empty while Issue #31 validation is unavailable.

## ATOMICITY / CAS REQUIREMENTS

The state checked must be the state mutated, or mutation fails. Consumption rejects
changed branch/ref/base/head/surface, objective, ancestry, governance lineage,
gate/snapshot/admission/issuance generation, stale digest, expired/not-yet-valid
ticket, replay, scope widening and revoked/superseded release. Workers cannot
silently refresh. Production must combine durable nonce consumption and the effect
in one transaction/CAS or equivalent generation-fenced protocol. The reference
model reserves and mutates nothing.

## TASK / QUEUE ATTACHMENT

Task and queue IDs do not imply authority. Every record attaches to an admitted
parent/lineage or receives separately trusted root admission before execution.
Admission identity/generation, inherited objective/lineage and gate state persist
through claim, retry, provider/session change and restart. Missing persisted
governance lineage is not reconstructed from worker text; it fails closed or is
quarantined.

`guardian_cursor_cycle` must preserve the same context through selection, launch,
worker execution, completion, verification and progression. Completion cannot
self-promote control-plane state.

## AUTHORIZED-PROGRESS STATE MODEL

`OBSERVED_UNTRUSTED` → `PRESERVED_EVIDENCE` → `ADMITTED` →
`AUTHORIZED_TO_EXECUTE` → `EXECUTED_PENDING_VERIFICATION` →
`VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION` → `AUTHORIZED_PROGRESS`.

Verification answers technical correctness; governance answers authorization.
One cannot substitute for the other. Commits, branches, files, packets, PRs, CI,
Vega, architecture review and worker output may exist and be preserved without
becoming authorized progress. `7374820` and `0a2d135` remain examples of useful
evidence that is not automatically promotable.

## EXTERNAL WRITER HANDLING

Raw Git CLI, GitHub API/App/CLI, Cursor/Codex shell, third-party clients, other
clones and human local Git remain `NOT_ENFORCED`. Outputs may exist, be observed,
verified and preserved, but remain quarantined from authorized progress until
trusted admission/reconciliation establishes lineage, objective, action and
current gate state. Guardian-local observation is not prevention.

## FIRST FUTURE IMPLEMENTATION SLICE

Phase A: implement a trusted admission/issuance store and task/queue attachment
contract plus authoritative classifier and fenced ticket lifecycle, while keeping
all effects dry-run/reference-only. Prove persistence, generation high-water marks,
nonce replay protection and restart behavior before any live writer consumes a
ticket. This requires separate implementation authority and is not performed here.

Phase B would then integrate the same ticket at both live `mutation.py.apply` and
`repo_adapter.apply_patch` mediated paths. Phase C would add the controlled
authorized-progress transition and effect receipts.

## SECOND FUTURE BOUNDARY

Repository-side enforcement is required for ref mutation, push, branch creation,
PR source provenance, direct API writes and credentialed external agents. Its
ruleset/App/credential strategy and the Issue #31 trust anchor require separate
human authority. No hooks, rulesets, credentials or server policy are changed.

## TEST RESULTS

Implementer: **446 passed** in the required aggregate suite, including **233
governance-contract tests** and the inherited autopilot/Vega evidence suites.
The repair-specific module contributes **32 passing tests**. Python 3.13.15,
pytest 9.1.1 and jsonschema 4.26.0 were used. Contract `compileall`, AST parsing,
all 66 repository JSON parses, all 3 schema meta-validations and
`git diff --check` passed. No Guardian runtime, provider or mutation path was
activated.

## VEGA VERDICT

`PASS` — exact SHA `65c7feae50633f772caec6d0cbe58de2cfba8971`.

The independent breaker verified 32/32 repair tests and 233/233 governance
contract tests, then exercised the specified direct-boundary, adapter, root-mint,
restart, relabel, downgrade, stale-ticket, replay, race, external-writer and
verification-laundering cases. No material specification gap was found. The
review expressly retained future CAS/nonces as unimplemented transactional
obligations and left external paths `NOT_ENFORCED`.

## ARCHITECTURE VERDICT

`READY_FOR_INTEGRATION_REVIEW` — exact SHA
`65c7feae50633f772caec6d0cbe58de2cfba8971`.

The separate post-Vega reviewer found a coherent composed path from admission
through controlled progression, with honest limitations: no issuer
authentication, persistent nonce/generation store, atomic mutation integration,
operational bridge, repository policy or human trust anchor exists yet.

## CROSS-UNIVERSE ENFORCEMENT

`NOT_IMPLEMENTED`

## PRODUCTION ENFORCEMENT

`NOT_IMPLEMENTED`

All cited runtime paths remain `NOT_ENFORCED`.

## HUMAN TRUST ANCHOR

`UNRESOLVED`

Release validation remains `UNAVAILABLE`; release assertions stay
non-authoritative until Issue #31 is separately resolved.

## ISSUE #23

`GATED — NO SEMANTIC WORK AUTHORIZED`

PR #34, `7374820` and `0a2d135` remain preserved evidence only and are not
advanced or promoted by this repair.

## NEXT AUTHORITY REQUIRED

Separate human authority is required before implementing Phase A storage, any
production write guard, TaskLedger/runtime semantic change, repository rule,
credential mediation, hook, Issue #31 trust anchor, gate release, Issue #23 work,
PR #34 promotion, merge, deployment or provider/runtime activation.
