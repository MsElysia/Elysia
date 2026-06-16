# Full Runtime Test Refresh — Limited Live Release Candidate

**Milestone:** Full pytest refresh after limited-live RC baseline  
**Date:** 2026-05-30  
**Status:** **CLEAN** — full runtime pass; limited-live RC test baseline verified

**Starting checkpoint:** `4d2b351 docs(autonomy): record limited live release candidate`

**Related docs:** [`LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md`](LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md), [`LIVE_READINESS_AFTER_LIMITED_LIVE_SMOKE_COMMAND.md`](LIVE_READINESS_AFTER_LIMITED_LIVE_SMOKE_COMMAND.md)

---

## 1. Starting checkpoint

| Property | Value |
|----------|-------|
| Git HEAD | `4d2b351 docs(autonomy): record limited live release candidate` |
| Prior full runtime | `439 passed, 0 failed, 11 skipped` (older baseline) |
| Readiness status | `BLOCKED` |
| `config/autonomy.json` | `"enabled": false` (unchanged) |
| root `test.py` | Absent, untracked, unstaged |

---

## 2. Full collection

```bash
python -m pytest --collect-only -q
```

| Metric | Result |
|--------|--------|
| Collected | **471** tests |
| Collection time | 9.98s |
| Exit code | 0 |

---

## 3. Full pytest

```bash
python -m pytest -q
```

| Metric | Result |
|--------|--------|
| Passed | **459** |
| Failed | **0** |
| Skipped | **12** |
| Errors | **0** |
| Warnings | 135 |
| Runtime | 936.52s (15m 36s) |
| Exit code | 0 |

**Full pytest clean:** Yes

### Skipped tests (12)

| Module | Skipped | Notes |
|--------|---------|-------|
| `tests/test_file_writer_path_safety.py` | 2 | Platform/env conditional |
| `tests/test_invariants.py` | 1 | Conditional skip |
| `tests/test_limited_live_smoke_script.py` | 1 | Symlink test when unsupported |
| `tests/test_module_matrix.py` | 6 | Matrix conditional skips |
| `tests/test_mutation_path_safety.py` | 2 | Platform/env conditional |

### Failures

None.

### Failure clusters

None.

### Safety classification

| Category | Count |
|----------|-------|
| Safety-critical failures | **0** |
| Non-safety-critical failures | **0** |

No failures to classify.

---

## 4. Limited-live critical regression set

```bash
python -m pytest project_guardian/tests/test_live_action_readiness.py \
  tests/test_limited_live_smoke_script.py \
  project_guardian/tests/test_live_action_approval_route_executor_wiring.py \
  project_guardian/tests/test_live_action_executor.py -q
```

| Metric | Result |
|--------|--------|
| Passed | 87 |
| Skipped | 1 |
| Failed | 0 |
| Exit code | 0 |

All limited-live safety tests passed.

---

## 5. Passive Phase 2 targeted tests

```bash
python -m pytest project_guardian/tests/test_live_action_gate.py \
  project_guardian/tests/test_live_action_audit.py \
  project_guardian/tests/test_live_action_rollback.py \
  project_guardian/tests/test_live_action_approval_packet.py \
  project_guardian/tests/test_live_action_operator_decision.py \
  project_guardian/tests/test_live_action_readiness.py \
  project_guardian/tests/test_live_action_approval_route.py \
  project_guardian/tests/test_live_action_smoke_packet.py \
  project_guardian/tests/test_live_action_passive_smoke_approval_flow.py \
  project_guardian/tests/test_live_action_executor.py \
  project_guardian/tests/test_live_action_approval_route_executor_wiring.py -q
```

| Metric | Result |
|--------|--------|
| Passed | **185** |
| Failed | 0 |
| Exit code | 0 |

---

## 6. Safe Observer

```bash
python scripts/run_elysia_dry_run_report.py --mode real-planning
python scripts/run_elysia_dry_run_report.py --mode real-planning --json
```

| Check | Result |
|-------|--------|
| Text verdict | SAFE, exit 0 |
| JSON `"safe"` | `true` |
| `any_executed` | `false` |
| `execution_call_count` | 0 |

---

## 7. Safe-stack smoke

```bash
python scripts/run_safe_stack_smoke_tests.py
```

| Metric | Result |
|--------|--------|
| Collected | 454 |
| Passed | **454** |
| Failed | 0 |
| Exit code | 0 |

---

## 8. Config and repo hygiene

| Check | Result |
|-------|--------|
| `config/autonomy.json` changed | No — `enabled=false` |
| Autonomy enabled | No |
| root `test.py` present/tracked/staged | No |
| Unrelated dirty worktree used as proof | No |

---

## 9. Comparison to prior baseline

| Metric | Prior (`439/0/11`) | This refresh |
|--------|-------------------|--------------|
| Collected | 450 (prior) | **471** |
| Passed | 439 | **459** |
| Failed | 0 | **0** |
| Skipped | 11 | **12** |

Increase in collected/passed tests reflects limited-live smoke command tests and related additions since prior full-runtime baseline. No regressions observed.

---

## 10. Final recommendation

**Limited-live RC test baseline is CLEAN.**

Full pytest passed with zero failures. Limited-live critical regression, Passive Phase 2, Safe Observer, and safe-stack smoke all pass. No safety-critical failures.

Readiness remains `BLOCKED` — this refresh does not enable autonomy or production live execution.

### Next recommended milestone

- Tag or document this refresh as the limited-live RC test baseline checkpoint
- Or proceed to operator handoff using [`LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md`](LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md)

Do **not** enable `config/autonomy.json` or remove production-disabled readiness blockers without explicit operator opt-in.

---

## 11. Safety statement

- No autonomy enabled
- No production live default enabled
- `config/autonomy.json` remains `enabled=false`
- No source/runtime behavior changed in this milestone
- Documentation-only refresh
