# TrustMatrix Fixture Repair

## Checkpoint

**Starting HEAD:** `599af6f docs(tests): classify full runtime test status`

**Date:** 2026-06-01

## Root cause

`TrustMatrix.__init__` requires a `MemoryCore` instance (`project_guardian/trust.py`). Five gateway test modules defined a class-scoped `trust_matrix` fixture that called `TrustMatrix()` with no arguments. Pytest failed at **setup** with:

```text
TypeError: TrustMatrix.__init__() missing 1 required positional argument: 'memory'
```

This drove **54 setup errors** across the affected files (60 total in the prior full-suite classification, including overlap with suite-order effects in other modules).

The correct pattern already existed in `tests/test_mutation_path_safety.py` and `tests/test_gateways_smoke.py`: create `MemoryCore()`, then `TrustMatrix(memory)`.

## Files changed

| File | Change |
|------|--------|
| `tests/test_file_writer_path_safety.py` | `trust_matrix` fixture now depends on `memory` and passes it to `TrustMatrix` |
| `tests/test_webreader_post_json.py` | Same |
| `tests/test_webreader_target_validation.py` | Same |
| `tests/test_subprocess_background_audit.py` | Same |
| `tests/test_subprocess_runner_background.py` | Same |
| `tests/test_trust_matrix_fixture.py` | **New** — regression tests for constructor contract |

No production/runtime files changed. `project_guardian/core.py` and `elysia/api/server.py` unchanged.

## Targeted test results

### Before fix

```text
python -m pytest tests/test_file_writer_path_safety.py \
  tests/test_webreader_post_json.py \
  tests/test_webreader_target_validation.py \
  tests/test_subprocess_background_audit.py \
  tests/test_subprocess_runner_background.py -q --tb=no

→ 2 failed, 1 passed, 54 errors in 9.33s (exit 1)
```

```text
python -m pytest -q -k "TrustMatrix or trust_matrix or trustmatrix" tests/

→ 436 deselected, 5 errors in 15.71s (exit 1)
```

### After fix

```text
python -m pytest tests/test_file_writer_path_safety.py \
  tests/test_webreader_post_json.py \
  tests/test_webreader_target_validation.py \
  tests/test_subprocess_background_audit.py \
  tests/test_subprocess_runner_background.py \
  tests/test_trust_matrix_fixture.py -q --tb=no

→ 13 failed, 44 passed, 2 skipped, 0 errors in 14.37s (exit 1)
```

```text
python -m pytest -q -k "TrustMatrix or trust_matrix or trustmatrix" tests/

→ 2 failed, 3 passed, 436 deselected in 9.90s (exit 1)
```

```text
python -m pytest tests/test_trust_matrix_fixture.py -q

→ 2 passed
```

## Setup errors reduced?

**Yes.** All **54 setup errors** in the five repaired modules are eliminated. Remaining failures in those modules are **assertion/runtime** failures (approval replay, internal-host allow paths), not fixture construction errors.

Expected full-suite impact: **~54–60 fewer ERROR outcomes**; ERROR count should drop from 60 toward 0–6 depending on suite order for non-TrustMatrix modules.

## Verification (safety baseline unchanged)

| Check | Result |
|-------|--------|
| Passive Phase 2 targeted | 92 passed, exit 0 |
| Safe Observer | exit 0, `final safety verdict: SAFE` |
| Safe-stack smoke | 454 passed, exit 0 |
| Full collection | 443 tests collected (was 441; +2 regression tests) |

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged)
- Live execution **not** run
- No API/server routes added
- No execution code added
- No changes to `project_guardian/core.py` or `elysia/api/server.py`

## Remaining blocker clusters (out of scope for this milestone)

1. **UI local-only middleware** — tests expect HTTP 200, receive 403 (~27 failures)
2. **GuardianCore singleton collisions** — `test_core_smoke` and related modules fail in full suite
3. **TrustMatrix-adjacent runtime failures** — 13 failures remain in repaired gateway modules (replay/audit/internal-host behavior); require separate investigation, not fixture repair
4. **Other classified failures** — mutation/task execution, invariants, no-side-effects (see `docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`)

## Recommended next branch

Fix GuardianCore singleton test isolation, then UI local-only middleware test harness — before limited live executor design wiring.
