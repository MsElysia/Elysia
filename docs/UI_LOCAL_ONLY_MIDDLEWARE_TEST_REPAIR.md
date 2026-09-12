# UI Local-Only Middleware Test Repair

## Starting checkpoint

**HEAD:** `426ff6f fix(tests): repair WebReader gateway runtime assertions`

**Date:** 2026-06-02

## Failing tests before

UI file command:

```text
python -m pytest tests/test_ui_local_only.py tests/test_ui_smoke.py \
  tests/test_ui_observability.py tests/test_ui_diff_basehash.py -q
```

**Result:** 27 failed, 6 passed (exit 1)

Procedure `-k` command:

```text
python -m pytest -q -k "local_only or local-only or middleware or ui or dashboard or status" tests/
```

**Result:** 27+ UI-related failures dominated by `assert 403 == 200`

## Root causes

| Classification | Issue |
|----------------|-------|
| **TEST_CLIENT_REMOTE_ADDR_MISSING** | Starlette `TestClient` defaults to `client=('testclient', 50000)`. `is_loopback('testclient')` is false, so local-only middleware correctly returned **403** for all default test clients. |
| **TEST_EXPECTATION_OUTDATED** | Comments assumed TestClient always appears as localhost; that was never true with current Starlette. |
| **MIDDLEWARE_BUG_LOCALHOST_BLOCKED** (minor) | `is_loopback('[::1]:8000')` failed because port stripping used `split(':')[0]`, breaking bracketed IPv6 forms. Real ASGI clients typically send `::1` without brackets; fix is defensive only. |

## Files changed

| File | Change |
|------|--------|
| `tests/ui_test_helpers.py` | **New** — `local_test_client()` with `client=('127.0.0.1', 50000)` |
| `tests/test_ui_local_only.py` | Use helper; integration test proves remote client gets 403 |
| `tests/test_ui_smoke.py` | Use `local_test_client` in fixture |
| `tests/test_ui_observability.py` | Use `local_test_client` in fixture |
| `tests/test_ui_diff_basehash.py` | Use `local_test_client` in fixture |
| `project_guardian/ui/app.py` | Narrow `is_loopback()` fix for bracketed IPv6 + single-colon IPv4 ports |

## Middleware changed?

**Yes — narrowly.** Only `is_loopback()` host parsing improved (bracketed `::1`, IPv4 port split). Middleware still rejects any non-loopback `request.client.host` with 403. No bypass for `testclient`, `X-Forwarded-For`, or remote addresses.

## Local-only protection weakened?

**No.**

## Non-local clients still blocked?

**Yes.** Verified by `test_middleware_rejects_non_loopback` using `TestClient(app, client=('192.168.1.5', 50000))` → 403.

## Tests quarantined?

**No.**

## Targeted test results after

UI files:

```text
→ 30 passed, 3 failed (exit 1)
```

All **403/local-only** failures resolved. Remaining 3 failures are **unrelated** stale expectations (GuardianCore import path, mutation error message text, hash normalization) — out of scope for this milestone.

| Module | Result |
|--------|--------|
| `test_ui_local_only.py` | **13 passed** |
| `test_ui_observability.py` | **6 passed** |
| `test_ui_diff_basehash.py` | **5 passed** (1 hash-computation test still fails — unrelated) |
| `test_ui_smoke.py` | **6 passed**, 2 failed (unrelated) |

Procedure `-k` command:

```text
→ 70 passed, 5 failed, 367 deselected (exit 1)
```

The 5 `-k` failures include 2 non-UI tests (`test_artifact_policy_reviews`, `test_elysia_api_approval_implementation`) plus the 3 unrelated UI stale-expectation tests above.

## Verification (safety baseline)

| Check | Result |
|-------|--------|
| Passive Phase 2 targeted | 92 passed, exit 0 |
| Safe Observer | exit 0, `final safety verdict: SAFE` |
| Safe-stack smoke | 454 passed, exit 0 |
| Full collection | 443 tests collected |

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged)
- Live execution **not** run
- No execution code added
- No API/server route expansion
- Local-only middleware still blocks non-loopback clients
- `project_guardian/core.py` and `elysia/api/server.py` unchanged

## Remaining blocker clusters

1. **GuardianCore singleton collisions** — full-suite `test_core_smoke` and related modules
2. **Other full-suite failures** — mutation/task execution, invariants, no-side-effects (see `docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`)
3. **Minor UI stale expectations** (3 tests) — not local-only related

## Recommended next branch

GuardianCore singleton test isolation.
