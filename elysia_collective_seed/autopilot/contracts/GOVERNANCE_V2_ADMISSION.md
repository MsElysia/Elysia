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

1. an exact v1 object and independently pinned source digest;
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
