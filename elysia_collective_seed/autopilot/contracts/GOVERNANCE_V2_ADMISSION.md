# Governance snapshot v2 and trusted admission contract

Status: `SPECIFICATION_AND_TEST_ONLY`. This document and its executable reference
model define proof obligations for a future service. They do not authenticate an
authority, read GitHub, intercept Git, mutate TaskLedger, or permit an action.

## Version strategy

Snapshot v2 is a breaking replacement for the draft v1 shape. A consumer accepts
only integer `schema_version: 2`; missing, boolean, string, older, and forward
versions fail closed. `snapshot_generation` is a monotonically increasing state
generation. A consumer with a previously trusted generation rejects a lower one.
The complete snapshot digest must be pinned by an independently trusted current
state source; hashes supplied alongside worker-controlled content prove nothing.

V1 is supported only as explicit migration input. No runtime consumer treats v1
as v2. In particular, `parents=[]` never implies root status.

## Trusted admission record

`admissions` is separate from the proposed worker payload. Each record binds:

- stable entity ID and kind;
- explicitly admitted root or derived status;
- parent IDs;
- repository lineage references (Git facts such as branch/SHA/parents);
- governance lineage references (semantic ports/restacks across Git history);
- objective references;
- one or more authoritative action classes;
- admission generation, authority ID/generation, source, evidence and time;
- explicitly inherited gate references.

The authority must resolve to the snapshot's independently configured admission
authority registry at the exact generation. Schema-valid authority strings are
still only a normative representation. A production service must authenticate
and control that registry outside worker credentials.

`evaluate_admitted` accepts entity/action classification from the future trusted
admission boundary and ignores descriptive `worker_proposal` metadata. The action
must be present in the stored admission. A worker cannot downgrade
`semantic_code_write` to `test_only` or replace the objective, ancestry, or root
status in its proposal. Missing, contradictory, or unknown admission data blocks.

The snapshot admission is durable identity/classification state. The separate
per-attempt `TRUSTED_ADMISSION_RECORD` in `governance_bridge.schema.json` binds
that state to a concrete mutation target, current snapshot digest/generation,
applicable gate generations, issuance generation, freshness window, issuer
identity/provenance, and trusted classification evidence. It is not constructed
from a worker proposal. Both classifier output and the issued admission record
must match independently trusted current digests at the next boundary; a digest
chosen by the worker proves nothing. Schema validity still does not authenticate
its issuer.

## Root admission

Root creation is privileged classification. It requires a record admitted by a
known trusted control-plane authority and evidence that establishes an objective
root. Zero parents, a new branch/task/session/provider, a detached checkout, or a
new objective string is insufficient. Derived records require existing parents.
Ambiguity remains blocked until trusted review produces a new admission record.

The normative model cannot prove that its configured authority is actually
trusted. Production must keep authority configuration outside worker control.

## Objective and action classification

Objectives are durable references, inherited by union across every parent.
Renaming work does not subtract them. Expansion adds references. Reclassification
requires a new, higher-generation trusted admission with evidence; it cannot
rewrite history. Ambiguous semantic equivalence routes to human governance rather
than accepting an unrelated label. General model output may be evidence but is
not unquestioned classification authority.

The authoritative action classifier must inspect the intended mutation surface,
operation and content-derived facts where practical. Filenames, extensions and
worker labels such as docs, tests, refactor or maintenance are only proposals.
Runtime code under a documentation extension remains semantic code; generated
runtime code remains semantic code; a test-labeled patch that changes runtime
contains both action classes; and compound effects retain every applicable class.
Unknown content, conflicting evidence, or uncertain objective/action identity
fails closed. `classify_authoritatively` is a pure executable model of that
obligation and accepts only a separately registered classifier identity and
provenance. It does not perform or authenticate production content inspection.

V2 action classes are `static_read`, `test_only`, `docs_only`,
`schema_spec_write`, `semantic_code_write`, `repo_write`, `integration`, `merge`,
`deploy`, `external_write`, `permission_change`, and `private_data_access`.
Governance gates must include every consequential class from semantic code write
through private-data access. Static/test/docs/spec labels do not override stored
classification. A no-match result remains `NO_MATCHING_BLOCK_NOT_AUTHORIZATION`.

## Repository ancestry and governance lineage

Repository lineage records observable Git/control-plane facts: commit parents,
branch tips, pull-request refs, detached checkouts, and merge parents. Governance
lineage records semantic descent that Git ancestry cannot prove, including
cherry-picks, ports, restacks, recreated patches, and preservation branches.
Either kind can match a gate; both union transitively through all parents.

The future admission service must derive repository lineage from trusted
repository state and governance lineage from reviewed provenance/evidence. A
worker cannot declare either authoritative. Semantic ports without Git ancestry
must explicitly inherit governance objective/gate references or fail closed.

## Deterministic v1 → v2 migration

`migrate_v1_to_v2` requires:

1. an object validated against the preserved
   `checkpoint_snapshot.v1.schema.json` contract and an independently pinned
   source digest;
2. an explicit v1-to-v2 manifest;
3. a target generation greater than the v1 revision and any trusted minimum;
4. an exact trusted migration authority ID/generation from configuration outside
   the manifest;
5. exactly one classification decision for every v1 entity;
6. exact preservation of parents, objectives and gate references;
7. preservation (and optional expansion) of repository lineage;
8. nonempty governance lineage and admission evidence;
9. explicit root-admission evidence for every parentless root;
10. durable source/manifest digests, authority, time and evidence in migration
    provenance.

Derived records require their known parent list. Parentless records are ambiguous
until the manifest explicitly classifies them as roots with trusted evidence.
Active gates are copied. Old action names are mapped conservatively and all v2
consequential actions are added, so migration cannot narrow a gate. Stored
`released` assertions remain present and effective because release validation is
still `UNAVAILABLE`.

The reference function is deterministic for identical source, manifest, pin and
authority configuration. It performs no file/database writes. A production
migration must additionally preserve append-only generations transactionally,
prevent concurrent rollback, and persist an immutable audit record.

## Fail-closed conditions

Unsupported version; stale source digest; generation rollback; absent or unknown
authority; incomplete, duplicate, missing or conflicting admissions; fabricated
parents; lost objective, lineage, gate, or active-gate data; unknown action; action
downgrade; ambiguous root; malformed record; stale current-state pin; and
unvalidated release all block. A valid unrelated admission can report no matching
gate, but that report grants no authority.

## Non-implementation boundaries

`production_enforcement=NOT_IMPLEMENTED`.
`human_trust_anchor=UNRESOLVED`.
`external_write_enforcement=NOT_ENFORCED`.
`release_validation=UNAVAILABLE`.

There is no live repository service, cryptographic human authentication, GitHub
App/hook, atomic production mutation guard, deployment control, provider/runtime
activation, or TaskLedger integration in this package. Tests demonstrate the
normative evaluator only. Issue #23 remains gated and PR #34 remains preserved
unauthorized evidence.

## Two universes and the authoritative mutation boundary

Source: independent Cursor reconnaissance supplied by the user on 2026-09-12.
This addition incorporates that finding; it does not repeat the reconnaissance
or assert that any operational call path has been verified as protected.

The **GOVERNANCE UNIVERSE** contains schema, checkpoint evaluator, admission
contracts, gate inheritance and tests, including TaskLedger / Issue-33 constructs
on governance-oriented tips. The **OPERATIONAL UNIVERSE** contains actual
mutation/execution paths, task queues, repo adapters, Guardian cycles, and local
or external Git writes. Those paths can exist on lineages that do not contain or
import the governance implementation. Git-history presence, a passing evaluator,
or a governance-oriented branch does not join these universes.

Normative principle:

> No semantic or durable mutation path may infer authority merely because governance state exists elsewhere. The authoritative mutation boundary must consume a trusted admitted record and current effective gate state before mutation.

Passing governance tests alone does not establish this property in production.
An evaluator result, even `NO_MATCHING_BLOCK_NOT_AUTHORIZATION`, is not a mutation
permit. Actual coverage requires an authoritative bridge on the executing
operational lineage and evidence that every relevant route crosses that boundary.
An import alone is insufficient. A gated objective and an unprotected path can
coexist: the objective remains gated while the path is `NOT_ENFORCED`.

## Operational mutation surfaces and required admission bindings

All four surfaces below are concrete future enforcement/bypass surfaces from
Cursor's findings. None is assumed to consult governance. In the absence of
direct evidence of authoritative enforcement, each is `NOT_ENFORCED`.

For **each** surface, the future boundary must obtain the complete trusted
admission bundle below from a trusted source, bound to the exact attempted effect.
These are bridge proof obligations, not claims that new fields or a production
permit format have already been implemented in v2:

| Required binding | What the admission record and trusted current state must supply |
| --- | --- |
| Admitted entity identity | Stable entity ID/kind, exact admission generation and authenticated authority ID/generation; bind the acting task and concrete operation/target to that entity. Worker labels cannot supply authority. |
| Root/derived classification | Explicit trusted root decision and root evidence, or derived classification with existing admitted parents. Empty ancestry cannot create a root. |
| Ancestry | All admitted parents and independently established repository/control-plane ancestry, including ports, queue sources and detached checkout identity as applicable. |
| Governance lineage | Reviewed semantic descent across all parents, ports, restacks and recreated work, with inherited objective/gate references; Git disconnection cannot erase it. |
| Objective | Trusted objective references inherited by union, bound to the proposed effect, including Issue #23 when applicable. Unknown equivalence fails closed. |
| Action class | Authoritative classification of every intended effect before mutation; compound operations must cover every applicable class. A worker's test/docs label cannot narrow it. |
| Applicable gate generation | Effective inherited gate IDs and their exact current generations from trusted state, including applicable scope/actions and release state. A prior admission cannot freeze older gate state. |
| Trusted snapshot/generation | Independently trusted current snapshot digest and monotonic generation, authority-registry generation, and durable rollback high-water mark; recheck freshness at the mutation boundary. |
| Human-release evidence when required | Authenticated human authority, release provenance, objective/action/gate scope and exact gate generation, validated against current state. A worker assertion or tests cannot release a gate. Validation is currently `UNAVAILABLE`, so required releases remain blocked. |

The following per-surface bindings specialize **all nine** requirements above;
they are not substitutes for them. Action examples are minimum candidate classes,
not an exhaustive preclassification of uninspected runtime behavior.

| Surface | Entity, ancestry and effect that the trusted bundle must bind | Objective/action and gate application | Current classification |
| --- | --- | --- | --- |
| `mutation_engine._direct_apply_mutation` | Admitted mutation request derived from its submitting task/proposal; exact target checkout/content generation and intended change. A direct call cannot omit its parent or mint a root. Operational inspection shows it is a fallback skipped by the configured live mutation backend, so its architectural role is `PARTIAL_BOUNDARY`, never a sufficient choke point. | Resolve semantic objective/lineage before apply; classify `semantic_code_write` and/or other applicable durable writes. Consume current inherited gates and generation-scoped release evidence immediately before the effect. | `NOT_ENFORCED` |
| `implementer/repo_adapter` | Admitted repository operation derived from the implementing task and mutation request; exact repository, target state and local/external destination. Preserve governance descent through ports/restacks regardless of branch or detached SHA. | Classify applicable `repo_write`, `integration`, `merge`, `external_write`, and semantic effects; bind each effect to current objective gates and required releases. Direct adapter invocation must require the same bundle. | `NOT_ENFORCED` |
| `self_task_queue` | Admitted queue entry/operation derived from the producer task and its full ancestry; persist admission identity/generation through enqueue, update, retry and dequeue/execution. Queue persistence itself needs classification. | Classify durable queue changes and the eventual execution effects under inherited objectives. Re-read current gates on execution/retry; an enqueue-time snapshot or queue-generated task ID grants no authority. | `NOT_ENFORCED` |
| `guardian_cursor_cycle` | Admitted cycle operation and derived child work tied to originating task(s), inputs and intended output targets; retain ancestry/governance lineage across cycle, worker and restart boundaries. | Classify dispatch, durable cycle updates and each downstream semantic/repository/external effect as applicable. Reconsume current gates at each mutation boundary; a successful cycle or worker output cannot supply release evidence. | `NOT_ENFORCED` |

The bounded current mediated-writer inventory additionally names
`mutation.py.apply`, `MutationPublisher.publish_mutation` (including its direct
`Path.write_text` effects) and
`MetaCoder.apply_mutation`. They also remain `NOT_ENFORCED`. The future control
plane must maintain a versioned authoritative writer registry: an entry records
the writer identity/version, surface class, integration generation and reviewed
effect adapter. Presence in a source scan or registry is not enforcement.
Unknown/unintegrated writers are outside the enforcement plane and remain
`NOT_ENFORCED` until direct integration evidence proves otherwise.

## Admission issuance and objective attachment

`WORKER_PROPOSAL` is descriptive, untrusted input. It can request work and offer
evidence, but its task ID, objective name, root/derived label, parent list,
provider/session identity, action label, target or claimed generation grants no
authority. `TRUSTED_ADMISSION_RECORD` is issued by the future trusted admission
service from independently controlled state and evidence. It binds:

1. admitted entity identity and explicit root/derived status;
2. all parents plus inherited repository and governance lineage;
3. the union of inherited objective references;
4. every authoritative action class for the intended effect;
5. applicable gate IDs and generations;
6. trusted current snapshot generation and digest;
7. exact mutation surface/repository/worktree/ref and expected base/head state;
8. admission and issuance generations;
9. issue/expiry times;
10. issuer identity/generation and provenance;
11. classifier identity/version and evidence;
12. canonical classified write set, write-set digest, classification digest and
    exact staged-patch digest; and
13. required human-release evidence and validation status.

Workers cannot manufacture, refresh or widen these fields. A derived task or
queue item must attach to admitted parents before execution. A root requires a
separate trusted root admission. A new queue/task/branch/objective ID is never a
root proof. On restart, missing or invalid persisted admission context is not
reconstructed from worker text; the item fails closed or is quarantined.

Objective attachment occurs before claim or mutation. Inherited objective refs
cannot be replaced by labels such as constructor cleanup, bootstrap repair,
lifecycle normalization, runtime hygiene, monitoring refactor, or a newly minted
objective. A trusted higher-generation reclassification with evidence may expand
or clarify scope. The system does not claim perfect automatic semantic detection:
uncertain equivalence is quarantined for human governance review.

## Classified write set and deterministic classification digest

This repair advances the bridge-only `TRUSTED_ADMISSION_RECORD` and
`MUTATION_AUTHORIZATION_TICKET` shapes to record version 2 because exact-effect
fields are safety-significant required data. Version 1 bridge records are legacy
evidence and cannot be silently accepted or inferred into version 2.

Authorization applies to exact intended effects, not merely an action label. An
authoritative classifier emits a canonical `classified_write_set`. Each entry
binds one repository-relative normalized path, its operation (`create`, `update`,
`delete` or `rename`), a content/effect digest, and every action class applicable
to that path. Paths use `/`, are relative, contain no empty, `.` or `..` segment,
and are unique. Entries sort by path, operation and effect digest; action arrays
sort lexically. Duplicate, malformed, unsorted or noncanonical input fails closed.

`write_set_digest` is SHA-256 over UTF-8 contract-canonical JSON v1:
`{"write_set_version":1,"effects":[...]}` with object keys lexically sorted,
compact `,`/`:` separators, JSON arrays preserved in their required canonical
order, and non-finite numbers forbidden. `classification_digest` uses the same
serialization over the authoritative classification record excluding the digest
field itself. It binds admitted entity ID, admission generation, objective refs,
governance lineage, exact repository/ref/worktree/base/head target, normalized
write set and digest, aggregate action classes, classifier ID/generation/version,
staged-patch digest, dynamic-effect policy and classification evidence. Ticket ID
and nonce are deliberately absent, avoiding a circular dependency.

The classifier and admission issuer independently pin the classification digest.
The admission issuer also compares entity, generation, objectives, governance
lineage and mutation target against trusted admission state. A worker cannot
classify `docs/readme.md` and later substitute `project_guardian/core.py`, even if
both attempts claim the same action class.

For semantic writes, the preferred safe pattern is an exact staged patch whose
digest and complete materialized write set are classified before ticket issuance.
Generated/dynamic work may first run in a non-durable sandbox, then materialize,
reclassify and request a new ticket. An authoritative classifier may additionally
limit materialization to approved namespaces, but a namespace is not a substitute
for the final exact patch/write-set binding. Unknown expansion, namespace escape,
or `reclassify_after_materialization` state cannot receive a mutation ticket.

## Mutation authorization ticket and atomic consumption

After admission and authoritative classification, a future boundary may issue a
single-use `MUTATION_AUTHORIZATION_TICKET`. The executable schema/reference binds:

- ticket ID and nonce/replay identity;
- admitted entity, inherited objective refs, and both lineage forms;
- every permitted action class;
- exact target surface, repository, worktree/ref, expected base SHA and head SHA;
- classifier version, classification digest, canonical classified write set,
  write-set digest and exact staged-patch digest;
- current gate snapshot generation/digest and applicable gate generations;
- admission and issuance generations;
- release generations (empty while validation is unavailable);
- issue/expiry times; and
- issuer identity/provenance plus a digest of the complete checked state.

The normative invariant is: **the state checked must be the state mutated, or the
mutation must fail**. The production boundary must consume the ticket and perform
the effect in one transaction/CAS or an equivalent generation-fenced protocol.
It rejects a changed head/base/ref/worktree/surface, changed ancestry or governance
lineage, changed objective, gate/snapshot/admission/issuance generation change,
stale digest, expired/not-yet-valid ticket, nonce replay, scope widening, or a
revoked/superseded release. A worker cannot silently refresh a ticket. External
effects need equivalent fencing at their authoritative repository/service edge.

Immediately before mutation, the mediated writer must independently derive the
actual requested target, complete write set and staged-patch digest and compare
them with the ticket. Any added, omitted, changed or reordered path; different
operation/content; classifier substitution; surface change; or patch change is
`BLOCKED_EFFECT_MISMATCH`. Omission is handled deterministically as a mismatch,
not silently narrowed authority. The check, durable nonce consumption, exact
effect, and effect receipt must share one transaction/CAS or equivalent fence.

`issue_mutation_authorization_ticket` and
`consume_mutation_authorization_ticket` are pure reference functions. Their
success disposition explicitly says it is not production authority; they neither
reserve state nor mutate anything. Production needs durable nonce consumption,
high-water marks, concurrency serialization and recovery semantics.

Tickets are fail-closed single-consumption tokens. Once a mutation attempt enters
the fenced boundary, its nonce is consumed whether the attempt succeeds, fails,
partially writes, or crashes. A retry re-reads actual repository state,
re-materializes and reclassifies the effect where needed, and obtains a new
ticket. A worker cannot replay or refresh the old token.

## Task, queue and cycle identity binding

A task/queue attachment binds task ID, admitted entity ID, parent entity refs,
objective refs, governance lineage, admission generation and admission-record
digest. The task ID and admitted entity ID must identify the same admitted task;
the parent/scope/generation fields must exactly match the admission record. IDs
are unique in the authoritative store and ownership cannot be transferred by a
worker reference. Foreign-admission borrowing and parent/admission swaps fail
closed. Restart validates the immutable attachment and quarantines missing or
changed lineage.

Every orchestration cycle carries admission-record digest, admitted entity,
active ticket ID and nonce, classification and write-set digests, objectives,
repository and governance lineage, applicable gate generations, admission and
snapshot generations, and snapshot digest through selection → prompt → worker
launch → tool invocation → result → verifier → retry → provider switch → restart.
Provider/session are transport fields only. A worker response cannot replace the
immutable context; missing context quarantines the cycle.

## Authorized-progress state model

Artifact existence and technical correctness are separate from authorized
control-plane progress. The normative states are:

`OBSERVED_UNTRUSTED` → `PRESERVED_EVIDENCE` → `ADMITTED` →
`AUTHORIZED_TO_EXECUTE` → `EXECUTED_PENDING_VERIFICATION` →
`VERIFIED_NOT_YET_AUTHORIZED_FOR_PROGRESSION` → `AUTHORIZED_PROGRESS`.

Transitions can skip from observed/preserved output to technically verified
evidence, but cannot reach `AUTHORIZED_PROGRESS` without a trusted progression
decision bound to the complete immutable provenance chain:

`Admission record digest → classification digest/write-set digest → ticket ID
and state digest → mutation result digest/result identity → verification digest
→ authorized-progress decision`.

A mutation result can be created only after the ticket nonce is in the consumed
state and binds that nonce plus the admission and ticket identities, exact classified
effect, staged patch, mutation outcome, evidence-persistence outcome and immutable
result identity. Result identity is an exact commit SHA, tree SHA, patch digest or
changed-file digest plus repository head and write-set digest. Verification binds
its PASS/FAIL to that exact mutation-result digest, ticket ID and result identity.
Progression revalidates every link and the current result identity. A PASS boolean,
completion flag or technically valid but differently bound verification is
`BLOCKED_PROVENANCE_MISMATCH`.

Verification answers whether work is technically correct; governance answers
whether it was authorized. CI,
Vega, architecture review, a completion packet, branch, commit, PR, file or worker
output cannot substitute for governance. Historical `7374820` and `0a2d135` may
remain technically useful preserved evidence while staying outside authorized
progress.

Mutation/evidence dual failures are explicit fail-closed states:

- mutation succeeds but its receipt/evidence persistence fails, or the process
  crashes between them: `QUARANTINED_INCOMPLETE_EVIDENCE` pending trusted
  reconciliation, never authorized progress;
- evidence claims success while mutation failed: the independently observed
  mutation/result identity controls, so progression is blocked;
- partial mutation: `QUARANTINED_PARTIAL_MUTATION`, with the ticket consumed;
- stale or substituted result identity: `BLOCKED_PROVENANCE_MISMATCH`.

Ordinary filesystem and Git writes are not database transactions. A production
design must either transactionally couple mutation, nonce and receipt, or persist
a recoverable intent/receipt journal with fencing and post-crash reconciliation.
Reconciliation must independently inspect repository state and issue a new
immutable chain; it cannot mark the old incomplete attempt authorized.

## Composed multi-boundary design

`mutation_engine._direct_apply_mutation` is retracted as a sufficient or singular
first production boundary. Operational inspection classifies it as
`PARTIAL_BOUNDARY`: it is absent on the product tip, is a fallback on the current
operational lineage, and is bypassed by the configured live mutation backend,
`repo_adapter`, publisher/MetaCoder, queue/cycle orchestration and raw writers.

The smallest credible bridge is `COMPOSED_MULTI_BOUNDARY_DESIGN` spanning:

1. trusted admission issuance and objective/lineage attachment;
2. task/claim authorization and queue attachment before execution;
3. authoritative objective/action and exact write-set classification from
   intended effects;
4. fenced single-use authorization-ticket issuance;
5. mediated checks at the actual live `mutation.py.apply` (or authoritative
   equivalent) and `implementer/repo_adapter.apply_patch`/equivalent repository
   file-write paths;
6. atomic ticket/effect comparison and consumption with mutation and evidence
   capture;
7. a controlled authorized-progress transition distinct from verification; and
8. later repository-side enforcement for external transports.

Protecting only one listed function is an incomplete plan. The executable
`assess_composed_boundary_plan` model requires live mutation, repository file
write, task claim, queue/objective attachment and authorized-progress boundaries
together, while continuing to report production/cross-universe enforcement as
`NOT_IMPLEMENTED`.

Recommended sequencing, without implementation:

- **Phase A — dry-run control plane:** trusted admission issuance store,
  task/queue attachment, objective/action/write-set classifier, deterministic
  classification digest, fenced ticket lifecycle, durable nonce/generation
  high-water state and simulated/quarantine progression. No live writer consumes
  a ticket.
- **Phase B — mediated writer enforcement:** consume the same effect-bound ticket
  at all inventoried mediated writers: live `mutation.py.apply`,
  `mutation_engine._direct_apply_mutation`,
  `implementer/repo_adapter.apply_patch`, `MutationPublisher.publish_mutation`
  and its direct `Path.write_text` effects,
  `MetaCoder.apply_mutation`, and proven current equivalents. This inventory is
  the known set, not a completeness claim. Every unknown or unintegrated mediated
  writer remains `NOT_ENFORCED` until registered, reviewed and connected to the
  same effect comparison and transaction.
- **Phase C — authorized progress:** enable the real transition only when the
  complete admission → classification → ticket → effect → result → verification
  chain validates against current state.
- **Phase D:** add repository-side enforcement and credential mediation for raw
  external writes, plus a separately approved Issue #31 trust anchor.

`guardian_cursor_cycle` must carry the immutable admission-record digest,
admitted identity, active ticket ID/nonce, classification/write-set digests,
objectives, repository/governance lineage and gate/snapshot/admission generations through
selection → launch → worker execution → completion → verification → progression.
Provider/session changes, retries and restarts cannot erase them. Completion can
produce evidence but cannot self-promote progression.

## Repository-side second boundary and external writers

Raw Git CLI, GitHub API/App/CLI, Cursor/Codex shells, third-party Git clients,
other clones and human local Git cannot necessarily be stopped by Guardian-local
checks. They remain `NOT_ENFORCED`. Their outputs may exist, be observed, and be
preserved, but must remain quarantined from `AUTHORIZED_PROGRESS` until trusted
admission/reconciliation establishes the required lineage, objective, action and
current gate state.

Future repository-side enforcement is necessary to control ref mutation, push,
branch creation, PR-source provenance, direct API writes and credentialed external
agents. Possible mechanisms require a separate authority decision; this contract
does not choose or install hooks/rulesets, alter credentials, configure an App,
or claim server policy exists.

## Required governance-to-runtime bridge (future, not implemented)

The first credible bridge is the composed sequence above, not one function. It
MUST guarantee all of the following before enforcement can be claimed:

1. **One authoritative admission format.** Runtime paths consume the same
   versioned, authenticated admitted record, resolved outside worker control and
   bound to the exact requested effect. Caller-specific permissive formats or
   worker-supplied authority registries are not alternate admission mechanisms.
2. **One trusted current gate snapshot.** All boundaries resolve effective gates
   from the authoritative state source, with independently pinned digest,
   snapshot/gate/authority generations and a defined freshness protocol.
3. **Objective/action classification before mutation.** Resolve all applicable
   objectives and action classes, and ancestry/governance-lineage inheritance
   across every parent, before any semantic or durable effect. Unknown, missing,
   contradictory or unavailable classification/state fails closed.
4. **Atomic check + mutation or equivalent transactional protection.** Bind the
   admission, exact effect/target state and current gate generation in the commit
   protocol. A concurrent gate change invalidates stale decisions. A local check
   followed by an unguarded write is insufficient; external effects need an
   equivalent generation-fenced protocol at the authoritative external boundary.
5. **No worker-controlled root creation.** Only the trusted admission authority
   may admit roots. Task/session/provider changes and empty parents cannot reset
   inheritance.
6. **No branch-name or detached-SHA escape.** Bind trusted repository identity and
   state plus semantic governance lineage. Renames, rebases, ports, restacks,
   cherry-picks and detached execution cannot subtract inherited gates.
7. **No direct adapter bypass and no queue/cycle bypass.** Every relevant entry
   point and downstream write must cross the authoritative boundary, including
   direct calls, retries, resumed work and local/external Git writes. Protecting
   one wrapper does not establish complete coverage.
8. **Restart-safe state and generation rollback protection.** Persist admissions,
   lineage, gate state, trusted generation high-water marks and effect receipts
   transactionally outside worker control. Recovery cannot restore older trusted
   state or replay a stale authorization; retries must revalidate current gates
   and avoid duplicate effects. Unavailable recovery evidence fails closed.
9. **Validated release and output provenance.** A required human release must be
   authenticated and bound to the effective gate generation and intended scope.
   Record an authoritative effect receipt tying output to the admitted operation
   and checked generations. Output existence, test success or a worker's receipt
   alone must never be accepted as authorized progress.

## Cross-universe acceptance scenarios (specification only)

These are normative scenarios for future bridge verification, not executed
runtime tests. They require no imports or invocation of the unprotected paths
in the current specification work. Repeat every scenario for each of the four
surfaces above and for applicable local/external effects.

Base setup: trusted governance state on lineage G gates an objective (Issue #23
is a concrete example). Operational lineage O contains the selected mutation
path but does not contain/import the governance implementation. No authoritative
bridge exists. A worker attempts mutation on O under that objective.

| Scenario | Expected normative result |
| --- | --- |
| Base setup, regardless of whether the worker produces output | Path classification is `NOT_ENFORCED`; cross-universe enforcement is `NOT_IMPLEMENTED`. Do not report an actual blocked mutation without runtime evidence. The objective remains gated. |
| Output exists and passes operational tests; governance tests also pass on G | Output remains unauthorized evidence, never authorized progress or a gate release. Test success does not demonstrate that O consulted G. |
| Governance code is later copied/imported on O, but no authoritative check guards the effect | Still `NOT_ENFORCED`; availability/import is not boundary enforcement. |
| Worker changes branch name, uses detached SHA, recreates a patch, or claims a new root | Still `NOT_ENFORCED` without a bridge, and no normative authority is gained. Future bridge must preserve inherited gates and reject fabricated roots. |
| Worker calls the adapter directly or resumes queued/cycle work | Still `NOT_ENFORCED` without coverage evidence. A future wrapper-only bridge cannot authorize these bypass routes. |
| Future bridge sees missing admission, unknown objective/action, stale snapshot, generation rollback or unavailable required release validation | Required behavior is fail-closed before effects. This is a future acceptance obligation, not evidence of a present runtime block. |
| Future gate changes between check and write, or process restarts/retries | Required behavior is transactional rejection/revalidation of stale authority without duplicate effects or rollback; test the interleaving at the actual boundary. |

Future integration tests must observe the real mutation boundary and its effects,
not merely stub an evaluator that returns a desired result. Even demonstrated
coverage of one surface does not change the other surfaces' classifications.
Current cross-universe enforcement remains `NOT_IMPLEMENTED`.

Issue #23 remains: `GATED — NO SEMANTIC WORK AUTHORIZED`.
