# Agent A claim-boundary handoff — existing AUTOPILOT #8

Worker: independent Codex Agent A (boundary_claim). Base/worktree: detached 6649b89 at C:/Users/Owner/guardian-remote-boundary-claim. No production edits, commits, provider calls, merge or deploy. Parent owns sequential implementation after #22.

## Reproduced evidence

Run `python claim_boundary_repro.py` from this worktree (Python 3.13.15, stdlib only). Seven policy failures each yield an initial claim, same-owner renewal and expired-lease recovery: protected deployment; human approval required; unknown risk; missing dependency; disallowed worker; missing capability; missing task-class capability. Dispatcher denies all seven. An eighth bridge case supplies states={'missing':'completed'} and acquires despite absent dependency row. Script assertions all passed and records current vulnerabilities, not desired regression outcomes. pytest is not installed in the default interpreter; no baseline pytest run claimed.

## Smallest complete repair specification

1. Add keyword-only execution_workers constructor configuration using Worker records, default empty; copy into a trusted coordinator-owned registry. Unknown ID or absent registry must deny. Do not borrow verification registry or trust workers passed to dispatch_and_claim to authorize execution. Existing arbitrary Python/SQLite access and initial put_task admission remain trusted process boundaries, as documented by PR15; do not claim hostile-process authentication.
2. In claim, after BEGIN IMMEDIATE, fetch persisted row/payload and evaluate policy before any success path (especially existing first renewal UPDATE). Preserve terminal/state/active-lease errors sensibly. Require known AUTO_RISKS and no human_approval_required; protected risks always deny even if a Worker lists them. No new approval bypass/token semantics.
3. Resolve every dependency from tasks.status in this same transaction, requiring exactly completed. Missing, queued, running, verifying, review, blocked, human_review, rejected, archived and self-dependencies deny. Do not use payload status, caller states or auto-admit dependencies from caller assertions.
4. Requesting registered Worker must be available, explicitly cover risk, satisfy allowed_workers when nonempty, required_capabilities AND task_class (existing eligible_workers semantics). Claim checks eligibility, not score winner. Reuse eligible_workers or factor a small shared predicate; do not call whole dispatch in claim because last-attempt valid renewal must remain legal.
5. Failed policy checks must not extend lease, increment attempts, replace owner, or emit a success event. Keep current bounded attempt semantics: allowed live last-attempt renewal succeeds without increment; allowed expired recovery consumes one attempt and respects ceiling; explicit reap releases ownership but every subsequent acquisition must still recheck policy.
6. Bridge should select from trusted execution registry and authoritative DB dependency statuses, not caller-supplied worker descriptions/states. Retain arguments for compatibility if necessary but document them as advisory, and never configure trusted registry from those arguments. claim is the final same-transaction guard against stale selection. Prefer accurate blocked decision over merely claim_blocked on caller spoofing.
7. Fail closed for malformed/missing authorization policy: missing/unknown risk must never default to repo_write/read_only. Validate safety-relevant collection fields (dependencies/allowed_workers/required_capabilities list of strings) and boolean approval; avoid crash or surprising truthy coercion that silently authorizes. Admission can reject malformed tasks, or claim can return bounded invalid-policy reason for legacy malformed records.

## Acceptance tests

- Direct protected/human/unknown/missing-risk denial with a fully capable registered worker.
- Direct missing registry, unknown worker, unavailable worker, wrong risk, disallowed ID, missing explicit capability and missing task-class capability; eligible non-preferred worker succeeds.
- Each dependency status above denies; persisted completed succeeds. Forged payload status and bridge caller state cannot override row status; stale caller non-completed does not block actual completed dependency if bridge treats args advisory.
- Bridge forged worker with good capabilities/availability cannot override trusted disabled/incapable/missing entry.
- Repeat acquisition checks on renewal and expired recovery, plus reap then reacquire; use explicit legacy-row SQL fixture for protected/human historical leases, trusted registry replacement for revoked availability, and controlled dependency row status change for stale eligibility. Denied call leaves row/attempt/lease unchanged.
- Missing registry after reopening existing DB denies renewal/recovery; reopen with trusted registry succeeds for eligible task.
- Existing concurrent claim, last-attempt renewal, immutable upsert, retry budget and producer/verifier tests remain valid. Add transaction-level dependency consistency coverage if a deterministic two-connection fixture is available.

## Precise compatibility/fixture changes

- Seed test_task_ledger._task lacks risk_class: add explicit read_only to legitimate lease fixtures and constructor Worker entries for worker-a/worker-b. Preserve dedicated missing-risk negative test.
- Seed test_dryrun_orchestrator constructors need execution_workers=_workers(); those workers already cover code capability and automatic risks. Preserve separate caller inputs for spoof tests.
- Root test_autopilot_verifier_lifecycle._claimed_writer uses required_capabilities=['verification']; authorized execution registry must therefore give writer AND writer-b that capability and repo_write, without granting verifier independence. Set registry at constructor/helper, including reopened ledger helpers.
- tests/test_vega_verifier_boundaries.open_ledger similarly needs writer/writer-b execution entries with verification capability and repo_write. Preserve original assertions; fixture-only adaptation is necessary for deliberate fail-closed API change.
- Review tests/test_autopilot_lifecycle_repairs.py and migration constructors for legitimate direct claims and reopened connections; supply explicit execution workers and risks. Historical migration fixtures intentionally missing policy should be asserted denied, not made permissive by production defaults. Pure schema/no-claim tests need no registry.
- #22 may add new fixtures; update only setup necessary for execution authority, never weaken evidence assertions. No production overlap with #22 completion/evidence binding.

## Separate followup finding (outside this repair)

validate_followup compares proposed risk to AUTO_RISKS only, not parent authority; checks source_refs subset but ignores files_in_scope/files_out_of_scope and parent human gate. Reproduced parent read_only, human_approval_required=True, approved docs file with secret/ excluded; proposal repo_write, human_approval_required=False, secret/key.txt in scope, exclusions removed, identical source_refs -> (True, ()). No callsites found beyond tests so currently validation contract gap, no demonstrated runtime execution path. Queue separately under existing control-plane work; do not expand claim repair. Risk rank needs explicit approved policy; path containment/canonicalization and omitted-scope semantics need bounded specification before repair.

## Files read / uncertainty

Read AGENTS.md; task_ledger.py; dispatcher.py; dryrun_orchestrator.py; task_packet_schema.json; dispatch_policy.md; verifier_lifecycle_contract.md; orchestrator_spec.md; both worker registry JSONs; PR15 lifecycle handoff; seed ledger/dispatcher tests; root verifier lifecycle/Vega fixture excerpts. Registry JSONs differ from runtime Worker representation (classes/risk_ceiling vs capabilities/risk_classes); no loader exists here. Keep constructor registry explicit rather than invent JSON authority conversion. Genesis recovery/canonical runtime are intentionally outside assignment. Only files created: this handoff and stdlib reproduction. Next role: independent implementer, then fresh falsifier on exact head.
