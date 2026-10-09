# Bounded integration worker — Issue #112

Authority: [Issue #11](https://github.com/MsElysia/Elysia/issues/11).
This is a disposable worker and evidence adapter, not a scheduler, ledger,
governance release mechanism, or second control plane. Its result maps to the
existing task packet's `review` status. `READY_FOR_MERGE_REVIEW` is an integration
result, never a task completion, release, or merge authorization. Existing task,
completion, and state-transition contracts remain unchanged.

## Adopt / adapt / build

Inspected the seed `AGENTS.md`, task/completion schemas, orchestrator and state
machine; the disabled GitHub synchronization contract; current Safe Stack runner
and PR #100/#101's exact-event-head checkout pattern; and the seed validation
workflow. Reuse Git worktrees, binary Git patches, GitHub draft PRs, Actions,
pytest, existing Safe Stack registration, and the existing packet/handoff format.
No TaskLedger, dispatcher, executor, provider, runtime or memory wiring is added.
Only the patch/provenance, hosted evidence, and independent-verdict glue is new.
The seed validation workflow's stale nonexistent root test glob is replaced by
the existing six state-machine regressions and this worker's tests; its checkout
also adopts the existing exact-event-head pattern. No suite is silently skipped.

Implementation is isolated above seed `136932ad7974d1349d96ea41acbdb3d67759d646`.
The implementation PR is separate from any production consolidation PR.

## Start one bounded run

From an exact reviewed integration-tool checkout:

```text
python elysia_collective_seed/autopilot/integration.py start --plan plan.json --repo SOURCE_CHECKOUT --destination NEW_ISOLATED_WORKTREE --producer BUILDER_ID --trust OPERATOR_VERIFIER_TRUST.json --receipts RECEIPT_DIRECTORY --result result.json
```

The worker first validates the entire plan and pinned Issue #11 checkpoint,
checks current open/draft source PR heads, and verifies prerequisite signatures.
Only then does it create one branch, apply explicit patches, make one commit,
reconstruct the expected tree, push that exact SHA, and create one draft PR.
It produces `VERIFYING` with provenance. There is no merge command.

The plan is JSON with these required fields:

```json
{
  "control_plane": "https://github.com/MsElysia/Elysia/issues/11",
  "issue": 112,
  "task_id": "ELY-TASK-000112",
  "toolkit_sha": "EXACT_40_HEX_REVIEWED_TOOL_COMMIT",
  "checkpoint_comment": 6089305304,
  "checkpoint_sha256": "SHA256_OF_EXACT_COMMENT_BODY",
  "verification_epoch": 1791576000,
  "base": {"pr": 110, "sha": "EXACT_40_HEX_BASE"},
  "sources": [{"pr": 101, "sha": "EXACT_40_HEX_SOURCE"}],
  "changes": [{
    "source_pr": 101,
    "from": "EXPLICIT_RANGE_BASE_SHA",
    "to": "EXPLICIT_RANGE_END_SHA",
    "files": ["project_guardian/example.py"],
    "scope": "Approved unique behavior; explain what is excluded",
    "patch_sha256": "SHA256_OF_GIT_DIFF_BYTES"
  }],
  "tests": [{"id": "safe-stack", "runner": "safe-stack", "paths": []}],
  "independent_verifier_required": true,
  "closed_gates": ["merge", "deploy", "permissions", "runtime", "providers", "autonomy", "live_memory", "external_action", "governance_release", "local_sync"]
}
```

This illustrative plan is deliberately not executable. Do not materialize the
#110 + #101 composition while #110's fresh independent exact-SHA PASS is pending.
The first base remains `700cbfebf13686f776cd904da8f27ec0dfe05455`; the source
remains #101 `71ac66c3c9d4a4f4f68922941563db85618a2922`. Only its unique explicit
Guardian activation behavior, disabled-autonomy diagnostic/event-memory fence,
necessary tests and Safe Stack registration are eligible. Preserve all #110
Windows/POSIX transaction behavior. Superseded prerequisite commits are excluded.

Patch bytes are produced by `git diff --binary --full-index FROM TO -- FILES`.
Their SHA256 must match the approved plan exactly. Each range must belong to the
pinned source lineage. A single squashed composition commit must have the exact
base as its sole parent; its tree must exactly equal reapplying all listed
patches. Empty/duplicate patches, missing files, extra content/history, protected
paths, symlinks and submodules fail closed. Semantic review remains mandatory;
path selection alone is not proof of authorized behavior.

## Verifier evidence and trust

No production verifier key or trust file is shipped. The unresolved project
human/governance trust anchor is not solved by this implementation. The separate
operator-provisioned trust adapter authenticates bounded technical evidence only.
Do not infer trust from an owner account, agent name, comment text or receipt.
An unconfigured adapter blocks the run.

Trust file (outside the plan and candidate checkout):

```json
{
  "allowed_signers": "ABSOLUTE_PATH_TO_OPERATOR_PROVISIONED_SSH_ALLOWED_SIGNERS",
  "checkpoint_comment": 6089305304,
  "minimum_verification_epoch": 1791576000,
  "producers": {"builder": {"group": "implementation"}},
  "verifiers": {"reviewer": {"group": "independent-review"}}
}
```

`allowed_signers` uses OpenSSH's allowed-signers format. The operator must bind
the listed identities to actual independent keys and groups. Producer keys must
not appear as independent verifier keys. Configuration changes are outside this
task; an agent may not self-provision production trust.

Receipts `pr-110.json`, `pr-101.json`, and later `composed.json`:

```json
{"subject":"EXACT_REVIEWED_SHA","scope":"SHA256_OF_CANONICAL_PLAN","verdict":"PASS","verifier":"reviewer","issued_at":1791576000,"evidence":["durable independent exact-SHA review reference"]}
```

Sign the canonical JSON bytes (sorted keys, compact separators, UTF-8) with
`ssh-keygen -Y sign -n elysia-issue11-integration -f VERIFIER_PRIVATE_KEY RECEIPT`.
The detached signature is `RECEIPT.json.sig`. The verifier creates the receipt,
never the producer. Subject, entire plan, freshness epoch, signer identity and
separate group must match. FAIL, PARTIAL, unsigned, missing, stale or wrong-scope
receipts block promotion. Historical prose PASS cannot be automatically imported.

## Exact-head hosted evidence and final verification

`start` automatically pushes a deterministic `integration-evidence/…` request
branch above the exact reviewed tool commit. That branch has one new commit
containing only `integration-request.json` (plan, candidate and tool SHA). This
launches `.github/workflows/bounded-integration.yml` through a push event while
the tool remains draft and unmerged; no workflow installation on `main` or
second PR is necessary. The result records the request branch/SHA. Find its run
with `gh run list --repo MsElysia/Elysia --branch REQUEST_BRANCH`.
The workflow validates the request's sole parent and unchanged tool tree,
checks out the exact candidate, reconstructs
the entire patch tree, and runs every named required suite on Linux and Windows.
It uploads platform-specific `evidence.json`. Permissions are read-only, checkout
credentials are not persisted, and test commands are limited to pytest files and
the existing Safe Stack runner. This is intended for already independently
reviewed bounded candidate code on disposable hosted runners; it is not a sandbox
for arbitrary hostile code. No live/user data or secrets may be made available.

After the composed exact SHA receives fresh independent signed PASS:

```text
python elysia_collective_seed/autopilot/integration.py finish --plan plan.json --repo COMPOSED_WORKTREE --candidate EXACT_COMPOSED_SHA --producer BUILDER_ID --trust OPERATOR_VERIFIER_TRUST.json --receipts RECEIPT_DIRECTORY --toolkit EXACT_REVIEWED_TOOL_SHA --run-id HOSTED_RUN_ID --result result.json
```

Both mandatory hosted jobs, correct workflow/event/tool SHA, exact candidate,
identical plan digest, every required test and signed composed verdict are
mandatory. Only `READY_FOR_MERGE_REVIEW` can result. Operator merge authority and
every protected gate remain closed. After merge, local sync is a separate later
operator task. Nothing here performs it.

## Retry, repair and handoff

Keep plan, trust, receipts and result files outside the clean tool and candidate
checkouts. Plan digest determines the branch. `start` refuses existing destinations/branches
without resetting or overwriting. Once a candidate exists, `resume` uses the same
arguments as `finish` except toolkit/run-id are unnecessary; it rechecks source
gates, parent/tree, remote branch and existing PR before returning `VERIFYING`.
It reuses exactly one matching open draft PR; conflicting/closed/non-draft PRs
block. Remote candidate branches must exactly match; no advancing or overwriting
an existing branch is allowed. CI request branches are also reused only after
their sole parent and JSON content are revalidated. A failure before commit preserves the isolated checkout for inspection;
repair requires an explicit revised plan and fresh receipts, never silent reset.

Persist the result alongside the existing Issue #112 task/completion handoff.
It is evidence, not authority. Existing Issue #11 history and draft PRs are not
edited. Failure returns `BLOCKED_REPAIR_REQUIRED` with evidence/reason. Missing
keys/CI/verdicts stay blocked; no automatic governance or merge escalation occurs.

## Tests

`python -m pytest -q elysia_collective_seed/autopilot/test_integration.py`

Synthetic repositories only. Production #110/#101 composition is not exercised.
