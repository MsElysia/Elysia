# Memory auto-cleanup effectiveness repair

## Starting checkpoint

**HEAD:** `2d4cb1c fix(tests): repair router task telemetry`

**Date:** 2026-06-13

**Scope:** Test-only repair for `tests/test_auto_cleanup_effectiveness.py`. No autonomy, routes, execution paths, or core/server changes.

---

## Dirty-worktree warning

The worktree contains extensive unrelated modified and untracked files (DIRTY_SAFE). This milestone:

- Did **not** clean, restore, stash, reset, or stage unrelated files
- Did **not** use dirty/runtime memory artifacts as proof
- Tests already use isolated `tempfile` JSON paths (not configured user memory)
- Staged only the two files listed under **Files changed**

---

## Classification docs reviewed

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md`
- `docs/ROUTER_TASK_TELEMETRY_REPAIR.md`

---

## Targeted tests before

**Exact memory cleanup file:**

```bash
python -m pytest tests/test_auto_cleanup_effectiveness.py -q
```

| Result | Count |
|--------|-------|
| Failed | **4** |
| Passed | **4** |
| Exit | 1 |

Failures:

- `test_cleanup_reduces_memory_count`
- `test_cleanup_never_increases_count`
- `test_cleanup_with_heartbeat_pulse`
- `test_consolidate_preserves_recent_memories`

**Broad selector** (`-k "auto_cleanup or cleanup or memory or retention or prune or aging or effectiveness"`):

Not run before fix (exact file failures sufficient). After fix: **49 passed**, exit 0 (includes related cleanup/memory modules; no in-scope failures).

---

## Root causes (classified)

| Symptom | Classification | Fix |
|---------|----------------|-----|
| `assert "error" not in result` fails when `result == {..., "error": None}` | **METRIC_SCHEMA_DRIFT** / **TEST_EXPECTATION_OUTDATED** | `consolidate_memories()` now always includes `error` key; success uses `error: None`. Tests updated to `_assert_cleanup_ok()` checking `result.get("error") is None` and `action != "error"` |
| Cleanup logic / effectiveness | — | **No regression** — memory counts still reduce correctly; only assertion shape was stale |

---

## Files changed

| File | Change |
|------|--------|
| `tests/test_auto_cleanup_effectiveness.py` | Added `_assert_cleanup_ok()` helper; updated 4 stale `"error" not in result` assertions |
| `docs/MEMORY_AUTO_CLEANUP_REPAIR.md` | This document |

**Not changed:** `config/autonomy.json`, `elysia/api/server.py`, `project_guardian/core.py`, `project_guardian/memory_cleanup.py`.

---

## Targeted tests after

**Exact memory cleanup file:**

| Result | Count |
|--------|-------|
| Passed | **8** |
| Exit | 0 |

**Broad selector:**

| Result | Count |
|--------|-------|
| Passed | **49** |
| Exit | 0 |

---

## Tests quarantined?

**No.** All failures fixed via test assertion alignment; no quarantine markers.

---

## Safety proof

| Check | Result |
|-------|--------|
| Real configured user memory cleaned/deleted | **No** — tests use isolated temp JSON files |
| Memory safety weakened | **No** — production cleanup code unchanged |
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
| Router + core + UI + artifact + gateway + e2e + API + review queue | 93 passed |
| Safe Observer real-planning (text) | SAFE |
| Safe Observer real-planning (`--json`) | SAFE |
| Passive Phase 2 | 92 passed |
| Safe-stack smoke | 454 passed |
| Full collection | 450 tests collected |

---

## Remaining blocker clusters

1. **`test_ui_diff_basehash.py`** — hash environment drift
2. **Out-of-scope task/mutation tests** — `test_apply_mutation_task.py`, `test_task_execution.py` from broad router/task selector
