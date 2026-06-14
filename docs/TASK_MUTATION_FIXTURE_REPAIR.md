# Task/mutation fixture repair

## Starting checkpoint

**HEAD:** `d0b88a4 docs(tests): classify task mutation execution-adjacent failures`

**Date:** 2026-06-14

**Milestone type:** Test-only fixture repair + safe cleanup of accidental untracked file.

---

## Accidental `test.py` before cleanup

| Check | Result |
|-------|--------|
| `git status --short -- test.py` | `?? test.py` (untracked) |
| `git ls-files -- test.py` | empty (not tracked) |
| Content | `print('new')` (14 bytes) |
| Origin | `test_approval_replay_applies_mutation` during classification run — `mutation.repo_root` not bound to `tmp_path` |

---

## Cleanup action

**Command:** `del test.py` (Windows)

**Proof only accidental file removed:**

- File was **untracked** before deletion
- Content was exactly `print('new')` — matches accidental mutation payload from classification
- No other untracked files were removed
- `git status --short -- test.py` after cleanup: empty (file absent)

---

## Root causes repaired

| Test | Root cause | Fix |
|------|------------|-----|
| `test_approval_replay_applies_mutation` | MISSING_TMP_REPO_FIXTURE, MISSING_APPROVAL_FIXTURE, STALE_MUTATION_EXPECTATION | Bind `mutation.repo_root`, isolated review/approval stores under `tmp_path/REPORTS`, `_test_skip_external_storage`; assert wrapper `status`/`outcome` + tmp filesystem; assert repo-root `test.py` absent |
| `test_run_acceptance_calls_acceptance_runner` | MISSING_TMP_REPO_FIXTURE | Pass `mutations_dir=tmp_path/MUTATIONS`; subprocess remains mocked |
| `test_run_acceptance_handles_missing_script` | MISSING_TMP_REPO_FIXTURE, stale path to real `scripts/acceptance.ps1` | Pass `mutations_dir=tmp_path/MUTATIONS` so missing tmp script reaches `ACCEPTANCE_SCRIPT_NOT_FOUND` |

No production execution behavior changed.

---

## Files changed

- `tests/test_apply_mutation_task.py` — isolation helpers + approval replay fixture repair
- `tests/test_task_execution.py` — isolated `mutations_dir` for RUN_ACCEPTANCE tests
- `docs/TASK_MUTATION_FIXTURE_REPAIR.md` — this document

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`

---

## Exact task/mutation tests after repair

**Command:**

```bash
python -m pytest tests/test_apply_mutation_task.py tests/test_task_execution.py -q
```

| Outcome | Count |
|---------|-------|
| Passed | 14 |
| Failed | 0 |
| Exit code | 0 |
| Duration | ~137.6s |

---

## Repo-root `test.py` not recreated

After fixture repair test run:

- `git status --short -- test.py` — empty
- Repo-root `test.py` does not exist
- Test asserts `not (_REPO_ROOT / "test.py").exists()` in approval replay case

---

## Safety proofs

| Check | Result |
|-------|--------|
| Real repo mutation after repair | **No** — mutations confined to `tmp_path` via `repo_root` bind |
| Task/mutation safety weakened | **No** — trust gates unchanged; no production code edits |
| Execution outside isolated mocked fixtures | **No** — RUN_ACCEPTANCE subprocess mocked; APPLY_MUTATION uses isolated tmp workspace |
| Autonomy enabled | **No** — `config/autonomy.json` → `"enabled": false` (unchanged) |
| Live execution run | **No** |
| New API/server routes | **No** |
| Execution code added | **No** |

---

## Recent regression suites (post-repair)

| Suite | Result |
|-------|--------|
| UI diff + smoke | 14 passed |
| Router telemetry + core task router + core smoke | 26 passed |
| Auto cleanup effectiveness | 8 passed |
| Artifact policy run_once + reviews | 4 passed |
| Gateways smoke + e2e workflow | 18 passed |
| API approval + approval store smoke | 23 passed |
| Review queue smoke + review queue | 14 passed |
| Safe Observer (real-planning text) | SAFE, exit 0 |
| Safe Observer (real-planning JSON) | `"safe": true`, exit 0 |
| Passive Phase 2 (6 modules) | 92 passed |
| Safe-stack smoke | 454 passed |
| Full collection | 450 collected |

---

## Safety statement

- **Autonomy not enabled** — `config/autonomy.json` → `"enabled": false`
- **No live execution run**
- **No tools/capabilities executed** (beyond isolated test fixtures)
- **No new API/server routes added**
- **No execution code added**
- **Accidental untracked `test.py` removed** — not committed
- **No unrelated dirty files staged**

---

## Remaining blockers

- Full default `pytest` run may still report failures outside repaired clusters (see `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`)
- Unmocked RUN_ACCEPTANCE subprocess with trust elevation — future approval-gated executor phase
- Broader worktree dirty files remain (pre-existing, not part of this milestone)
