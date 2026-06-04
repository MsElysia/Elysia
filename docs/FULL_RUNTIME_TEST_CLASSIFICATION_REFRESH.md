# Full Runtime Test Classification Refresh

## Starting checkpoint (repair baseline)

**HEAD:** `132eacc fix(tests): repair core task-router contract expectations`

**Classification run HEAD:** `a0455c7 docs(browser): triage cloudflare captcha fail-closed handling` (docs-only commits after repair baseline; no runtime behavior change)

**Date:** 2026-06-04

## Why this refresh was needed

`docs/FULL_RUNTIME_TEST_CLASSIFICATION.md` (2026-05-30, pre-repair) reported **441 collected**, **265 passed / 107 failed / 60 errors**. Multiple targeted repair milestones landed since then:

- TrustMatrix memory fixture (`31e25fc`)
- WebReader gateway runtime assertions (`426ff6f`)
- UI local-only middleware (`74031e0`)
- GuardianCore singleton isolation (`4aacc57`)
- Core smoke path-safety (`8ec3bc7`)
- Core task-router contract (`132eacc`)

This refresh re-runs default `pytest.ini` scope (`testpaths = tests`) to update blocker counts and clusters.

**Elysia-only:** Piggy2 / Cloudflare-CAPTCHA implementation prompts were not used. No WebScout/browser activity was run for classification.

---

## Safety checks (unchanged)

| Check | Command | Result |
|-------|---------|--------|
| Safe Observer | `python scripts/run_elysia_dry_run_report.py --mode real-planning` | **PASS** — SAFE, exit 0, 0 executions |
| Passive Phase 2 | six `test_live_action_*` modules | **92 passed**, 3 warnings, exit 0 |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` | **454 passed**, 3 warnings, exit 0 |
| Autonomy config | `config/autonomy.json` | **unchanged**, `"enabled": false` |

---

## Full collection

**Command:** `python -m pytest --collect-only -q`

| Metric | Prior (2026-05-30) | **Refresh (2026-06-04)** |
|--------|----------------------|---------------------------|
| Tests collected | 441 | **449** (+8 regression/isolation tests) |
| Collection duration | 16.40s | 35.08s |
| Exit code | 0 | 0 |

**Scope:** root `tests/` only per `pytest.ini` (not `project_guardian/tests/`).

---

## Full pytest

**Command:** `python -m pytest -q`

| Metric | Prior (2026-05-30) | **Refresh (2026-06-04)** | Delta |
|--------|----------------------|---------------------------|-------|
| Outcome | FAIL | **FAIL** | — |
| Duration | 89.69s | **446.05s** (~7m 26s) | Slower (more tests + heavier modules) |
| Passed | 265 | **391** | **+126** |
| Failed | 107 | **47** | **−60** |
| Errors | 60 | **0** | **−60** |
| Skipped | 9 | **11** | +2 |
| Warnings | 98 | **127** | +29 |
| Exit code | 1 | 1 | — |
| Hung? | No | **No** | Completed in bounded window |

**Raw output (local, not committed):** `REPORTS/_full_runtime_classification_refresh_out.txt`

---

## Previously fixed clusters — status in full run

| Cluster | Prior symptom | **Refresh full-run status** |
|---------|---------------|------------------------------|
| TrustMatrix fixture setup | 60 ERRORs across gateway/path modules | **Resolved** — `test_file_writer_path_safety`, `test_webreader_*`, subprocess modules all pass (no ERROR) |
| WebReader gateway assertions | runtime assertion failures | **Resolved** — `test_webreader_post_json.py` 6/6, `test_webreader_target_validation.py` 22/22 |
| UI local-only middleware 403 | 24× `403 == 200` class failures | **Resolved** — `test_ui_local_only.py` 13/13 |
| GuardianCore singleton collisions | `GuardianCore instance already exists` | **Resolved** — `test_core_smoke.py` 10/10, `test_guardian_singleton.py` 8/8, `test_unified_interface_no_double_init.py` 3/3 |
| Core smoke path-safety | 2 PATH_TRAVERSAL_BLOCKED failures | **Resolved** — mutation integration + regression tests pass |
| Core task-router contract | 2 ready/error mismatches | **Resolved** — `test_core_task_router.py` 11/11 |

---

## Remaining blocker clusters (classified)

**47 failures**, **0 errors**, across **19 modules** (no setup ERROR bucket remaining).

### By category

| Category | Approx. count | Blocks limited live mode? |
|----------|---------------|---------------------------|
| **API/approval implementation** | 9 (`test_elysia_api_approval_implementation.py`) | **Yes** — UI/API approval route / auto-implement expectations |
| **Gateway smoke drift** | 6 (`test_gateways_smoke.py`) | **Yes** — file writer / web reader replay semantics |
| **Invariant / bypass detection** | 5 (`test_invariants.py`) | **Yes** — safety-critical gating proofs |
| **Environment / memory cleanup** | 4 (`test_auto_cleanup_effectiveness.py`) | Partial — operational, not executor core |
| **Artifact / run_once policy** | 4 (`test_artifact_policy_*.py`, `test_apply_mutation_task.py`) | **Yes** — task/artifact execution contracts |
| **Router telemetry** | 4 (`test_router_telemetry_adapt.py`, `test_router_rules.py`) | Partial — routing config drift |
| **No-side-effects suites** | 5 (mutation/network/subprocess/task_engine) | **Yes** — prove zero writes on deny/review |
| **E2E mutation workflow** | 2 (`test_e2e_workflow.py`) | **Yes** |
| **Task acceptance (subprocess)** | 2 (`test_task_execution.py` RUN_ACCEPTANCE) | Partial — script/env dependent |
| **UI residual** | 3 (`test_ui_smoke.py` ×2, `test_ui_diff_basehash.py` ×1) | Partial for UI route work; not autonomy core |
| **Misc** | 3 (review_queue restart, lazy_embeddings, etc.) | Mixed |

### UI failures (still present)

| Module | Failures | Notes |
|--------|----------|-------|
| `test_ui_smoke.py` | 2 | `test_run_once_creates_artifact`, `test_create_mutation_path_mismatch` |
| `test_ui_diff_basehash.py` | 1 | `test_payload_creation_includes_base_hashes` |

`test_ui_local_only.py` is **fully passing** after middleware repair.

### Safety-critical / execution-path (still failing)

- `test_invariants.py` (trust replay, bypass detection)
- `test_no_side_effects_*.py` (mutation, network, subprocess, task_engine)
- `test_gateways_smoke.py`
- `test_elysia_api_approval_implementation.py` (approval/auto-implement surface)
- Parts of `test_artifact_policy_run_once.py`, `test_e2e_workflow.py`

These remain blockers for **limited live mode** until fixed or explicitly classified non-blocking with human approval.

---

## Live-mode readiness impact

| Gate | Status |
|------|--------|
| Passive Phase 2 + Safe Observer + safe-stack smoke | **Pass** |
| Default `tests/` full suite clean | **No** — 47 failures remain |
| Prior 60 setup ERROR bucket | **Cleared** |
| Limited live mode | **Still blocked** — full runtime not clean; API/approval implementation tests still fail; safety/invariant/no-side-effects clusters remain |

Unchanged product gates (from prior readiness docs): live executor, UI/API approval route implementation, harmless live-action smoke — not enabled by this classification milestone.

---

## Comparison summary

```text
                    │ 2026-05-30 (old) │ 2026-06-04 (refresh)
────────────────────┼──────────────────┼─────────────────────
Collected           │ 441              │ 449
Passed              │ 265              │ 391
Failed              │ 107              │ 47
Errors              │ 60               │ 0
Non-pass total      │ 167              │ 47
```

Major improvement: **all TrustMatrix setup ERRORs eliminated**; targeted repair modules green in full run.

---

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged)
- No live execution, WebScout, or browser activity run for this milestone
- No API/server routes or execution code added
- Classification used committed test tree + local pytest only; dirty runtime files were not used as proof

---

## Related docs

- [`docs/FULL_RUNTIME_TEST_CLASSIFICATION.md`](FULL_RUNTIME_TEST_CLASSIFICATION.md) — original baseline
- [`docs/TRUSTMATRIX_FIXTURE_REPAIR.md`](TRUSTMATRIX_FIXTURE_REPAIR.md)
- [`docs/WEBREADER_RUNTIME_TEST_REPAIR.md`](WEBREADER_RUNTIME_TEST_REPAIR.md)
- [`docs/UI_LOCAL_ONLY_MIDDLEWARE_TEST_REPAIR.md`](UI_LOCAL_ONLY_MIDDLEWARE_TEST_REPAIR.md)
- [`docs/GUARDIANCORE_SINGLETON_TEST_ISOLATION.md`](GUARDIANCORE_SINGLETON_TEST_ISOLATION.md)
- [`docs/PATH_SAFETY_TEST_REPAIR.md`](PATH_SAFETY_TEST_REPAIR.md)
- [`docs/TASK_ROUTER_CONTRACT_REPAIR.md`](TASK_ROUTER_CONTRACT_REPAIR.md)
