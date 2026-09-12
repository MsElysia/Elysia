# Artifact / run_once policy repair

## Starting checkpoint

**HEAD:** `90f7d66 fix(tests): isolate review queue environment state`

**Date:** 2026-06-12

**Scope:** Test-only repairs for artifact/run_once policy (`tests/test_artifact_policy_*.py`). No autonomy, routes, execution paths, or core/server changes.

---

## Dirty-worktree warning

The worktree contains extensive unrelated modified and untracked files (DIRTY_SAFE). This milestone:

- Did **not** clean, restore, stash, reset, or stage unrelated files
- Did **not** use dirty runtime artifacts (`REPORTS/review_queue.jsonl`, `safe.py`, etc.) as proof
- Bound all mutation/review/approval paths to `tmp_path` in artifact policy tests
- Staged only the three files listed under **Files changed**

---

## Classification docs reviewed

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/GATEWAY_SMOKE_TEST_REPAIR.md`
- `docs/REVIEW_QUEUE_ENVIRONMENT_CLEANUP_REPAIR.md`
- `docs/NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md`

---

## Targeted tests before

**Exact artifact policy files:**

```bash
python -m pytest tests/test_artifact_policy_run_once.py tests/test_artifact_policy_reviews.py tests/test_artifact_policy_coverage.py -q
```

| Result | Count |
|--------|-------|
| Failed | **4** |
| Passed | **2** |
| Exit | 1 |

**Broad selector** (`-k "artifact or run_once or changed_files or generated_reports"`):

| Result | Count |
|--------|-------|
| Failed | **5** (4 artifact + 1 UI residual) |
| Passed | **8** |
| Exit | 1 |

**Selector note:** The `-k` filter includes `tests/test_ui_smoke.py::test_run_once_creates_artifact`, which is **UI residual** and out of scope for this milestone.

---

## Root causes (classified)

| Symptom | Classification | Fix |
|---------|----------------|-----|
| `ReviewQueue(queue_path=...)` / `ApprovalStore(path=...)` | **TEST_EXPECTATION_OUTDATED** | Use `queue_file=` and `store_file=`; `update_status(id, "approved")` not `new_status=` |
| Tests expect `run_once_last.json` from `core.run_once()` | **RUN_ONCE_SCHEMA_DRIFT** | `run_once_last.json` is written by UI `/control/run-once` (`project_guardian/ui/app.py`), not `GuardianCore.run_once()`; tests now assert passive result dict + isolated filesystem effects |
| `status == "success"` on allow path | **TEST_EXPECTATION_OUTDATED** | Current passive contract uses `status == "ok"` (aligned with `tests/test_e2e_workflow.py`) |
| `status == "denied"` on invalid path | **TEST_EXPECTATION_OUTDATED** | Current contract returns `status == "error"` with `code == "MUTATION_PAYLOAD_INVALID"` |
| Mutation applied under repo root (`safe.py`) | **MISSING_TEST_ISOLATION** | `_bind_isolated_reports()` sets `mutation.repo_root` and review/approval stores under `tmp_path/REPORTS` |
| Review queue written to repo `REPORTS/` | **MISSING_TEST_ISOLATION** | Same `_bind_isolated_reports()` helper |
| `test_ui_smoke.py::test_run_once_creates_artifact` | **NEEDS_QUARANTINE** (out of scope) | UI residual cluster — not modified here |

---

## Files changed

| File | Change |
|------|--------|
| `tests/test_artifact_policy_run_once.py` | Isolated tmp stores; passive result assertions; updated status/code expectations; no `run_once_last.json` from core |
| `tests/test_artifact_policy_reviews.py` | Fixed `ReviewQueue` / `ApprovalStore` ctor kwargs and `update_status` API |
| `docs/ARTIFACT_RUN_ONCE_POLICY_REPAIR.md` | This document |

**Not changed:** `config/autonomy.json`, `elysia/api/server.py`, `project_guardian/core.py`, runtime execution code.

---

## Targeted tests after

**Exact artifact policy files:**

```bash
python -m pytest tests/test_artifact_policy_run_once.py tests/test_artifact_policy_reviews.py tests/test_artifact_policy_coverage.py -q
```

| Result | Count |
|--------|-------|
| Passed | **6** |
| Exit | 0 |

**Broad selector:**

| Result | Count |
|--------|-------|
| Failed | **1** (`test_ui_smoke.py` — out of scope) |
| Passed | **12** |
| Exit | 1 |

---

## Tests quarantined?

**No.** All in-scope artifact policy tests pass. The remaining `-k` failure is documented as UI residual, not quarantined with `pytest.mark`.

---

## Safety proof

| Check | Result |
|-------|--------|
| Artifact/run_once safety weakened | **No** — tests still forbid acceptance/subprocess artifacts; core remains passive |
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
| Safe Observer stub (text) | SAFE |
| Safe Observer stub (`--json`) | SAFE |
| Safe Observer real-planning (text) | SAFE |
| Safe Observer real-planning (`--json`) | SAFE |
| Gateway + e2e | 18 passed |
| API approval | 23 passed |
| Review queue | 14 passed |
| Passive Phase 2 | 92 passed |
| Safe-stack smoke | 454 passed |
| Full collection | 450 tests collected |

---

## Remaining blocker clusters

1. **UI residual** — `tests/test_ui_smoke.py` (`test_run_once_creates_artifact`, `test_create_mutation_path_mismatch`)
2. **Router/task telemetry** — not addressed
3. **Memory auto-cleanup effectiveness** — `test_auto_cleanup_effectiveness.py`
4. **Artifact/run_once in broad `-k`** — 1 UI failure still appears in selector; exact artifact files all pass
