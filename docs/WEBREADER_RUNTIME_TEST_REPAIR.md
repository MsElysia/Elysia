# WebReader Gateway Runtime Test Repair

## Starting checkpoint

**HEAD:** `31e25fc fix(tests): repair TrustMatrix memory fixture setup`

**Date:** 2026-06-01

## Failures before

Targeted gateway command:

```text
python -m pytest tests/test_webreader_post_json.py \
  tests/test_webreader_target_validation.py \
  tests/test_file_writer_path_safety.py \
  tests/test_subprocess_background_audit.py \
  tests/test_subprocess_runner_background.py \
  tests/test_trust_matrix_fixture.py -q
```

**Result:** 13 failed, 44 passed, 2 skipped, 0 errors (exit 1)

Failure clusters:

| Cluster | Count | Symptom |
|---------|-------|---------|
| `ApprovalStore.approve()` signature | 3 | `TypeError: got multiple values for argument 'approver'` |
| WebReader fetch mocks | 5 | `assert None is not None` — `_extract_text()` rejects short/plain `"OK"` |
| WebReader `request_json` urllib mocks | 3 | `json.loads(MagicMock)` — urlopen context manager not configured |
| FileWriter path assertions | 2 | Windows `\` vs POSIX `/` in context target |
| FileWriter traversal stub test | 1 | Empty `pytest.raises` block with `pass` |
| Subprocess approval replay | 2 | `APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH` — stale global store + wrong context |

## Root causes

1. **TEST_EXPECTATION_OUTDATED — `ApprovalStore.approve`:** Tests passed `context` as the second positional argument; current signature is `approve(request_id, approver=..., notes=..., context=...)`.

2. **TEST_EXPECTATION_OUTDATED — WebReader fetch mocks:** Tests mocked `response.text = "OK"`. `WebReader._extract_text()` uses BeautifulSoup and only keeps paragraph text **> 10 characters**, so fetch returned `None`.

3. **TEST_EXPECTATION_OUTDATED — `request_json` urllib mocks:** `request_json` uses `with urllib.request.urlopen(...) as response`. Plain `MagicMock` return values did not implement `__enter__`/`__exit__`, so `read()` returned another `MagicMock` instead of JSON bytes.

4. **TEST_EXPECTATION_OUTDATED — FileWriter paths:** Runtime reports native Windows separators; tests asserted POSIX `/` literals.

5. **TEST_EXPECTATION_OUTDATED — traversal test stub:** `test_blocks_path_outside_repo_via_resolve` contained an empty `pytest.raises` block and never exercised traversal blocking.

6. **NEEDS_INVESTIGATION → fixed — subprocess replay:** Hard-coded `request_id="test-request-123"` collided with entries in the shared `REPORTS/approval_store.json`. Approval silently no-oped when ID already existed; replay context hash did not match.

## Files changed

| File | Change |
|------|--------|
| `tests/gateway_test_helpers.py` | **New** — shared fetch/urllib mocks for gateway tests |
| `tests/test_webreader_post_json.py` | Fixed approve signature, gate context, urllib context-manager mocks |
| `tests/test_webreader_target_validation.py` | HTML fetch mocks via helper; urllib JSON mock for internal allow test |
| `tests/test_file_writer_path_safety.py` | Real traversal assertion; POSIX-normalized path checks |
| `tests/test_subprocess_background_audit.py` | Isolated approval store; enqueue+approve replay flow |
| `tests/test_subprocess_runner_background.py` | Isolated approval store; enqueue+approve replay flow |

No production/runtime files changed. Target validation logic unchanged.

## Targeted test result after

```text
python -m pytest tests/test_webreader_post_json.py \
  tests/test_webreader_target_validation.py \
  tests/test_file_writer_path_safety.py \
  tests/test_subprocess_background_audit.py \
  tests/test_subprocess_runner_background.py \
  tests/test_trust_matrix_fixture.py -q

→ 57 passed, 2 skipped in 15.13s (exit 0)
```

## Tests quarantined?

**No.** All failures were repaired via test/fixture updates. No skips added beyond existing platform skips.

## Target validation weakened?

**No.** Internal-host blocking, scheme validation, and TrustMatrix gating behavior were not modified. Tests now mock network responses correctly without bypassing SSRF checks.

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
- No API/server routes added
- No execution code added
- Target validation **not** weakened
- `project_guardian/core.py` and `elysia/api/server.py` unchanged

## Remaining blocker clusters

1. **UI local-only middleware** — tests expect HTTP 200, receive 403 (~27 failures)
2. **GuardianCore singleton collisions** — `test_core_smoke` and related modules in full suite
3. **Other full-suite failures** — mutation/task execution, invariants, no-side-effects (see `docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`)

## Recommended next branch

GuardianCore singleton test isolation, then UI local-only middleware test harness.
