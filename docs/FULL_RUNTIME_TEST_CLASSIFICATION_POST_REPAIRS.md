# Full Runtime Test Classification — Post Repairs

## Starting checkpoint

**HEAD:** `48af326 fix(tests): isolate task mutation fixtures`

**Date:** 2026-06-14

**Scope:** root `tests/` only per `pytest.ini` (`testpaths = tests`); not `project_guardian/tests/`.

---

## Why this refresh was needed

`docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md` (2026-06-04, HEAD baseline `a0455c7`) reported **449 collected**, **391 passed / 47 failed / 0 errors**. Since then, all named blocker clusters were repaired or narrowed:

| Repair milestone | Commit (approx.) | Cluster |
|------------------|------------------|---------|
| No-side-effects invariants | `e99bc9a` | `test_invariants.py`, `test_no_side_effects_*` |
| API approval contract | `c0861e5`, `57e66bb` | `test_elysia_api_approval_implementation.py` |
| Gateway smoke passive contract | `c8941d7` | `test_gateways_smoke.py` |
| Review queue isolation | `90f7d66` | `test_review_queue*.py` |
| Artifact/run_once policy | `310043b` | `test_artifact_policy_*.py` |
| UI residual expectations | `1557130` | `test_ui_smoke.py` |
| Router task telemetry | `2d4cb1c` | `test_router_telemetry_adapt.py` (partial — see remaining) |
| Memory auto-cleanup | `96b18a1` | `test_auto_cleanup_effectiveness.py` |
| UI diff/basehash | `7c7f0e1` | `test_ui_diff_basehash.py` |
| Task/mutation fixtures | `48af326` | `test_apply_mutation_task.py`, `test_task_execution.py` |

This refresh re-runs the full default collection to measure post-repair state.

**No WebScout/browser activity, no live execution, no autonomy mode.**

---

## Safety checks

| Check | Command | Result |
|-------|---------|--------|
| Safe Observer (text) | `python scripts/run_elysia_dry_run_report.py --mode real-planning` | **PASS** — SAFE, exit 0, 3 cycles, `any_executed=False`, `execution_call_count=0` |
| Safe Observer (JSON) | `... --json` | **PASS** — `"safe": true`, `"safety_verdict": "SAFE"`, exit 0 |
| Passive Phase 2 | six `test_live_action_*` modules | **92 passed**, 3 warnings, exit 0 |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` | **454 passed**, 3 warnings, exit 0 |
| Autonomy config | `config/autonomy.json` | **unchanged**, `"enabled": false` |
| Root `test.py` | `git status --short -- test.py` | **absent** — not present, not tracked, not staged |

---

## Full collection

**Command:** `python -m pytest --collect-only -q`

| Metric | Prior refresh (2026-06-04) | **Post-repair (2026-06-14)** |
|--------|------------------------------|-------------------------------|
| Tests collected | 449 | **450** |
| Collection duration | 35.08s | 10.07s |
| Exit code | 0 | 0 |

---

## Full pytest

**Command:** `python -m pytest -q`

| Metric | Prior refresh (2026-06-04) | **Post-repair (2026-06-14)** | Delta |
|--------|------------------------------|-------------------------------|-------|
| Outcome | FAIL | **FAIL** | — |
| Duration | 446.05s (~7m 26s) | **657.33s (~10m 57s)** | Slower |
| Passed | 391 | **436** | **+45** |
| Failed | 47 | **3** | **−44** |
| Errors | 0 | **0** | 0 |
| Skipped | 11 | **11** | 0 |
| Warnings | 127 | **135** | +8 |
| Exit code | 1 | 1 | — |
| Hung? | No | **No** | Completed in bounded window |

**Raw output (local, not committed):** `REPORTS/_full_runtime_post_repairs_out.txt`

---

## Clusters now confirmed green (full run)

| Cluster | Module(s) | Full-run status |
|---------|-----------|-----------------|
| No-side-effects / invariants | `test_invariants.py`, `test_no_side_effects_mutation.py`, `test_no_side_effects_network.py`, `test_no_side_effects_subprocess.py`, `test_no_side_effects_task_engine.py` | **All pass** (1 skip in invariants) |
| API approval | `test_elysia_api_approval_implementation.py` | **10/10 pass** |
| Gateway / e2e | `test_gateways_smoke.py`, `test_e2e_workflow.py` | **14/14 pass**, **4/4 pass** |
| Review queue | `test_review_queue_smoke.py`, `test_review_queue.py` | **10/10 pass**, **4/4 pass** |
| Artifact / run_once | `test_artifact_policy_run_once.py`, `test_artifact_policy_reviews.py`, `test_artifact_policy_coverage.py` | **3/3**, **1/1**, **2/2 pass** |
| UI residual | `test_ui_smoke.py` | **8/8 pass** |
| Router / task telemetry (core) | `test_router_telemetry_adapt.py` (4/5), `test_core_task_router.py`, `test_core_smoke.py` | **4/5 pass** — 1 cloud-escalation test still fails (see below) |
| Memory auto-cleanup | `test_auto_cleanup_effectiveness.py` | **8/8 pass** |
| UI diff / basehash | `test_ui_diff_basehash.py` | **6/6 pass** |
| Task / mutation fixtures | `test_apply_mutation_task.py`, `test_task_execution.py` | **7/7**, **7/7 pass** |

---

## Remaining failures (3)

| # | Test | Module | Classification | Blocks limited live mode? |
|---|------|--------|----------------|---------------------------|
| 1 | `test_embeddings_enabled_after_startup` | `test_lazy_embeddings.py` | **Environment / optional-deps** — deferred embedding enablement; `add_memory` mock not called in this runtime | **No** — not execution-path or safety-gating |
| 2 | `test_governance_cloud_executor_with_key` | `test_router_rules.py` | **Router config / environment drift** — expects `openai` executor; got `ollama:llama3.2:3b` with reason `governance_openai_insufficient_quota_skip_cloud_executor; openai_unavailable_local_fallback` | **No** — local fallback is policy-correct; test expects cloud when quota blocked |
| 3 | `test_invalid_intents_escalate_cloud_serial` | `test_router_telemetry_adapt.py` | **Router config / environment drift** — expects `openai` executor; got `ollama:mistral` with reason `openai_unavailable_local_fallback` | **No** — same local-fallback semantics |

**Safety-critical failures remaining:** **None**

**Execution-path failures remaining:** **None**

**UI-only failures remaining:** **None**

**Environment-only / stale-test failures:** **3** (all classified non-blocking for limited live mode)

---

## Live-mode readiness impact

| Gate | Status |
|------|--------|
| Safety-critical clusters | **Clear** — invariants, no-side-effects, gateway, API approval, artifact policy all pass |
| Execution-path clusters | **Clear** — e2e, task/mutation, gateways pass |
| Full runtime clean | **Not yet** — 3 failures remain |
| Limited live mode | **Still blocked for strict full-suite green** — but remaining 3 failures are **classified non-blocking** (environment/router drift, optional embeddings). Operator may proceed to limited live-mode design review with documented exceptions. |

Prior refresh: **47 failures** blocked progress. Post-repair: **3 failures**, none safety-critical.

---

## Comparison summary

```
2026-06-04 refresh:  391 passed / 47 failed / 0 errors  (449 collected)
2026-06-14 post-repair: 436 passed /  3 failed / 0 errors  (450 collected)
                         +45 passed    -44 failed
```

---

## Safety statement

- **Autonomy not enabled** — `config/autonomy.json` → `"enabled": false` (unchanged)
- **No live execution run**
- **No tools/capabilities/mutation/proposal implementation executed** (classification + passive safety checks only)
- **No new API/server routes added**
- **No execution code added**
- **No real repo mutation performed**
- **No real configured memory cleanup performed**
- **Root accidental `test.py` not present**
- **No unrelated dirty files staged or committed**

---

## Remaining blockers (next milestones)

1. **Router cloud-escalation tests** — update `test_router_rules.py` and `test_router_telemetry_adapt.py` to accept local-fallback when OpenAI quota/unavailable (or isolate with mocked cloud state)
2. **Lazy embeddings startup test** — fixture/mock drift in `test_lazy_embeddings.py`
3. **Strict full-suite green** — optional polish; not safety-critical for limited live mode

---

## Related docs

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md` — prior baseline (47 failures)
- `docs/TASK_MUTATION_FIXTURE_REPAIR.md` — latest fixture repair
- `docs/TASK_MUTATION_EXECUTION_ADJACENT_CLASSIFICATION.md` — classification before fixture repair
