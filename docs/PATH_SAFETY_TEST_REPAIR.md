# Core Smoke Path-Safety Test Repair

## Starting checkpoint

**HEAD:** `4aacc57 fix(tests): isolate GuardianCore singleton state`

**Date:** 2026-06-02

## Failing tests before

```text
python -m pytest -q -k "test_core_smoke"
→ 2 failed, 6 passed (exit 1)
```

| Test | Actual result |
|------|----------------|
| `test_governance_mutation_with_review_enqueues_request` | `[Guardian Core] Mutation denied: PATH_TRAVERSAL_BLOCKED` |
| `test_governance_mutation_approval_replay_succeeds` | Same |

## Root causes

| Classification | Issue |
|----------------|-------|
| **SAFE_TEMP_PATH_REJECTED** | Tests passed `str(Path(tmpdir) / "CONTROL.md")` — absolute paths outside repo root |
| **TEST_EXPECTATION_OUTDATED** | Expected review/replay behavior; path validation correctly blocked before trust/replay |
| **TEST_FIXTURE_PATH_FORMAT** (replay only) | Approval `touched_paths` used POSIX slashes while `MutationEngine` normalizes to OS separators on Windows |

Production `MutationEngine._validate_and_resolve_path` behavior is correct: reject absolute paths, reject `..`, resolve only under `repo_root`.

## Files changed

| File | Change |
|------|--------|
| `tests/guardian_core_test_helpers.py` | `repo_relative_mutation_workspace()` — repo-scoped CONTROL.md for mutations |
| `tests/test_core_smoke.py` | Mutation integration tests use relative paths; approval context uses engine-normalized path; regression tests for absolute/`..` |
| `tests/_core_smoke_workspace/.gitignore` | Ignore ephemeral workspace dirs |
| `docs/PATH_SAFETY_TEST_REPAIR.md` | This document |

## Production code changed?

**No.** Path traversal rules in `project_guardian/mutation.py` unchanged.

## Path traversal protection weakened?

**No.**

Proof (automated):

- `TestCoreSmokePathSafetyRegression::test_absolute_path_still_blocked`
- `TestCoreSmokePathSafetyRegression::test_traversal_path_still_blocked`
- Existing `tests/test_mutation_path_safety.py`, `tests/test_file_writer_path_safety.py` still pass

## Targeted results after

```text
python -m pytest -q -k "test_core_smoke"
→ 10 passed (exit 0)

python -m pytest -q -k "path_safety or traversal or PATH_TRAVERSAL or file_writer"
→ 23 passed, 4 skipped (exit 0)

python -m pytest project_guardian/tests/test_live_action_*.py (Phase 2 slice)
→ 92 passed (exit 0)

python scripts/run_elysia_dry_run_report.py --mode real-planning
→ SAFE, exit 0

python scripts/run_safe_stack_smoke_tests.py
→ 454 passed (exit 0)

python -m pytest --collect-only -q
→ 447 tests collected (exit 0)
```

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged in this commit)
- No live execution run
- No execution code added
- No API/server routes added
- `elysia/api/server.py` not modified in this commit

## Remaining blockers (out of scope)

- `test_core_task_router` — 2 failures (`ready` vs `error` task contract)
- UI — 3 unrelated failures (`test_ui_smoke`, mutation error text, `test_ui_diff_basehash`)
- Other full-suite failures per `docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`
