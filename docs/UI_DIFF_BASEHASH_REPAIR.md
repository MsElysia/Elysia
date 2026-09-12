# UI diff / basehash repair

## Starting checkpoint

**HEAD:** `96b18a1 fix(tests): repair memory auto-cleanup effectiveness`

**Date:** 2026-06-13

**Scope:** Test-only repair for `tests/test_ui_diff_basehash.py`. No autonomy, routes, execution paths, or core/server changes.

---

## Dirty-worktree warning

The worktree contains extensive unrelated modified and untracked files (DIRTY_SAFE). This milestone:

- Did **not** clean, restore, stash, reset, or stage unrelated files
- Did **not** use dirty/runtime artifacts as proof
- Tests use isolated `tmp_path` project roots via existing fixture pattern
- Staged only the two files listed under **Files changed**

---

## Classification docs reviewed

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/UI_RESIDUAL_TEST_REPAIR.md`
- `docs/ARTIFACT_RUN_ONCE_POLICY_REPAIR.md`
- `docs/MEMORY_AUTO_CLEANUP_REPAIR.md`

---

## Targeted tests before

```bash
python -m pytest tests/test_ui_diff_basehash.py -q
```

| Result | Count |
|--------|-------|
| Failed | **1** (`test_payload_creation_includes_base_hashes`) |
| Passed | **5** |
| Exit | 1 |

**Broad selector** (`-k "ui_diff or basehash or diff_basehash or base_hash"`):

Not run before fix; after fix: **6 passed**, exit 0.

---

## Root causes (classified)

| Symptom | Classification | Fix |
|---------|----------------|-----|
| Expected SHA256 `2d5430…` vs actual `a7f798…` | **NEWLINE_NORMALIZATION_DRIFT** / **ENVIRONMENT_DEPENDENT** (Windows) | Test hashed string literal with `\n`; `Path.write_text()` on Windows wrote `\r\n`; UI reads file with `rb` and hashes on-disk bytes. Expected hash now derived from `test_file.read_bytes()` after write |
| Other diff/basehash tests | — | Already passing (mismatch warnings, legacy payload, detail page) |

Production behavior is correct and deterministic for on-disk bytes; only the test expectation was stale.

---

## Files changed

| File | Change |
|------|--------|
| `tests/test_ui_diff_basehash.py` | Compute expected base hash from on-disk bytes after `write_text` |
| `docs/UI_DIFF_BASEHASH_REPAIR.md` | This document |

**Not changed:** `config/autonomy.json`, `elysia/api/server.py`, `project_guardian/core.py`, `project_guardian/ui/app.py`.

---

## Targeted tests after

```bash
python -m pytest tests/test_ui_diff_basehash.py -q
```

| Result | Count |
|--------|-------|
| Passed | **6** |
| Exit | 0 |

---

## Tests quarantined?

**No.** Single failure fixed via deterministic on-disk hash alignment.

---

## Safety proof

| Check | Result |
|-------|--------|
| Diff/basehash safety weakened | **No** — production hash logic unchanged |
| Mutation applied in tests | **No** — only passive payload creation + diff viewing |
| Generated runtime artifacts staged | **No** |
| Execution/mutation/implementation in milestone | **No** |
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
| UI smoke | 8 passed |
| Router + core + cleanup + artifact + gateway + e2e + API + review queue | 93 passed |
| Safe Observer real-planning (text) | SAFE |
| Safe Observer real-planning (`--json`) | SAFE |
| Passive Phase 2 | 92 passed |
| Safe-stack smoke | 454 passed |
| Full collection | 450 tests collected |

---

## Remaining blocker clusters

1. **`test_apply_mutation_task.py`** — out-of-scope task/mutation cluster
2. **`test_task_execution.py`** — out-of-scope RUN_ACCEPTANCE subprocess expectations
