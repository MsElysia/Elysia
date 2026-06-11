# Review queue environment cleanup repair

## Starting checkpoint

**HEAD:** `c8941d7 fix(tests): repair gateway smoke passive contract`

**Date:** 2026-06-11

**Scope:** Review queue restart tolerance (`tests/test_review_queue_smoke.py`) and append-only latest-state contract in `ReviewQueue.list_pending()`. No autonomy, routes, or execution paths changed.

---

## Safety checks (unchanged)

| Check | Result |
|-------|--------|
| `config/autonomy.json` | **unchanged**, `"enabled": false` |
| Index at start | **clean** (no staged files) |
| Dirty runtime artifacts | **not used as proof** (`REPORTS/review_queue.jsonl` worktree drift ignored) |
| Generated runtime files staged | **No** |

---

## Classification docs reviewed

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/GATEWAY_SMOKE_TEST_REPAIR.md`
- `docs/API_APPROVAL_EXECUTION_BEHAVIOR_REPAIR.md`
- `docs/NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md`

---

## Targeted tests before

**Review queue smoke:**

```bash
python -m pytest tests/test_review_queue_smoke.py -q
```

| Result | Count |
|--------|-------|
| Failed | **1** (`TestRestartTolerance::test_restart_preserves_pending_requests`) |
| Passed | **8** |
| Exit | 1 |

**Environment selector** (`-k "review_queue or queue or restart or cleanup or environment"`):

| Result | Count |
|--------|-------|
| Failed | **7** |
| Passed | **48** |
| Exit | 1 |

**Selector note:** Broad `-k` filter pulls in artifact/run_once and memory auto-cleanup modules outside this milestone. Those failures were **not** modified here.

---

## Root causes (classified)

| Symptom | Classification | Fix |
|---------|----------------|-----|
| Approved request still in `list_pending()` after `update_status` | **REVIEW_QUEUE_CONTRACT_REGRESSION** | `list_pending()` now uses latest-state per `request_id` (same semantics as `get_request()`), not per-line scan |
| `from_dict` fragile on status-update rows with extra keys | **REVIEW_QUEUE_CONTRACT_REGRESSION** | `ReviewRequest.from_dict()` ignores `approver`/`notes`/`updated_at` append-only fields |
| Stale pending rows in append-only JSONL after restart | **STALE_RESTART_EXPECTATION** (test was correct; implementation wrong) | Contract fix + regression test `test_list_pending_uses_latest_status_not_stale_rows` |

**Not in scope (selector still failing):**

| Failure | Classification |
|---------|----------------|
| `test_artifact_policy_*.py` (2) | **TEST_EXPECTATION_OUTDATED** / artifact/run_once cluster |
| `test_auto_cleanup_effectiveness.py` (4) | **STALE_RESTART_EXPECTATION** on result dict shape (`error: None` key present) |

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/review_queue.py` | Latest-state `list_pending()`; hardened `from_dict()` |
| `tests/test_review_queue_smoke.py` | Regression test for latest-state pending filtering |
| `docs/REVIEW_QUEUE_ENVIRONMENT_CLEANUP_REPAIR.md` | This report |

**Not changed:** `config/autonomy.json`, API routes, gateway handlers, execution/autonomy code.

---

## Tests quarantined?

**No.**

---

## Targeted tests after

**Review queue smoke + unit:**

```bash
python -m pytest tests/test_review_queue_smoke.py tests/test_review_queue.py -q
```

| Result | Count |
|--------|-------|
| Passed | **14** (10 smoke + 4 unit) |
| Failed | **0** |
| Exit | 0 |

**Environment selector:**

| Result | Count |
|--------|-------|
| Passed | **50** |
| Failed | **6** (artifact ×2, auto_cleanup ×4 — out of scope) |
| Exit | 1 |

---

## Regression gates (post-repair)

| Check | Result |
|-------|--------|
| Gateway/e2e | **18 passed**, exit 0 |
| API approval | **23 passed**, exit 0 |
| Passive Phase 2 | **92 passed**, exit 0 |
| Safe Observer (text) | **SAFE**, exit 0 |
| Safe Observer (JSON) | **SAFE**, exit 0 |
| Safe-stack smoke | **454 passed**, exit 0 |
| Full collection | **450 collected**, exit 0 |

---

## Proof environment/global-state cleanup improved

- `list_pending()` no longer surfaces stale `pending` rows after approve/deny append — eliminates false pending set on restart/re-instantiation.
- Smoke tests continue to use isolated `tmp_path` queue files; no dependency on dirty `REPORTS/review_queue.jsonl`.
- New regression test locks latest-state behavior for append-only JSONL.

---

## Proof approval/gateway safety not weakened

- Change is read-path only (`list_pending`, `from_dict` parsing); no write/approve/execute behavior added.
- Monotonic status policy in `update_status()` unchanged.
- Gateway (18/18) and API approval (23/23) regression suites pass unchanged.

---

## Safety statement

- **Autonomy enabled?** No
- **Live execution run?** No
- **Tools/capabilities executed?** No
- **New API/server routes?** No
- **Execution code added?** No
- **`config/autonomy.json`:** `enabled=false`, unchanged

---

## Remaining blocker clusters

| Cluster | Status |
|---------|--------|
| Review queue restart tolerance | **Resolved** |
| Artifact/run_once policy | Open (2 failures in broad selector) |
| UI residual | Open |
| Router/task telemetry | Open |
| Memory auto-cleanup effectiveness | Open (4 failures in broad selector) |
