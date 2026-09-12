# UI residual test repair

## Starting checkpoint

**HEAD:** `310043b fix(tests): repair artifact run-once policy`

**Date:** 2026-06-12

**Scope:** Test-only repairs for `tests/test_ui_smoke.py`. No autonomy, routes, execution paths, or core/server changes.

---

## Dirty-worktree warning

The worktree contains extensive unrelated modified and untracked files (DIRTY_SAFE). This milestone:

- Did **not** clean, restore, stash, reset, or stage unrelated files
- Did **not** use dirty runtime artifacts as proof
- Used `tmp_path` + patched `project_root` in UI tests (existing fixture pattern)
- Staged only the two files listed under **Files changed**

---

## Classification docs reviewed

- `docs/ARTIFACT_RUN_ONCE_POLICY_REPAIR.md`
- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/API_APPROVAL_EXECUTION_BEHAVIOR_REPAIR.md`

---

## UI tests before

```bash
python -m pytest tests/test_ui_smoke.py -q
```

| Result | Count |
|--------|-------|
| Failed | **2** |
| Passed | **6** |
| Exit | 1 |

Failures:

- `TestRunOnce::test_run_once_creates_artifact`
- `TestMutationCreation::test_create_mutation_path_mismatch`

**Broad selector** (`-k "ui_smoke or run_once_creates_artifact or ui"`):

| Result | Count |
|--------|-------|
| Failed | **3** (2 ui_smoke + 1 `test_ui_diff_basehash.py` — out of scope) |
| Passed | **52** |
| Exit | 1 |

**Selector note:** Broad `-k "ui"` pulls in `test_ui_diff_basehash.py` and other UI-adjacent modules outside this milestone.

---

## Root causes (classified)

| Symptom | Classification | Fix |
|---------|----------------|-----|
| `patch('project_guardian.ui.app.GuardianCore')` raises `AttributeError` | **LOCAL_ONLY_TEST_CLIENT_DRIFT** | `GuardianCore` is imported inside `run_once()` from `project_guardian.core`; patch `project_guardian.core.GuardianCore` |
| `test_create_mutation_path_mismatch` expects `touched_paths must match` | **TEST_EXPECTATION_OUTDATED** | UI validates path/content **count** first; test data (2 paths, 1 content) triggers `Number of file paths must match number of file contents` |
| `test_ui_diff_basehash.py` hash mismatch in broad selector | **ENVIRONMENT_DEPENDENT** / out of scope | Not modified in this milestone |

---

## Files changed

| File | Change |
|------|--------|
| `tests/test_ui_smoke.py` | Patch target for `GuardianCore`; updated mutation validation error assertion |
| `docs/UI_RESIDUAL_TEST_REPAIR.md` | This document |

**Not changed:** `config/autonomy.json`, `elysia/api/server.py`, `project_guardian/core.py`, `project_guardian/ui/app.py`.

---

## UI tests after

```bash
python -m pytest tests/test_ui_smoke.py -q
```

| Result | Count |
|--------|-------|
| Passed | **8** |
| Exit | 0 |

---

## Tests quarantined?

**No.** Both in-scope failures were fixed with stale-expectation updates; no `pytest.mark` quarantine added.

---

## Safety proof

| Check | Result |
|-------|--------|
| UI/artifact/run_once safety weakened | **No** — tests still mock `GuardianCore.run_once()`; no live core spin-up |
| Generated runtime artifacts staged | **No** |
| Execution/mutation/implementation in milestone | **No** — test-only changes |
| `config/autonomy.json` | **unchanged**, `"enabled": false` |
| Autonomy enabled | **No** |
| Live execution run | **No** |
| Tools/capabilities executed | **No** |
| New API/server routes | **No** |
| Execution code added | **No** |

---

## Regression verification

| Suite | Result |
|-------|--------|
| Artifact policy (`run_once` + reviews) | 4 passed |
| Gateway + e2e | 18 passed |
| API approval | 23 passed |
| Review queue | 14 passed |
| Safe Observer real-planning (text) | SAFE |
| Safe Observer real-planning (`--json`) | SAFE |
| Passive Phase 2 | 92 passed |
| Safe-stack smoke | 454 passed |
| Full collection | 450 tests collected |

---

## Remaining blocker clusters

1. **Router/task telemetry** — not addressed
2. **Memory auto-cleanup effectiveness** — `test_auto_cleanup_effectiveness.py`
3. **UI adjacent (out of scope)** — `test_ui_diff_basehash.py` still fails under broad `-k "ui"` selector (hash environment drift)
