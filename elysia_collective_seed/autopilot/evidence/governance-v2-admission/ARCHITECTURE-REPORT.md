# Independent Architecture Review — Governance v2 Trusted Admission

## Verdict

**READY_FOR_INTEGRATION_REVIEW** for exact immutable candidate
`7b076548751e72879d0632c1ec687e087e43a7b8` only.

This verdict means the schema, migration contract, reference evaluator, and
normative production obligations are coherent enough for integration review as
a `SPECIFICATION_AND_TEST_ONLY` deliverable. It does not authorize runtime
activation or claim that any repository, queue, mutation, deployment, release,
or external-write path is protected.

## Blockers

None within the authorized specification-and-test scope.

## Review provenance and scope

- Base: `9ad2d941269650b231d3f3e4f5327266a66f9cb1`
- Candidate: `7b076548751e72879d0632c1ec687e087e43a7b8`
- Candidate subject: `fix(governance): validate exact v1 migration inputs`
- Candidate branch named by the task: `codex/governance-v2-trusted-admission`
- Review worktree: `C:\Users\Owner\guardian-v2-admission-architecture`
- Worktree state: detached at the exact candidate and clean after review
- Vega report reviewed:
  `C:\Users\Owner\guardian-v2-admission-vega-report-7b07654.md`
- Vega evidence reviewed:
  `C:\Users\Owner\guardian-v2-admission-vega-evidence-7b07654`

I read `AGENTS.md`, the complete candidate stack and diff from the base, the v2
schema, the byte-preserved v1 schema, the admission/migration implementation,
the checkpoint evaluator, all candidate tests, the v2 specification, the
handoff, and the exact-candidate Vega report and breaker tests. I did not edit
the candidate or activate any runtime path.

## Architecture findings

### Schema evolution and version exactness

V2 is the smallest safe breaking evolution of the draft contract. The active
schema moves from `revision/entities` to
`snapshot_generation/admission_authorities/admissions/migration_provenance`,
while the original PR #32 v1 schema is retained separately. The retained file is
the exact original Git object (`b5aa1fed58ff86b5a79ef49f51049476e8c14473`),
so the candidate does not retroactively add `ancestry_kind` to v1.

The authoritative wrapper accepts only a Python integer version 2; missing,
boolean, float, string, older, and forward versions fail closed. V1 is accepted
only by the explicit migration function after an exact integer-version check and
full validation against the preserved v1 schema. This prevents
`parents=[] => root` from becoming an implicit version conversion.

### Trusted authority and worker-controlled fields

The trust separation is clear. The stored admission, not worker proposal prose,
contains entity identity, root/derived status, parents, objectives, action
classes, two lineage forms, gate references, authority generation, evidence,
and time. `evaluate_admitted` discards `worker_proposal`; an action must already
exist in the stored admission. Every admission authority reference must resolve
to an exact ID/generation in the validated snapshot registry.

The contract also states the essential limitation accurately: a schema-valid
authority string and a caller-computed digest are not authentication. The future
repository/control-plane service must supply entity/action classification,
authority configuration, and the current snapshot pin outside worker control.
The evaluator produces diagnostics rather than permission.

### Root/derived, objective, action, and gate semantics

Root creation is a privileged classification. Native v2 roots require a trusted
admission record with evidence and zero parents. Migration roots additionally
require explicit root-admission evidence. Derived records require at least one
parent, and graph validation rejects missing parents, cycles, duplicate records,
unknown authorities, and missing gates across the entire graph, including
disconnected records.

Objectives, both lineage sets, and explicit gate references union through every
parent. Worker renaming cannot subtract inherited scope. Action classes cover
the requested static, test, documentation, schema/specification, semantic,
repository, integration, merge, deployment, external, permission, and private
data categories. Every gate must retain all consequential classes. An
unadmitted or unknown action fails closed; a valid no-match remains
`NO_MATCHING_BLOCK_NOT_AUTHORIZATION`.

Both `active` and `released` gate records remain effective because release
validation is unavailable. The model never converts a release-shaped assertion
into authority.

### Migration determinism, safety, and provenance

The migration is deterministic for identical source, manifest, trusted source
pin, trusted authority configuration, and minimum generation. It validates the
exact v1 source before conversion, requires a target generation greater than
the v1 revision and trusted minimum, resolves an exact trusted migration
authority, and requires exactly one decision for every source entity.

Parents, objectives, and gate references are preserved exactly; repository
lineage may expand but cannot shrink; governance lineage and evidence must be
nonempty. Parentless records require explicit root evidence. Gates are copied,
legacy action names are mapped, and every consequential v2 class is added, so a
migration cannot narrow an old gate. Source and manifest digests, authority,
time, and evidence are recorded. The generated target then passes both v2 schema
validation and graph-wide semantic evaluation before return. Public malformed
inputs normalize to `AdmissionError`.

### Repository ancestry and governance lineage

Separating repository lineage from governance lineage is the correct model for
branches, detached SHAs, merge parents, cherry-picks, ports, restacks, and
preservation branches. Either lineage can match a gate, and both inherit through
all admitted parents. The design does not pretend that Git ancestry proves
semantic descent; the future control plane must establish repository facts and
reviewed governance provenance independently.

### Two-universe operational bridge

The specification accurately distinguishes the governance universe from actual
mutation/execution paths. It classifies
`mutation_engine._direct_apply_mutation`, `implementer/repo_adapter`,
`self_task_queue`, and `guardian_cursor_cycle` as `NOT_ENFORCED` and makes no
claim that these paths exist on, import, or consult the governance lineage.

The future bridge requirements are implementation-ready at the obligation
level: one authenticated admission form, one current trusted snapshot,
effect-bound objective/action classification, complete ancestry and governance
lineage, generation fencing, atomic check-plus-mutation, restart and retry
safety, no direct-adapter/queue/cycle bypass, authenticated generation-scoped
release proof, and authoritative effect receipts. Cross-universe tests must
observe actual effects at the real boundary rather than stub the evaluator.

## Non-blocking limitations

1. **Authentication, durable storage, and enforcement are absent by design.**
   The human trust anchor remains `UNRESOLVED`; production and cross-universe
   enforcement remain `NOT_IMPLEMENTED`; external writes remain `NOT_ENFORCED`;
   release validation remains `UNAVAILABLE`.

2. **Monotonicity beyond the snapshot high-water mark belongs to the future
   store.** The pure model can reject snapshot rollback only when the caller
   supplies a trusted minimum. It does not compare per-admission, per-gate, or
   authority generations with historical records. The production design must
   define those high-water marks and causal rules transactionally.

3. **The strict v2 entry point matters.** JSON Schema treats JSON numbers such as
   `2.0` as integers when mathematically integral, and the low-level `evaluate`
   helper performs schema validation directly. `validate_snapshot_version` and
   `evaluate_admitted` add the intended exact runtime type check. A production
   adapter must use the strict boundary; a later cleanup should centralize that
   check so direct low-level use cannot diverge.

4. **Migration evidence needs durable canonical storage in production.** The
   reference stores a digest of the manifest and general evidence references,
   while the migration-only `root_admission_evidence` field is not copied as a
   separately named v2 field. A production migration must retain and
   dereference the canonical manifest, bind its approval to the selected
   authority, and make root-specific evidence auditable. The current function
   does correctly require and hash that evidence before returning a target.

5. **Directly supplied v2 provenance has fewer semantic checks than generated
   migration output.** The schema validates the shape of
   `migration_provenance`, while `evaluate` does not independently require its
   `migrated_by` reference to resolve to a migration authority. The migration
   function produces the correct linkage. Before a production service accepts
   externally materialized v2 snapshots, it should validate that relationship
   and reject hand-constructed inconsistent audit provenance.

6. **Compound effects require multiple authoritative classifications.** The
   evaluator accepts one entity/action pair per call. The bridge specification
   requires all applicable classes for a compound operation; production must
   make that requirement atomic so checking one harmless class cannot cover a
   semantic, repository, or external effect.

7. **The candidate handoff is an initial packet, not the completion packet.** It
   still records the earlier 376-test count and says Vega and architecture review
   are pending. The evidence publication step should record the exact candidate,
   Vega `PASS`, this verdict, and the current 414-test result. The contract README
   also has two stale v1 terms (`revision`, `claim`/`semantic_write`) in an
   otherwise v2 description. These are editorial follow-ups and do not change
   the implemented fail-closed semantics.

## Verification evidence

- Exact required candidate/inherited suite: **414 passed in 4.23s**.
- Focused contract suite: **201 passed in 1.31s**.
- Independent Vega breaker corpus, rerun against this detached candidate:
  **151 passed in 0.84s**.
- Contract `compileall`: PASS.
- Candidate contract JSON parse: PASS.
- Full Vega JSON parse: PASS, 65 files (reviewed from independent evidence).
- V1 schema Git-object identity: PASS.
- `git diff --check`: PASS.
- Detached exact-SHA and clean-worktree checks: PASS.

For completeness, a default repository-root `pytest -q` is not a usable gate in
this historical checkout: collection stops with 41 errors in unchanged files,
including absent runtime dependencies, an undefined optional `np`, a missing
pytest marker, and a pre-existing syntax error. None of those files is in the
candidate diff. The explicit 414-test governance/inherited suite is the relevant
passing gate; this review does not claim broad runtime compatibility from it.

## Next boundary recommendation

Preserve this report and the exact Vega evidence on a separate evidence commit,
complete the durable handoff, and open a stacked draft PR against the verified
PR #35 product lineage. Do not merge or activate it from this verdict.

The first future integration task may investigate
`mutation_engine._direct_apply_mutation` as a bounded candidate, but it must first
prove the actual write and transaction boundary and its caller coverage. That
separately authorized task must define authenticated authority resolution,
trusted generation high-water storage, canonical migration-manifest retention,
effect binding, and atomic generation-fenced mutation. Adapter, queue, cycle,
restart/retry, and external-write routes remain independently `NOT_ENFORCED`.

Issue #23 remains **GATED — NO SEMANTIC WORK AUTHORIZED**. PR #34 and its product
remain preserved unauthorized evidence and are outside this review.
