# Core Task-Router Contract Repair

## Starting checkpoint

**HEAD:** `f35a3cf docs(safety): record server phantom dirty cleanup`

**Date:** 2026-06-03

## Failing tests before

```text
python -m pytest -q -k "test_core_task_router"
→ 2 failed, 7 passed (exit 1)
```

| Test | Expected | Actual |
|------|----------|--------|
| `TestRunOnceReadyWhenTaskPresent::test_run_once_ready_when_task_present` | `status: ready` | `status: error` (`TASK_LOAD_ERROR` or `TASK_TYPE_INVALID`) |
| `TestLoadTaskContract::test_load_task_contract_success` | `status: ready` | `status: error` |

## Root causes

| Classification | Issue |
|----------------|-------|
| **TEST_EXPECTATION_OUTDATED** | Tests assumed `ready` without `TASK_TYPE:`; production `load_task_contract()` now requires exactly one whitelisted `TASK_TYPE` directive |
| **TEST_EXPECTATION_OUTDATED** | `run_once()` no longer returns legacy `ready` for loaded contracts — it executes whitelisted types or returns structured `error` |
| **MISSING_TEST_FIXTURE** | Task markdown used Unicode em-dash (`—`) without explicit UTF-8 write; on Windows this could surface as `TASK_LOAD_ERROR` (invalid UTF-8 byte `0x97`) when read as UTF-8 |
| **MISSING_TEST_FIXTURE** | Tests did not set `_test_skip_external_storage`, slowing/isolating boot unnecessarily |

Not a production regression: `test_task_execution.py` already encodes the current contract (`TASK_TYPE` required, controlled errors).

## Files changed

| File | Change |
|------|--------|
| `tests/test_core_task_router.py` | Valid `TASK_TYPE` fixtures; UTF-8 writes; `load_task_contract` ready assertions; `run_once` missing-`TASK_TYPE` error regression |
| `tests/guardian_core_test_helpers.py` | `minimal_guardian_core_test_config()`, `write_task_contract_file()` |
| `docs/TASK_ROUTER_CONTRACT_REPAIR.md` | This document |

## Production code changed?

**No.** `project_guardian/core.py` and `elysia/api/server.py` unchanged.

## Targeted results after

```text
python -m pytest -q -k "test_core_task_router"
→ 11 passed (exit 0)

python -m pytest -q -k "test_core_smoke"
→ 10 passed (exit 0)

python -m pytest project_guardian/tests/test_live_action_*.py (Phase 2 slice)
→ 92 passed (exit 0)

python scripts/run_elysia_dry_run_report.py --mode real-planning
→ SAFE, exit 0

python scripts/run_safe_stack_smoke_tests.py
→ 454 passed (exit 0)

python -m pytest --collect-only -q
→ 449 tests collected (exit 0)
```

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged)
- No live execution run; no tools/capabilities/mutation/WebScout/browser activity in this milestone
- No execution code or API/server routes added
- Task safety not weakened — missing/invalid contracts still return controlled errors; whitelisted execution unchanged
- Tests use `CLEAR_CURRENT_TASK` only inside isolated `tmp_path` sandboxes

## Remaining blockers (out of scope)

- Three unrelated UI failures (`test_ui_smoke`, mutation error text, `test_ui_diff_basehash`) if still present
- Other full-suite failures per `docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`
