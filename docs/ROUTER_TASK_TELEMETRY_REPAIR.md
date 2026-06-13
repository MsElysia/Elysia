# Router / task telemetry repair

## Starting checkpoint

**HEAD:** `1557130 fix(tests): repair ui residual expectations`

**Date:** 2026-06-13

**Scope:** Test-only repair for orchestration router telemetry adaptation (`tests/test_router_telemetry_adapt.py`). No autonomy, routes, execution paths, or core/server changes.

---

## Dirty-worktree warning

The worktree contains extensive unrelated modified and untracked files (DIRTY_SAFE). This milestone:

- Did **not** clean, restore, stash, reset, or stage unrelated files
- Did **not** use dirty runtime artifacts as proof
- Used isolated `tmp_path` SQLite telemetry stores (existing test pattern)
- Staged only the two files listed under **Files changed**

---

## Classification docs reviewed

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/TASK_ROUTER_CONTRACT_REPAIR.md`
- `docs/NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md`
- `docs/GATEWAY_SMOKE_TEST_REPAIR.md`
- `docs/UI_RESIDUAL_TEST_REPAIR.md`

---

## Targeted tests before

**Exact router telemetry cluster:**

```bash
python -m pytest tests/test_router_telemetry_adapt.py tests/test_router_rules.py tests/test_core_task_router.py -q
```

| Result | Count |
|--------|-------|
| Failed | **2** (`test_healthy_serial_kept`, `test_repeated_failures_escalate_parallel`) |
| Passed | **18** |
| Exit | 1 |

**Broad selector** (`-k "router or task or telemetry or trace"`):

| Result | Count |
|--------|-------|
| Failed | **5** (2 router telemetry + 3 out-of-scope: `test_apply_mutation_task`, `test_task_execution` ×2) |
| Passed | **48** |
| Exit | 1 |

**Selector note:** Broad `-k` pulls in task-execution and mutation-replay modules outside this milestone.

---

## Root causes (classified)

| Symptom | Classification | Fix |
|---------|----------------|-----|
| Healthy-route test sees `telemetry:yaml_default_local_first` instead of `kept_serial_due_to_healthy_local_route` | **ROUTER_TELEMETRY_SCHEMA_DRIFT** / **MISSING_TEST_FIXTURE** | `RulesRouter._coerce_ollama_ref()` resolves planner to `ollama_provider_ref()` (e.g. `llama3.2:3b`), but telemetry seeds used `model="mistral"`; `aggregate_route_metrics` filters by planner model → zero samples → insufficient-data path |
| Repeated-failure test stays on serial pipeline | **MISSING_TEST_FIXTURE** | Same model mismatch prevented `_repeated_local_failure()` from seeing seeded failures |
| `test_router_rules.py`, `test_core_task_router.py` | — | Already passing; no change |
| Broad-selector `test_apply_mutation_task` / `test_task_execution` failures | **Out of scope** | Not modified in this milestone |

---

## Files changed

| File | Change |
|------|--------|
| `tests/test_router_telemetry_adapt.py` | Autouse fixture pins `ollama_provider_ref()` to `ollama:mistral` so seeded telemetry matches router-resolved model |
| `docs/ROUTER_TASK_TELEMETRY_REPAIR.md` | This document |

**Not changed:** `config/autonomy.json`, `elysia/api/server.py`, `project_guardian/core.py`, `project_guardian/orchestration/router/policy.py`.

---

## Targeted tests after

**Exact router telemetry cluster:**

| Result | Count |
|--------|-------|
| Passed | **20** |
| Exit | 0 |

**Broad selector:**

| Result | Count |
|--------|-------|
| Failed | **3** (out-of-scope task/mutation modules only) |
| Passed | **50** |
| Exit | 1 |

---

## Tests quarantined?

**No.** In-scope router telemetry failures fixed via test fixture alignment; no `pytest.mark` quarantine.

---

## Safety proof

| Check | Result |
|-------|--------|
| Router/task safety weakened | **No** — tests only adjust telemetry seed alignment; adaptation policy unchanged |
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
| Core task router + core smoke + UI + artifact + gateway + e2e + API + review queue | 88 passed |
| Safe Observer real-planning (text) | SAFE |
| Safe Observer real-planning (`--json`) | SAFE |
| Passive Phase 2 | 92 passed |
| Safe-stack smoke | 454 passed |
| Full collection | 450 tests collected |

---

## Remaining blocker clusters

1. **Memory auto-cleanup effectiveness** — `test_auto_cleanup_effectiveness.py`
2. **`test_ui_diff_basehash.py`** — hash environment drift
3. **Broad `-k` task cluster (out of scope)** — `test_apply_mutation_task.py`, `test_task_execution.py` (RUN_ACCEPTANCE subprocess expectations)
