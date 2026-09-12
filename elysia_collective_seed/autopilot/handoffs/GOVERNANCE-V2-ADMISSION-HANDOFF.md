# GOVERNANCE V2 ADMISSION HANDOFF — FINAL

## BASE SHA

`9ad2d941269650b231d3f3e4f5327266a66f9cb1` (draft PR #35 product).

## EXACT CANDIDATE SHA

`7b076548751e72879d0632c1ec687e087e43a7b8`

All test and review verdicts below are bound to this exact immutable product SHA.
This final handoff is a later evidence-only commit and is not part of that product.

## BRANCH

Product: `codex/governance-v2-trusted-admission` (pushed at the exact candidate).

Final evidence: `codex/governance-v2-trusted-admission-final-evidence`.

## SCHEMA VERSION

`2`. Only exact integer version 2 is accepted as current. Missing, boolean,
string, v1, older, and forward versions fail closed at the v2 boundary. V1 is
accepted solely as exact legacy input to the explicit trusted migration model.

## CHANGE TYPE

`NORMATIVE_SPECIFICATION_AND_EXECUTABLE_CONTRACT_ONLY`

The candidate contains schema, a pure reference evaluator/migration model,
fixtures, tests, documentation and this handoff's pre-review form. It does not
authenticate an authority, mutate runtime state, intercept Git/GitHub, or grant
permission. Cross-universe scenarios and the future bridge remain specification
requirements rather than executable production enforcement.

## TWO-UNIVERSE MODEL

The **GOVERNANCE UNIVERSE** contains schemas, the checkpoint evaluator, trusted
admission model, gate inheritance, migration/versioning and tests.

The **OPERATIONAL UNIVERSE** contains runtime mutation paths, repository adapters,
task queues, Guardian cycles, local Git, external GitHub writes and external
agents. Those paths may exist on lineages that do not contain or import the
governance implementation.

Normative invariant:

> Governance state existing somewhere in repository history does not mean an operational mutation path is governed.

No semantic or durable mutation may derive authority from that existence. A
future authoritative mutation boundary must consume a trusted admitted record
and current effective gate state before mutation. Passing governance tests or
producing operational output does not establish authorization.

## MUTATION SURFACES

Every listed surface requires all nine trusted inputs before future authorization:

1. admitted entity identity;
2. explicit root/derived classification;
3. ancestry;
4. governance lineage;
5. objective;
6. action class;
7. applicable gate generation;
8. trusted current snapshot/generation;
9. authenticated human-release evidence when required.

### `mutation_engine._direct_apply_mutation`

Status: `NOT_ENFORCED`.

The nine inputs must bind an admitted mutation request and its parent task to the
exact target checkout/content generation and semantic or durable effect. Current
effective gates and generation-scoped release evidence must be consumed at the
apply boundary. Direct invocation cannot omit ancestry or create a root.

Remaining bypasses after integrating only this point: `implementer/repo_adapter`,
`self_task_queue`, `guardian_cursor_cycle`, raw local Git, external GitHub/API
writes, other clones/agents, and any write that does not converge on this method.

### `implementer/repo_adapter`

Status: `NOT_ENFORCED`.

The nine inputs must bind the implementing task and mutation request to the exact
repository, target state and local/external destination. Objective and governance
lineage must survive ports, restacks, branch changes and detached SHAs. Every
applicable semantic, repo-write, integration, merge and external-write action
must be classified against current inherited gates.

Remaining bypasses: direct adapter calls, raw Git/GitHub writers, mutation paths
outside the adapter, queue/cycle execution, retries and separately credentialed
agents. A protected caller or wrapper alone does not cover this surface.

### `self_task_queue`

Status: `NOT_ENFORCED`.

The nine inputs must bind every queue entry and durable queue operation to its
producer and full ancestry, then persist the admission identity/generation across
enqueue, update, retry, dequeue and execution. Eventual effects must be classified
under inherited objectives and current gates must be reread at execution/retry.

Remaining bypasses: direct queue-file changes, queue-created root/task identities,
stale enqueue-time snapshots, resumed/retried work, downstream adapter/Git writes,
and operational paths that never use this queue.

### `guardian_cursor_cycle`

Status: `NOT_ENFORCED`.

The nine inputs must bind the cycle and every derived child operation to its
originating task, inputs and exact output targets. Ancestry and governance lineage
must persist across worker and restart boundaries; dispatch, durable cycle state
and downstream semantic/repository/external effects require their own applicable
action classifications and current-gate checks.

Remaining bypasses: direct script/output writes, resumed cycles, child workers,
downstream queue/adapter/Git calls, external agents and successful output presented
as authority. A successful cycle is neither admission nor human release evidence.

## FIRST RECOMMENDED INTEGRATION BOUNDARY

`mutation_engine._direct_apply_mutation`

## WHY THIS BOUNDARY FIRST

The preserved Cursor admission-boundary map identifies it as a concrete local
semantic-write operation that can apply directly when the live backend is absent.
It is a small, high-leverage place to bind one exact effect and target generation
to one trusted admitted record and current effective gate snapshot. Integration
must first confirm actual caller and transaction coverage; this recommendation
does not assert that all writes converge there.

## WHAT IT DOES NOT COVER

Integrating only `_direct_apply_mutation` would not cover `implementer/repo_adapter`,
`self_task_queue`, `guardian_cursor_cycle`, other MutationEngine routes, direct
filesystem edits, raw commits/ref updates/pushes, GitHub App/API/CLI writes, other
clones, separately credentialed workers, deploy/release paths, or downstream
effects that occur after the guarded call. Every uncovered path remains
`NOT_ENFORCED` until direct exact-boundary evidence proves otherwise.

## V1 → V2 MIGRATION STATUS

`EXECUTABLE_NORMATIVE_MODEL_VALIDATED`; production migration is `NOT_IMPLEMENTED`.

The migration accepts only a schema-valid exact v1 snapshot with an independently
pinned source digest, explicit v1→v2 manifest, strictly increasing target
generation, independently configured trusted migration authority, one decision
per entity, exact parent/objective/gate preservation, repository-lineage
preservation, nonempty governance lineage, explicit root evidence and durable
provenance. It maps actions conservatively, adds all consequential v2 actions,
and leaves release assertions ineffective. It is pure and deterministic; durable
transactional persistence, concurrency protection and authentication remain future
bridge obligations.

## ROOT ADMISSION STATUS

`EXECUTABLE_NORMATIVE_MODEL_VALIDATED`; production trust is `NOT_IMPLEMENTED`.

Root is a privileged explicit classification by a registered trusted authority at
an exact generation with source/evidence/time. Empty parents, a new task/branch,
provider/session, detached SHA or new objective label never implies root. Derived
admissions require admitted parents. Authority records are normative data rather
than proof that a human or control plane is authenticated.

## OBJECTIVE ADMISSION STATUS

`EXECUTABLE_NORMATIVE_MODEL_VALIDATED`; production classification is
`NOT_IMPLEMENTED`.

Trusted objective references union through every parent. Worker proposals cannot
replace them. Expansion/reclassification requires a higher-generation trusted
admission with evidence; ambiguous semantic equivalence fails closed.

## ACTION ADMISSION STATUS

`EXECUTABLE_NORMATIVE_MODEL_VALIDATED`; production classification is
`NOT_IMPLEMENTED`.

The v2 admission stores authoritative action classes. The requested action must
be admitted, consequential classes remain gated, worker labels cannot downgrade
semantic work to tests/docs, and no-match is explicitly not authorization.

## CROSS-UNIVERSE ENFORCEMENT

`NOT_IMPLEMENTED`

The specification includes future acceptance scenarios for a gated governance
lineage and an operational lineage without an authoritative bridge. Expected path
classification is `NOT_ENFORCED`; any output remains unauthorized evidence even
if operational and governance tests pass. These scenarios are
`DOCUMENTATION_VALIDATED`, not production integration tests.

## PRODUCTION ENFORCEMENT

`NOT_IMPLEMENTED`

No enforcement was added to the four mutation surfaces, TaskLedger production
writes, hooks, GitHub Apps, Guardian runtime, providers, deployment, local Git or
external GitHub writes.

## HUMAN TRUST ANCHOR

`UNRESOLVED`

Release validation remains `UNAVAILABLE`. Actor strings, owner association,
automation-writable evidence and worker assertions cannot authenticate a human
release. Required release remains blocking until a separately authorized trust
anchor exists and binds human identity, gate ID/generation, objective/lineage,
actions, scope and provenance.

## TESTS

Exact candidate `7b076548751e72879d0632c1ec687e087e43a7b8`, Windows,
Python 3.13.15, pytest 9.1.1, jsonschema 4.26.0:

- Required governance plus inherited suite: **414 passed**.
- Governance contract/checkpoint/Issue #33/v2 migration/adversarial suite:
  **201 passed**.
- Independent Vega rerun of the 201-test scoped suite: **201 passed**.
- All **65** repository JSON files parsed; v1 and v2 schemas passed Draft 2020-12
  meta-schema validation.
- Contract Python compiled; independent AST/JSON parse passed.
- Candidate diff check passed; worktree was clean; product and remote branch SHAs
  matched.

Result: `EXECUTABLE_CONTRACT_VALIDATED` for the pure normative model and
`DOCUMENTATION_VALIDATED` for future bridge/cross-universe requirements. No test
claims production enforcement or authorization.

## VEGA VERDICT

`PASS` — exact-SHA-bound to
`7b076548751e72879d0632c1ec687e087e43a7b8`.

Vega found no place where worker-controlled fields, disconnected governance
history, successful tests or unbridged output becomes authority. It confirmed
all four surfaces are `NOT_ENFORCED`, cross-universe enforcement is
`NOT_IMPLEMENTED`, external writes are `NOT_ENFORCED`, and release validation is
`UNAVAILABLE`. This verdict does not transfer to a changed product SHA.

## ARCHITECTURE VERDICT

`READY_FOR_INTEGRATION_REVIEW` — exact-SHA-bound to
`7b076548751e72879d0632c1ec687e087e43a7b8`.

The separate review found the v2 model internally coherent: version evolution is
explicit; root/derived, objective/action and lineage authority boundaries are
clear; Git ancestry and governance lineage are distinct; the two-universe gap is
truthful; `_direct_apply_mutation` is recommendation only; bypasses remain explicit;
the future bridge requires fail-closed classification, trusted current state,
generation fencing and atomic check+mutation or equivalent protection. It grants
no runtime coverage, trust anchor, release or Issue #23 authority.

## ISSUE #23

`GATED — NO SEMANTIC WORK AUTHORIZED`

## PR #34

`UNAUTHORIZED_BUT_PRESERVED_EVIDENCE`

Neither technical correctness, CI, Vega nor architecture review promotes it.

## CURSOR 0a2d135

`TECHNICALLY_VERIFIED_BUT_NOT_AUTHORIZED_FOR_PROMOTION`

Its sibling/disconnected Git lineage does not erase the Issue #23 governance
lineage or supply human release.

## NEXT BOUNDED TASK

Prepare an integration-review packet for the normative v2 candidate and decide,
under separate authority, whether to design the first dry-run bridge around
`mutation_engine._direct_apply_mutation`. Before implementation, prove caller and
transaction coverage and define the #31 human trust anchor plus the write-plane
strategy. Any bridge implementation, Issue #23 semantic work, PR #34/`0a2d135`
promotion, gate release, merge, deploy, credential/permission change, hook install,
provider/runtime activation or external-write enforcement requires separate
authority and is not performed by this finalization.
