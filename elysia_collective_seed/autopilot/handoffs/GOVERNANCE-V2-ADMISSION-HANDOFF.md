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
