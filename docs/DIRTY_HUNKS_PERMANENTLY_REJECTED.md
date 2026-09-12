# Dirty Hunks Permanently Rejected

**Milestone:** Branch A — permanent discard of quarantined dirty hunks (operator-approved)  
**Checkpoint before cleanup:** `173b0fb` — docs(autonomy): plan dirty hunk cleanup  
**Date:** 2026-06-01  
**Human approval:** Operator approved permanently discarding dirty unstaged hunks in the two files listed below only.

**Related docs:** [`DIRTY_HUNKS_CLEANUP_PLAN.md`](DIRTY_HUNKS_CLEANUP_PLAN.md), [`DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md), [`PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md`](PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md)

---

## 1. Cleanup action performed

```powershell
git restore project_guardian/core.py elysia/api/server.py
```

No other files were restored, reset, stashed, or discarded.

---

## 2. Files restored to committed HEAD

| File | Prior state | After restore |
|------|-------------|---------------|
| `project_guardian/core.py` | Modified, unstaged (~189 lines dirty) | **Clean** — matches HEAD |
| `elysia/api/server.py` | Modified, unstaged (~128 lines dirty) | **Clean** — matches HEAD |

Post-restore verification:

```powershell
git diff -- project_guardian/core.py    # no output
git diff -- elysia/api/server.py        # no output
git status --short -- project_guardian/core.py elysia/api/server.py  # not listed
```

---

## 3. Reason for permanent rejection

Dirty hunks were classified in [`DIRTY_HUNKS_CLEANUP_PLAN.md`](DIRTY_HUNKS_CLEANUP_PLAN.md) as **REJECT**, **REWRITE_FROM_SCRATCH**, or **NEEDS_HUMAN_REVIEW**. They included:

- **`core.py`:** risky autonomy trace wiring, selection/scoring changes, legacy executor edits — safe observability already extracted to committed `autonomy_dry_run_guard.py` and Safe Observer.
- **`server.py`:** auto-implement-on-approve, proposal implementation chaining, WebScout API expansion — must not block the safety baseline.

Safe replacements already exist in the committed passive Phase 2 stack (`live_action_*` modules). These dirty hunks must not remain in the worktree.

---

## 4. Verification after restore

| Check | Result |
|-------|--------|
| Both files clean after restore | **Pass** |
| Safe Observer stub (text) | exit 0 — `mode: stub`, `final safety verdict: SAFE`, `any_executed: False`, `execution_call_count: 0` |
| Safe Observer stub (JSON) | exit 0 — `"safe": true`, `"safety_verdict": "SAFE"`, `"any_executed": false` |
| Safe Observer real-planning (text) | exit 0 — `mode: real-planning`, `final safety verdict: SAFE`, `any_executed: False`, `execution_call_count: 0` |
| Safe Observer real-planning (JSON) | exit 0 — `"safe": true`, `"safety_verdict": "SAFE"`, `"any_executed": false` |
| Passive Phase 2 targeted tests | **91 passed**, 3 warnings in 0.84s (exit 0) |
| Safe-stack smoke | **454 passed**, 3 warnings in 9.74s (exit 0) |
| `config/autonomy.json` | **`enabled: false`** (unchanged) |
| Autonomy enabled | **No** |
| Live execution run | **No** |
| Unrelated dirty files preserved | **Yes** — only the two approved files were restored |

Commands run:

```powershell
python scripts/run_elysia_dry_run_report.py
python scripts/run_elysia_dry_run_report.py --json
python scripts/run_elysia_dry_run_report.py --mode real-planning
python scripts/run_elysia_dry_run_report.py --mode real-planning --json
python -m pytest project_guardian/tests/test_live_action_gate.py project_guardian/tests/test_live_action_audit.py project_guardian/tests/test_live_action_rollback.py project_guardian/tests/test_live_action_approval_packet.py project_guardian/tests/test_live_action_operator_decision.py project_guardian/tests/test_live_action_readiness.py -q
python scripts/run_safe_stack_smoke_tests.py
```

---

## 5. Readiness gate impact

After this cleanup, default evidence for `evaluate_live_mode_readiness()` sets:

- `DIRTY_CORE_CLEANED` → **true** (updated in `fix(autonomy): update live-mode readiness after dirty cleanup`)
- `DIRTY_SERVER_CLEANED` → **true** (same)

Remaining blockers for limited live mode (unchanged):

- Missing live executor
- Missing UI/API approval route
- Missing harmless live-action smoke verification
- Full runtime tests not classified

Discarding dirty hunks does **not** enable limited live mode or live execution.

---

## 6. Explicit forward guidance

Future work must **not** recover discarded hunks from local history unless re-derived on a clean branch with full governance review.

- **Limited live executor:** design and implement from scratch using the passive safety stack — not from discarded `core.py` hunks.
- **UI/API approval routes:** design and implement from scratch using `live_action_approval_packet.py` and `live_action_operator_decision.py` — **never copy** from discarded `server.py` hunks.

**This document does not enable live execution or autonomy.**
