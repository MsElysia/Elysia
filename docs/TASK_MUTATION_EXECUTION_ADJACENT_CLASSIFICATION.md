# Task/mutation execution-adjacent classification

## Starting checkpoint

**HEAD:** `7c7f0e1 fix(tests): repair ui diff basehash drift`

**Date:** 2026-06-13

**Milestone type:** Documentation/classification only — no test or source repairs in this commit.

**Index:** Clean (no staged files at milestone start).

**Worktree:** Many pre-existing unrelated dirty files; not used as proof and not staged.

---

## Classification docs reviewed

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/ROUTER_TASK_TELEMETRY_REPAIR.md`
- `docs/NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md`
- `docs/ARTIFACT_RUN_ONCE_POLICY_REPAIR.md`
- `docs/API_APPROVAL_EXECUTION_BEHAVIOR_REPAIR.md`

---

## Exact tests inspected

| File | Tests collected |
|------|-----------------|
| `tests/test_apply_mutation_task.py` | 7 |
| `tests/test_task_execution.py` | 7 |
| **Total** | **14** |

**Command:**

```bash
python -m pytest tests/test_apply_mutation_task.py tests/test_task_execution.py -q -v
```

**Raw output (local, not committed):** `REPORTS/_task_mutation_classification_before.txt`

---

## Exact test results

| Outcome | Count |
|---------|-------|
| Passed | 11 |
| Failed | 3 |
| Exit code | 1 |
| Duration | ~151.6s |

### Passing tests (11) — aligned with passive safety phase

These use `tmp_path` for CONTROL/TASKS/MUTATIONS (where applicable) and assert structured **error**, **denied**, or **needs_review** contracts. No live repo mutation or subprocess execution required.

| Test | Asserts |
|------|---------|
| `TestInvalidContract::test_bad_mutation_file_path_returns_error` | `TASK_CONTRACT_INVALID` |
| `TestInvalidContract::test_mutation_file_not_under_mutations_returns_error` | path under MUTATIONS/ |
| `TestInvalidPayload::test_touched_paths_mismatch_returns_error` | `MUTATION_PAYLOAD_INVALID` |
| `TestProtectedPathWithoutOverride::test_protected_path_without_override_returns_denied` | `denied` / `MUTATION_DENIED` |
| `TestReviewFlow::test_review_flow_returns_needs_review` | `needs_review` + `request_id` |
| `TestPathSafety::test_path_with_dotdot_returns_error` | `MUTATION_PAYLOAD_INVALID` |
| `TestUnknownTaskType::test_unknown_task_type_returns_error` | `TASK_TYPE_INVALID` |
| `TestMissingTaskType::test_missing_task_type_returns_error` | missing directive |
| `TestMultipleTaskTypes::test_multiple_task_types_returns_error` | multiple directives |
| `TestClearCurrentTask::test_clear_current_task_updates_control` | CONTROL.md → NONE (tmp only) |
| `TestClearCurrentTask::test_clear_current_task_creates_control_if_missing` | CONTROL.md creation (tmp only) |

---

## Failing tests — per-test classification

### 1. `TestApprovalReplay::test_approval_replay_applies_mutation`

**Failure:** `KeyError: 'changed_files'` at line 263 (after `status=="ok"` and `outcome=="mutation_applied"` passed).

**Log evidence:** `[Guardian Mutation] test.py updated from GuardianCore.`

**Expected live execution/mutation?** **Yes** — test intends approved-replay APPLY_MUTATION with filesystem write under an isolated workspace.

**Root cause (multi-factor):**

| Factor | Classification | Detail |
|--------|----------------|--------|
| Wrapper schema drift | **STALE_MUTATION_EXPECTATION** | `_execute_apply_mutation` returns `changed_files`, but `run_once()` on `status=="ok"` only forwards `status`, `current_task`, `task_type`, `outcome`, `exit_code` (see `core.py` ~8211–8217). Test expects `changed_files` on the `run_once` wrapper. |
| Repo root not bound | **MISSING_TMP_REPO_FIXTURE** | Test passes `mutations_dir=tmp_path/MUTATIONS` but never calls `_bind_mutation_repo_root(core, tmp_path)` (pattern in `tests/test_e2e_workflow.py`). `MutationEngine.repo_root` defaults to real project root, so mutation wrote **`test.py` at repo root**, not `tmp_path/test.py`. |
| Store isolation | **MISSING_APPROVAL_FIXTURE** | Review queue / approval store use default on-disk paths; not isolated to `tmp_path`. |

**Safe tmp fixture could repair?** **Yes** — bind `core.mutation.repo_root = tmp_path`, isolated `queue_file` / `store_file`, `_test_skip_external_storage: True`; assert filesystem under `tmp_path` (e2e pattern) instead of `result["changed_files"]` on wrapper.

**Phase:** **Current passive safety phase** for contract repair (isolated tmp + passive wrapper assertions). Approval-replay *behavior* is already implemented; test isolation and assertion shape are stale.

**Recommended handling:** Next repair milestone — isolate fixture; assert `status=="ok"`, `outcome=="mutation_applied"`, and `tmp_path/test.py` content; drop or relocate `changed_files` assertion to `_execute_apply_mutation` direct call if needed. **Do not weaken approval gates.**

**Unsafe side effect observed:** Real repo-root `test.py` was created/updated during classification run. Accidental test isolation defect — **not** intentional milestone behavior. Do not treat dirty `test.py` as proof.

---

### 2. `TestRunAcceptance::test_run_acceptance_calls_acceptance_runner`

**Failure:** Command path is real repo `...\Project guardian\scripts\acceptance.ps1`, not tmp `...\scripts\acceptance.ps1`.

**Expected live execution?** **Partial** — subprocess is **mocked** (`patch.object(core.subprocess_runner, 'run_command')`); no real PowerShell ran. Test expects correct **path resolution** to tmp workspace script.

**Root cause:**

| Factor | Classification | Detail |
|--------|----------------|--------|
| Missing mutations_dir | **MISSING_TMP_REPO_FIXTURE** | Test creates `tmp_path/scripts/acceptance.ps1` but does **not** pass `mutations_dir=tmp_path/MUTATIONS`. `_execute_run_acceptance` resolves script via `self.mutations_dir.parent / "scripts" / "acceptance.ps1"`, which defaults to **real project root**. |
| Subprocess mock | Safe | Mock was invoked; `status=="ok"` path likely reached with wrong script path. |

**Safe tmp fixture could repair?** **Yes** — pass `mutations_dir=tmp_path/MUTATIONS` (and optionally `_test_skip_external_storage: True`).

**Phase:** **Current passive safety phase** — test-only fixture fix; no executor implementation required.

**Recommended handling:** Add `mutations_dir=tmp_path/MUTATIONS` to RUN_ACCEPTANCE tests; keep subprocess mocked. Full unmocked acceptance subprocess belongs to **future approval-gated executor** phase.

---

### 3. `TestRunAcceptance::test_run_acceptance_handles_missing_script`

**Failure:** Expected `status=="error"`, `code==ACCEPTANCE_SCRIPT_NOT_FOUND`; got `status=="denied"`.

**Log evidence:** `Insufficient trust for subprocess_execution by SubprocessRunner (trust: 0.500, required: 0.900)` — real repo `scripts/acceptance.ps1` **exists**, so trust gate runs before script-not-found path.

**Expected live execution?** **No** — test expects early error when script missing in tmp workspace.

**Root cause:**

| Factor | Classification | Detail |
|--------|----------------|--------|
| Missing mutations_dir | **MISSING_TMP_REPO_FIXTURE** | Same as test #2 — resolves to real project root where `scripts/acceptance.ps1` exists. |
| Trust deny before script check | **SAFETY_POLICY_EXPECTED_BLOCK** | With real script present, SubprocessRunner trust correctly **denies** (0.500 < 0.900). Not a passive-contract regression. |
| Stale error code expectation | **STALE_MUTATION_EXPECTATION** | Test written for script-not-found path that never runs when real script is found. |

**Safe tmp fixture could repair?** **Yes** — with `mutations_dir=tmp_path/MUTATIONS` and no tmp script, should reach `ACCEPTANCE_SCRIPT_NOT_FOUND`. Alternatively, document dual path: if real script exists, expect `denied` under default trust (policy-correct).

**Phase:** **Current passive safety phase** for fixture fix; trust/subprocess live execution deferred.

**Recommended handling:** Pass `mutations_dir=tmp_path/MUTATIONS`; reassert `ACCEPTANCE_SCRIPT_NOT_FOUND`. If testing trust-deny path separately, mock trust or use explicit trust fixture — do not lower trust threshold in production code.

---

## Summary classification table

| Test | Primary classification | Secondary | Live execution expected? | Tmp fixture fixes? | Phase |
|------|------------------------|-----------|--------------------------|-------------------|-------|
| `test_approval_replay_applies_mutation` | STALE_MUTATION_EXPECTATION | MISSING_TMP_REPO_FIXTURE, MISSING_APPROVAL_FIXTURE | Yes (isolated) | Yes | Passive contract repair |
| `test_run_acceptance_calls_acceptance_runner` | MISSING_TMP_REPO_FIXTURE | — | Mocked only | Yes | Passive contract repair |
| `test_run_acceptance_handles_missing_script` | MISSING_TMP_REPO_FIXTURE | SAFETY_POLICY_EXPECTED_BLOCK, STALE_MUTATION_EXPECTATION | No | Yes | Passive contract repair |

**Not classified as:**

- **PASSIVE_CONTRACT_REGRESSION** — core deny/review/error paths match expectations for the 11 passing tests; failures are fixture/assertion drift.
- **EXECUTOR_NOT_IMPLEMENTED_YET** — APPLY_MUTATION and RUN_ACCEPTANCE handlers exist; tests lack isolation.
- **NEEDS_QUARANTINE** — repairs are straightforward test-only fixture updates; no quarantine unless repair milestone is deferred.
- **STALE_UNSAFE_EXECUTION_EXPECTATION** — no test requires disabling safety gates; approval replay test accidentally hit real repo due to missing `repo_root` bind.

---

## Unsafe real repo mutation/execution during classification run

| Check | Result |
|-------|--------|
| Real repo mutation attempted? | **Yes** — `test_approval_replay_applies_mutation` wrote repo-root `test.py` (`print('new')`) because `mutation.repo_root` was not bound to `tmp_path`. |
| Live subprocess/PowerShell? | **No** — RUN_ACCEPTANCE tests use mocked `SubprocessRunner.run_command`. |
| Autonomy loop? | **No** |
| Tools/capabilities/WebScout/browser? | **No** |

Classification run should have been stopped or isolated before approval-replay test; documented here for safety audit. **Do not stage or commit** accidental `test.py` or other runtime artifacts.

---

## Recommended next milestone

**Title:** `fix(tests): isolate task/mutation execution-adjacent fixtures`

**Scope (test-only):**

1. **`test_approval_replay_applies_mutation`**
   - `_bind_mutation_repo_root(core, tmp_path)` (from `tests/test_e2e_workflow.py`)
   - Isolated review queue / approval store paths
   - `_test_skip_external_storage: True`
   - Assert filesystem under `tmp_path`; assert wrapper `status`/`outcome` only (not `changed_files` on `run_once`)

2. **`test_run_acceptance_*`**
   - Pass `mutations_dir=tmp_path/MUTATIONS` in both RUN_ACCEPTANCE tests
   - Keep subprocess mocked in happy path

3. **Optional cleanup:** Remove or ignore accidental repo-root `test.py` in a separate operator action (not this milestone).

**Out of scope (future approval-gated executor):**

- Unmocked RUN_ACCEPTANCE subprocess with trust elevation
- Live autonomy `run_once` loops
- API `/implement` execution paths

**Reuse patterns from prior repairs:**

- `_bind_mutation_repo_root` — `tests/test_e2e_workflow.py`
- `_test_skip_external_storage: True` — artifact/run_once repairs
- ReviewQueue `queue_file=`; ApprovalStore `store_file=`
- Wrapper vs executor result fields — `docs/ARTIFACT_RUN_ONCE_POLICY_REPAIR.md`

---

## Remaining blockers after this milestone

- **3 failing tests** in `test_apply_mutation_task.py` / `test_task_execution.py` (fixture + assertion repair)
- Accidental repo-root `test.py` from classification run (operator cleanup)
- Broader full-runtime collection may still report failures outside this cluster (see `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`)

---

## Safety statement

- **Autonomy not enabled** — `config/autonomy.json` → `"enabled": false` (unchanged)
- **No live execution run** — no autonomy mode, no unmocked subprocess acceptance
- **No intentional real repo mutation** — one accidental write documented; not staged
- **No tools/capabilities executed** — classification + passive safety checks only
- **No new API/server routes added**
- **No execution code added** — `elysia/api/server.py` and `project_guardian/core.py` untouched in this milestone
- **No mutation/task safety weakened**
- **No unrelated dirty files staged**
