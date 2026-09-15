# GOVERNANCE V2 ADMISSION HANDOFF

## BASE SHA

`9ad2d941269650b231d3f3e4f5327266a66f9cb1` (draft PR #35 product).

## CANDIDATE SHA

Recorded after commit and in separate exact-candidate verification evidence.
Branch: `codex/governance-v2-trusted-admission`.

## SCHEMA VERSION

`2`. Only exact integer version 2 is a valid current snapshot. V1 is accepted
solely by the explicit migration reference function. Missing, boolean, string,
older, and forward versions fail closed.

## BREAKING CHANGE

V2 replaces `revision/entities` with `snapshot_generation/admissions`, separates
repository from governance lineage, adds an authority registry and provenance,
and binds authoritative action classes. It resolves PR #35's improper breaking
mutation of v1. Existing v1 data cannot be consumed directly as v2.

## V1 → V2 MIGRATION

Migration requires a pinned v1 digest, explicit manifest, separately configured
trusted migration authority, strictly increasing generation, exactly one decision
per old entity, explicit root evidence, exact parent/objective/gate preservation,
repository-lineage preservation, nonempty governance lineage, and durable source
and manifest digests. Empty parents never infer root. Gate actions are mapped
conservatively and expanded to every consequential v2 action. Released assertions
remain ineffective. The reference is pure and deterministic; production
transaction/persistence is not implemented.

## ROOT ADMISSION MODEL

Root is privileged classification by a registered trusted control-plane authority
at an exact generation with source/evidence/time. A new name, branch, session,
provider, detached SHA, or empty parent list grants nothing. Derived admissions
require existing parents. Authority strings are normative data, not authentication.

## OBJECTIVE ADMISSION MODEL

Objective references live in trusted admission records and union through all
parents. Workers cannot replace them in proposal metadata. Expansion/reclassification
requires a new trusted admission with evidence; ambiguity remains blocked.

## ACTION ADMISSION MODEL

Stored classes distinguish static read, tests, docs, schema/spec, semantic code,
repo write, integration, merge, deploy, external write, permissions and private
data. The proposed authoritative action must exist in the admission. Descriptive
worker action labels are ignored and cannot downgrade semantic code to tests/docs.

## REPOSITORY ANCESTRY MODEL

Repository lineage represents independently derived Git/control-plane facts:
parents, branches, SHAs, PRs, detached rebinds and merge parents. This reference
model consumes those facts; it does not retrieve or authenticate them.

## GOVERNANCE LINEAGE MODEL

Governance lineage carries semantic descent across cherry-picks, ports, restacks,
recreated patches and preservation branches where Git ancestry alone is
insufficient. Repository and governance lineages union transitively and either
can match a gate.

## FAIL-CLOSED CONDITIONS

Unsupported versions, stale pins, generation rollback, unknown/duplicate authority,
incomplete/conflicting admissions, unknown/missing parents, ambiguous roots,
lost ancestry/objectives/lineage/gates, unadmitted action, malformed data, and
unvalidated releases block. No-match remains explicitly non-authorizing.

## TEST RESULTS

Implementer: **376 passed** (163 governance contract and 213 inherited tests),
Python 3.13.15, pytest 9.1.1, jsonschema 4.26.0. Contract compileall, every JSON
parse, and `git diff --check` passed. No Guardian/runtime/provider code activated.

## VEGA VERDICT

Pending fresh breaker on exact committed candidate.

## ARCHITECTURE VERDICT

Pending separate reviewer after Vega PASS.

## PRODUCTION ENFORCEMENT STATUS

`NOT_IMPLEMENTED`

## HUMAN TRUST ANCHOR STATUS

`UNRESOLVED`

## ISSUE #23 STATUS

`GATED — NO SEMANTIC WORK AUTHORIZED`

## NEXT BOUNDED TASK

Independent falsification, then architecture review. If both pass, preserve
reports on a separate evidence branch and open a stacked draft PR. A later task
may design the transactional storage/admission interface but must not claim Git
or human-auth enforcement without separately authorized implementation/evidence.

## TWO-UNIVERSES FINDING

Independent Cursor reconnaissance supplied by the user on 2026-09-12 identifies
a split between governance-oriented tips containing TaskLedger / Issue-33
constructs and operational/runtime lineages containing actual mutation paths.
This addendum incorporates that reconnaissance without repeating it.

GOVERNANCE UNIVERSE: schema, checkpoint evaluator, trusted admission contracts,
gate inheritance and tests. OPERATIONAL UNIVERSE: mutation/execution paths, queues,
repo adapters, Guardian cycles, local/external Git writes. Governance existing
somewhere in Git history does not protect runtime effects.

> No semantic or durable mutation path may infer authority merely because governance state exists elsewhere. The authoritative mutation boundary must consume a trusted admitted record and current effective gate state before mutation.

Passing governance tests alone does not establish this property in production.

## OPERATIONAL MUTATION SURFACES

| Cursor-identified surface | Current classification |
| --- | --- |
| `mutation_engine._direct_apply_mutation` | `NOT_ENFORCED` |
| `implementer/repo_adapter` | `NOT_ENFORCED` |
| `self_task_queue` | `NOT_ENFORCED` |
| `guardian_cursor_cycle` | `NOT_ENFORCED` |

No direct enforcement evidence is supplied for these paths; none is assumed to
consult governance. The [v2 contract](../contracts/GOVERNANCE_V2_ADMISSION.md#operational-mutation-surfaces-and-required-admission-bindings)
specifies each surface's required entity identity, explicit root/derived status,
ancestry, governance lineage, objective, action class, applicable gate generation,
trusted snapshot/generation and required human-release evidence. These future
bindings do not change any current enforcement classification.

## CURRENT CROSS-UNIVERSE ENFORCEMENT

`NOT_IMPLEMENTED`

The contract now specifies cross-universe acceptance scenarios: a gated objective
on governance lineage G, a worker mutation attempt on operational lineage O with
no governance import or authoritative bridge, and `NOT_ENFORCED` as the expected
path classification. Operational output, even passing tests, remains unauthorized
evidence. The scenarios also cover import-only wiring, detached/renamed work,
direct adapter calls, queue/cycle retries, stale state and transactional races.
They are specification scenarios, not executed integration tests or proof that
runtime attempts are blocked.

## REQUIRED GOVERNANCE→RUNTIME BRIDGE

Future requirements: one authoritative admission format; one trusted current gate
snapshot; objective/action classification before effects; complete ancestry and
governance-lineage inheritance; fail-closed unknown classification; atomic check
plus mutation or equivalent transactional protection; no worker-controlled roots;
no branch-name or detached-SHA escape; no direct adapter or queue/cycle bypass;
restart-safe trusted state; generation rollback protection; authenticated,
generation-scoped human releases when required; and authoritative output receipts.
The [normative bridge requirements](../contracts/GOVERNANCE_V2_ADMISSION.md#required-governance-to-runtime-bridge-future-not-implemented)
define the obligations. No production bridge is implemented or authorized here.

## FIRST FUTURE MUTATION BOUNDARY TO INTEGRATE

Recommend `mutation_engine._direct_apply_mutation` as the first bounded candidate:
the directly identified apply operation offers a small place to bind one concrete
mutation effect to an admitted entity and current gate generation. This is a
design recommendation based on the supplied surface, not a verified claim that
all writes converge there. A separately authorized integration task must first
establish its actual write/transaction boundary and caller coverage, then enforce
and test that bounded effect. Adapter, queue, cycle and external-write routes
remain `NOT_ENFORCED` unless separately covered and evidenced. Do not implement
this recommendation without separate authority.

## CURSOR FINDING INCORPORATION RECORD

Task: Governance Schema v2 / Trusted Admission Contract, Cursor finding addendum.
Worker: Codex. State: specification incorporated; production bridge pending
separate authority. Issue #23: `GATED — NO SEMANTIC WORK AUTHORIZED`.

Read: repository `AGENTS.md`, existing v2 specification and this handoff; supplied
Cursor findings. Changed: only this handoff and `GOVERNANCE_V2_ADMISSION.md`.
Existing admission/reference/schema working-tree changes belong to other ongoing
work and are outside this addendum. No operational source was changed or invoked.

Validation: reviewed all nine admission bindings for every listed surface, all
requested bridge properties, and the cross-universe scenario matrix; ran scoped
`git diff --check`. No executable tests added or run for this documentation-only
addendum. Earlier test counts above are historical and do not validate runtime
enforcement. Changes are uncommitted on `codex/governance-v2-trusted-admission`.

Uncertainty/risk: supplied reconnaissance does not establish a universal write
choke point or authenticated human release mechanism. Next bounded task remains
independent contract review; any runtime integration needs separate authority
and direct boundary evidence. No merge, publication, release or Issue #23 semantic
work is authorized by this record.
