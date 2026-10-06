# Issue #43 manifest/pointer model handoff

Task: execute the next bounded slice from the saved 2026-10-06
`Issue43-current-state-manifest-spec.md`, reusing the existing contracts package.
Status: SPECIFICATION_AND_TEST_ONLY / LOCAL_VERIFICATION_PASS / NOT_PRODUCTION.

Base: draft PR #105 exact `a5d61acfd9606b9090acebe5a049c3305e02a890`.
Branch: `codex/governance-43-manifest-model-20261006`.
This handoff is committed with the candidate; obtain its exact head from Git
or the draft PR, rather than inventing a self-referential commit SHA here.

## Read and changed

Read: AGENTS.md; current Issue #43 review 6004946848; current explicit Issue #11
checkpoint 6004967846; saved manifest specification; existing contracts README,
v2 snapshot schema, checkpoint_reference.py, admission.py and Issue #33 fixtures
and v2 tests; inherited exact-head CI workflow. No ancestor verdict transfers.

Changed: contracts/current_manifest.schema.json; contracts/manifest_reference.py;
contracts/test_issue_43_manifest.py; contracts/README.md; this handoff.
Existing snapshot schema, admission/gate evaluators, ledger, runtime and workflow
bytes are unchanged. No live manifest, current pointer or task state was created.

## Result and validation

The schema and disposable model enforce exact generations, complete independently
pinned fixture inventory, whole predecessor tuple, retained claims/blockers,
fail-dominant routing, fixed gate snapshot, dependency availability, source fences,
deterministic competing-writer schedules and replay diagnostics. All acceptance
is a model pointer disposition, never execution authority. Gate diagnostics reuse
the existing evaluate_admitted boundary. M01–M20 expand into 71 focused cases.

Final local CI-equivalent suite: **610 passed**, including 71 new cases and all
539 inherited cases. These counts overlap; they are not added as separate runs.
Compileall and diff-check passed; 31 seed JSON artifacts parsed successfully.
Python 3.12.14. Hosted CI is not claimed by this committed handoff.

Independent delegated review (manifest_review, same session, not external Vega)
ran **71/71** final focused tests and direct forged-receipt and same-pin changed
source probes. It found two defects, both fixed before final validation: reader
schema errors escaping the unavailable-state diagnostic, and otherwise passing
ungated records bypassing explicit unmet blockers. The added regressions cover
both. No remaining in-scope bypass was identified by that reviewer.

## Remaining limitation / next task

This is a conservative executable subset of the normative specification, not
live acceptance-complete #43. Complete inventory and trust pins are fixture-owned.
Existing product-specific record bindings/dispositions and the gate snapshot
remain immutable; successors may add records, claims and blockers, not retract
history, clear failures, update gates or release authority. Authenticated
supersession, live exhaustive inventory acquisition, bootstrap, real transactional
storage/CAS, physical crash durability, actual process restart/replay and automatic
checkpoint generation are absent. The in-memory lock models a linearization
point only; deterministic schedules do not prove production concurrency.

Next bounded task: fresh exact-published-SHA independent falsification and hosted
exact-head CI for this draft. Do not rerun unchanged ancestors or wire a storage
adapter/TaskLedger/runtime as part of that review. Issue #43 stays PARTIAL/open.

#29/#30/#31/#33 remain unreleased; #23/#36/#37 remain blocked; PR #34 remains
unauthorized-but-preserved. External enforcement NOT_ENFORCED, production
enforcement NOT_IMPLEMENTED, human trust anchor UNRESOLVED, release validation
UNAVAILABLE. Keep all PRs draft/unmerged. No merge, deployment, activation,
live-memory, provider/autonomy, private-data/credential/permission expansion,
human release, history rewrite or evidence deletion occurred.
