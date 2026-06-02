# GuardianCore Singleton Test Isolation

## Starting checkpoint

**HEAD:** `74031e0 fix(tests): repair local-only UI middleware expectations`

**Date:** 2026-06-02

## Failing behavior before

### `test_core_smoke` (isolation symptom)

```text
python -m pytest -q -k "test_core_smoke" tests/
→ 7 failed, 1 passed (exit 1)
```

First test passed; subsequent tests failed with:

```text
RuntimeError: GuardianCore instance already exists ...
```

### Broader singleton subset

```text
python -m pytest -q -k "core_smoke or GuardianCore or guardian_core or singleton" tests/
→ 9 failed, 9 passed (exit 1)
```

Includes stale `UnifiedElysiaSystem` import from `run_elysia_unified` (class moved to `elysia.py`).

## Root causes

| Classification | Issue |
|----------------|-------|
| **TEST_LEAKS_SINGLETON_STATE** | `GuardianCore._any_instance_initialized` class flag and `guardian_singleton._guardian_core_instance` not reset between tests in `tests/` |
| **MISSING_RESET_FIXTURE** | `test_core_smoke.py` and `test_core_task_router.py` constructed multiple `GuardianCore()` instances per module without `allow_multiple=True` or teardown |
| **MOCK_PATH_STALE** | Unified/interface singleton tests imported `UnifiedElysiaSystem` from deprecated `run_elysia_unified.py` |

Not singleton (remain failing):

| Test | Classification | Reason |
|------|----------------|--------|
| `test_governance_mutation_with_review_enqueues_request` | TEST_EXPECTATION_OUTDATED | Absolute temp path blocked by `PATH_TRAVERSAL_BLOCKED` |
| `test_governance_mutation_approval_replay_succeeds` | TEST_EXPECTATION_OUTDATED | Same path-safety mismatch |
| `test_run_once_ready_when_task_present` | NEEDS_INVESTIGATION | Task router returns `error` not `ready` (unrelated to singleton) |
| `test_load_task_contract_success` | NEEDS_INVESTIGATION | Same |

## Files changed

| File | Change |
|------|--------|
| `tests/guardian_core_test_helpers.py` | **New** — `reset_guardian_core_test_state()`, `minimal_unified_elysia_system()` |
| `tests/conftest.py` | Autouse fixture resets singleton state before/after each test in `tests/` |
| `tests/test_guardian_core_isolation.py` | **New** — regression tests for reset behavior |
| `tests/test_guardian_singleton.py` | Updated unified+singleton test to use `elysia.py` helper |
| `tests/test_unified_interface_no_double_init.py` | Same; removed stale `run_elysia_unified` import |

## Production code changed?

**No.** `project_guardian/core.py` and `guardian_singleton.py` unchanged. Existing `reset_singleton()` reused from tests only.

## Targeted test results after

```text
python -m pytest -q -k "test_core_smoke" tests/
→ 2 failed, 6 passed (exit 1) — failures are path-safety, not singleton
```

```text
python -m pytest tests/test_guardian_singleton.py tests/test_unified_interface_no_double_init.py tests/test_guardian_core_isolation.py -q
→ 13 passed (exit 0)
```

```text
python -m pytest -q -k "core_smoke or guardian_singleton or unified_interface_no_double_init or guardian_core_isolation" tests/
→ 2 failed, 19 passed (exit 1)
```

Singleton collision failures: **eliminated**. Remaining 2 failures in `test_core_smoke` are mutation path validation (out of scope).

## Verification (safety baseline)

| Check | Result |
|-------|--------|
| Passive Phase 2 targeted | 92 passed, exit 0 |
| Safe Observer | exit 0, `final safety verdict: SAFE` |
| Safe-stack smoke | 454 passed, exit 0 |
| Full collection | 445 tests collected (+2 isolation tests) |

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` unchanged, `"enabled": false`)
- Live execution **not** run
- No API/server routes added
- No execution code added
- Runtime singleton semantics **unchanged** for production paths

## Remaining blocker clusters

1. **Three unrelated UI test failures** (GuardianCore mock path, error message text, hash normalization)
2. **Mutation path / task-router test expectations** in `test_core_smoke` / `test_core_task_router` (2+2 failures)
3. **Other full-suite failures** per `docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`

## Recommended next branch

Fix mutation path test fixtures (use repo-relative paths under temp `MUTATIONS/`) or quarantine stale governance-mutation tests.
