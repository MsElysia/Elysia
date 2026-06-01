# Full Runtime Test Classification

## Current checkpoint

**HEAD:** `b10b8c2 fix(autonomy): update live-mode readiness after dirty cleanup`

**Date:** 2026-05-30

## Purpose

Classify full runtime test status from the current clean safety baseline **before** limited live executor or UI/API approval route work. This milestone is documentation and classification only — no test fixes, no autonomy enablement, no live execution.

---

## Baseline safety checks

| Check | Command | Result |
|-------|---------|--------|
| Safe Observer | `python scripts/run_elysia_dry_run_report.py --mode real-planning` | **PASS** — exit 0, `final safety verdict: SAFE`, all cycles `blocked=True executed=False`, zero execution |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` | **PASS** — 454 passed, 3 warnings, exit 0 |
| Passive Phase 2 targeted | `python -m pytest project_guardian/tests/test_live_action_gate.py project_guardian/tests/test_live_action_audit.py project_guardian/tests/test_live_action_rollback.py project_guardian/tests/test_live_action_approval_packet.py project_guardian/tests/test_live_action_operator_decision.py project_guardian/tests/test_live_action_readiness.py -q` | **PASS** — 92 passed, 3 warnings, exit 0 |
| Autonomy config | `config/autonomy.json` | **unchanged**, `"enabled": false` |

---

## Full collection result

**Command:** `python -m pytest --collect-only -q`

**Scope note:** `pytest.ini` sets `testpaths = tests`, so default collection covers the root `tests/` tree only (not `project_guardian/tests/`).

| Metric | Value |
|--------|-------|
| Tests collected | **441** |
| Duration | 16.40s |
| Exit code | 0 |
| Warnings/errors at collection | None blocking collection |

**Supplementary broader scope (not the mandated default run):**

```text
python -m pytest project_guardian/tests tests --collect-only -q
→ 1901 tests collected in 4.17s
```

The mandated procedure uses default `pytest.ini` configuration. Broader `project_guardian/tests` coverage is tracked separately in prior audit artifacts under `REPORTS/broader_audit_*.txt` and is **out of scope** for this classification commit unless explicitly expanded in a follow-up milestone.

---

## Full pytest result

**Command:** `python -m pytest -q`

| Metric | Value |
|--------|-------|
| Outcome | **FAIL** (completed; did not hang) |
| Duration | **89.69s** (~1m 30s) |
| Passed | 265 |
| Failed | 107 |
| Skipped | 9 |
| Errors | 60 |
| Warnings | 98 |
| Exit code | 1 |

**Hang/timeout:** No. Run completed within bounded window.

**Raw output artifact:** `REPORTS/_full_runtime_classification_out.txt` (local, not committed).

---

## Failure classification summary

**167 non-pass outcomes** (107 failed + 60 errors) across **28 test modules** in `tests/`.

### By category

| Category | Count (approx.) | Blocks limited live mode? |
|----------|-----------------|---------------------------|
| LEGACY_EXPECTATION | 60 errors + ~15 failures | Partial — fixture/API drift in `tests/` trust/gateway layer |
| NEEDS_INVESTIGATION | ~25 failures | Yes until root cause confirmed (singleton isolation, router telemetry) |
| ENVIRONMENT_DEPENDENT | ~25 failures | No for executor design; yes for UI/API approval route verification |
| SAFETY_CRITICAL | ~15 failures | **Yes** — invariants, no-side-effects, gateway gating |
| REAL_REGRESSION | ~10 failures | Yes if confirmed (mutation/task/artifact policy flows) |
| SLOW_OR_HANGING | 0 | N/A |

### Per-module classification

#### ERRORS (60) — fixture/setup breakage

| Test module | Count | Category | Reason | Next action |
|-------------|-------|----------|--------|-------------|
| `tests/test_file_writer_path_safety.py` | 11 ERROR + 2 FAILED | LEGACY_EXPECTATION | `TrustMatrix.__init__()` now requires `memory` argument; test fixture calls `TrustMatrix()` with no args | Update test fixtures to pass memory stub; re-run path-safety slice |
| `tests/test_read_only_analysis_task.py` | 6 ERROR + 1 FAILED | LEGACY_EXPECTATION | Same TrustMatrix/setup drift | Fix shared trust fixture |
| `tests/test_subprocess_background_audit.py` | 9 ERROR | LEGACY_EXPECTATION | TrustMatrix/setup fixture drift | Fix fixture; verify audit assertions |
| `tests/test_subprocess_runner_background.py` | 6 ERROR | LEGACY_EXPECTATION | TrustMatrix/setup fixture drift | Fix fixture |
| `tests/test_webreader_post_json.py` | 6 ERROR | LEGACY_EXPECTATION | TrustMatrix/setup fixture drift | Fix fixture |
| `tests/test_webreader_target_validation.py` | 22 ERROR | LEGACY_EXPECTATION | TrustMatrix/setup fixture drift | Fix fixture; priority for network gating coverage |

#### FAILED (107) — by module

| Test module | Failures | Category | Reason | Next action |
|-------------|----------|----------|--------|-------------|
| `tests/test_apply_mutation_task.py` | 6 | REAL_REGRESSION / SAFETY_CRITICAL | Mutation apply/review/replay contract tests failing | Investigate task engine + governance integration |
| `tests/test_artifact_policy_reviews.py` | 1 | REAL_REGRESSION | Approval store / queue status assertion mismatch | Compare artifact policy vs current review queue |
| `tests/test_artifact_policy_run_once.py` | 3 | REAL_REGRESSION | Run-once artifact/write expectations | Investigate run-once artifact paths |
| `tests/test_auto_cleanup_effectiveness.py` | 4 | NEEDS_INVESTIGATION | Memory cleanup count/consolidation assertions | Check memory store state / test isolation |
| `tests/test_core_smoke.py` | 7 | NEEDS_INVESTIGATION / SAFETY_CRITICAL | Singleton collision (`GuardianCore instance already exists`) and governance propagation | Reset singleton between tests; verify mutation/review flows |
| `tests/test_core_task_router.py` | 9 | LEGACY_EXPECTATION | Task router / control.json contract drift | Align tests with current control task schema |
| `tests/test_e2e_workflow.py` | 4 | REAL_REGRESSION | End-to-end mutation review/approve/replay workflow | Fix after core_smoke + apply_mutation_task stabilized |
| `tests/test_elysia_api_approval_implementation.py` | 9 | ENVIRONMENT_DEPENDENT / REAL_REGRESSION | API approval auto-implement, preview, WebScout forwarding | Blocks UI/API approval route work until green or quarantined |
| `tests/test_gateways_smoke.py` | 6 | SAFETY_CRITICAL | FileWriter/WebReader deny/review/replay gating | Fix after TrustMatrix fixture; verify gateway trust paths |
| `tests/test_guardian_singleton.py` | 1 | NEEDS_INVESTIGATION | Unified/interface singleton identity | Fix test isolation |
| `tests/test_invariants.py` | 5 | **SAFETY_CRITICAL** | Trust replay, bypass detection (network/file/subprocess) | **Must pass or be quarantined with explicit waiver before live mode** |
| `tests/test_lazy_embeddings.py` | 1 | ENVIRONMENT_DEPENDENT | Embeddings enabled after startup | Optional dependency / Ollama state |
| `tests/test_no_side_effects_mutation.py` | 1 | **SAFETY_CRITICAL** | Mutation review must not write | Fix mutation review side-effect guard |
| `tests/test_no_side_effects_network.py` | 2 | **SAFETY_CRITICAL** | Network review must enqueue only | Fix network gateway review path |
| `tests/test_no_side_effects_subprocess.py` | 1 | **SAFETY_CRITICAL** | Subprocess review must not launch | Fix subprocess review path |
| `tests/test_no_side_effects_task_engine.py` | 3 | **SAFETY_CRITICAL** | Task apply_mutation review/deny side effects | Fix task engine trust integration |
| `tests/test_review_queue_smoke.py` | 1 | NEEDS_INVESTIGATION | Restart tolerance / pending request persistence | Verify review queue storage |
| `tests/test_router_rules.py` | 1 | ENVIRONMENT_DEPENDENT | Cloud executor routing with API key | Mock or skip without cloud key |
| `tests/test_router_telemetry_adapt.py` | 3 | NEEDS_INVESTIGATION | Serial/parallel escalation telemetry | Align with current router telemetry store |
| `tests/test_task_execution.py` | 7 | REAL_REGRESSION / SAFETY_CRITICAL | Task type validation, acceptance runner, control updates | Fix task execution engine contracts |
| `tests/test_ui_diff_basehash.py` | 6 | ENVIRONMENT_DEPENDENT | UI diff viewer / base hash display (403 or routing) | Requires local-only middleware test setup |
| `tests/test_ui_local_only.py` | 7 | ENVIRONMENT_DEPENDENT | Local-only middleware returns 403 vs expected 200 | Configure test client for loopback/local-only flags |
| `tests/test_ui_observability.py` | 6 | ENVIRONMENT_DEPENDENT | API routes return 403 in test harness | Same local-only / TestClient setup |
| `tests/test_ui_smoke.py` | 8 | ENVIRONMENT_DEPENDENT | Dashboard/API smoke (`assert 403 == 200`) | Fix test middleware env or mark `@pytest.mark` for UI server fixture |
| `tests/test_unified_interface_no_double_init.py` | 2 | NEEDS_INVESTIGATION | Double-init / monitoring singleton | Fix test isolation |

---

## Live-mode readiness impact

### Full runtime tests classified?

**Yes.** This document satisfies the `FULL_RUNTIME_TESTS_CLASSIFIED` evidence requirement for operator review. Default-scope pytest (`tests/`, 441 items) was run to completion and failures are categorized.

### Does full pytest pass?

**No.** 265/441 passed in default scope; 167 non-pass outcomes remain.

### Blockers for limited live mode from tests

| Blocker type | Present? | Summary |
|--------------|----------|---------|
| SAFETY_CRITICAL failures | **Yes** | `test_invariants.py` bypass detection (3), `test_no_side_effects_*` (7), `test_gateways_smoke.py` (6), mutation/task side-effect guards |
| Execution/autonomy-related failures | **Yes** | `test_apply_mutation_task.py`, `test_task_execution.py`, `test_core_smoke.py` mutation integration, `test_elysia_api_approval_implementation.py` |
| Environment-only failures | **Yes** | UI smoke/observability/local-only (~27 failures) — do not block passive executor **design**, but block UI/API approval route verification |
| Fixture drift (TrustMatrix) | **Yes** | 60 errors — blocks confidence in file/network/subprocess gating tests until fixtures updated |

**Verdict:** Limited live mode remains **blocked** by test failures even after classification. Passive Phase 2 scaffolding tests (92/92) and safe-stack smoke (454/454) pass independently.

### Recommended readiness gate update (future milestone)

Set `FULL_RUNTIME_TESTS_CLASSIFIED=true` in passive readiness evidence **after operator accepts this document**. Do **not** set `ready_for_limited_live_mode=true` until SAFETY_CRITICAL and execution-path failures are fixed or explicitly quarantined.

---

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged)
- Live execution **not** run
- No API/server routes added
- No execution code added
- `project_guardian/core.py` and `elysia/api/server.py` **not** modified
- Classification only — no broad test fixes in this milestone

---

## Recommended next branch

1. **Targeted failure investigation branch** — fix TrustMatrix test fixtures (unblocks 60 errors + gateway/path-safety coverage).
2. **Singleton test isolation branch** — stabilize `test_core_smoke.py`, `test_guardian_singleton.py`, `test_unified_interface_no_double_init.py`.
3. **SAFETY_CRITICAL quarantine/fix branch** — `test_invariants.py`, `test_no_side_effects_*`, `test_gateways_smoke.py` must green or receive explicit waiver.
4. **UI/API test harness branch** — local-only middleware test setup for `test_ui_*` (needed before approval route work, not before executor design).
5. **Limited executor design only** — may proceed in parallel with (1)–(3) as **design/docs**; must not wire live execution until blockers above are resolved.

---

## Commands reference

```text
# Baseline safety (all passed at classification time)
python scripts/run_elysia_dry_run_report.py --mode real-planning
python scripts/run_safe_stack_smoke_tests.py
python -m pytest project_guardian/tests/test_live_action_*.py -q

# Default full suite (pytest.ini → tests/ only)
python -m pytest --collect-only -q
python -m pytest -q
```
