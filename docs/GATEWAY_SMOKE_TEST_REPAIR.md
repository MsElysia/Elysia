# Gateway smoke passive contract repair

## Starting checkpoint

**HEAD:** `57e66bb fix(api): keep approval implementation path passive`

**Date:** 2026-06-11

**Scope:** `tests/test_gateways_smoke.py` (6 failures) and gateway-adjacent `tests/test_e2e_workflow.py` (2 failures). No production execution paths, routes, or autonomy changes.

---

## Safety checks (unchanged)

| Check | Result |
|-------|--------|
| `config/autonomy.json` | **unchanged**, `"enabled": false` |
| Index at start | **clean** (no staged files) |
| Dirty worktree artifacts | **not used as proof** (`file_a.py`, `file_b.py`, `REPORTS/*` runtime leaks ignored) |

---

## Classification docs reviewed

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`
- `docs/API_APPROVAL_TEST_REPAIR.md`
- `docs/API_APPROVAL_EXECUTION_BEHAVIOR_REPAIR.md`
- `docs/NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md`

---

## Targeted gateway tests before

**Primary files:**

```bash
python -m pytest tests/test_gateways_smoke.py tests/test_e2e_workflow.py -q
```

| Result | Count |
|--------|-------|
| Failed | **8** |
| Passed | **10** |
| Exit | 1 |

**Broad `-k` filter (includes adjacent smoke modules):**

```bash
python -m pytest -q -k "gateway or smoke or e2e"
```

| Result | Count |
|--------|-------|
| Failed | **8+** (overlapping gateway/e2e cluster plus unrelated UI/review-queue drift) |
| Passed | **61+** |
| Exit | 1 |

---

## Root causes (classified)

| Test / area | Symptom | Classification | Fix |
|-------------|---------|----------------|-----|
| `TestWebReaderApprovalReplay` | `APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH` | **APPROVAL_PASSIVE_CONTRACT_DRIFT** | Align approval context with `WebReader.fetch` `gate_context` (`scheme`, `allow_internal`); use `make_fetch_response()` |
| `TestFileWriter*` (5 tests) | `PATH_TRAVERSAL_BLOCKED` instead of trust errors | **TEST_EXPECTATION_OUTDATED** | Pass `repo_root=Path(tmpdir)` and use **relative** paths (absolute paths rejected before trust gating) |
| `TestFileWriterApprovalReplay` | context mismatch on replay | **APPROVAL_PASSIVE_CONTRACT_DRIFT** | Include full `gate_context` fields (`bytes`, `allow_overwrite`) when approving |
| `test_review_approve_replay_success_workflow` | expected `needs_review`, got `ok` on first run | **TEST_EXPECTATION_OUTDATED** | Mutate protected `CONTROL.md` with `ALLOW_GOVERNANCE_MUTATION: true` to hit governance trust gate |
| `test_preflight_allows_all_files_when_approved` | `KeyError: changed_files` / workspace pollution | **GLOBAL_STATE_LEAK** + **TEST_EXPECTATION_OUTDATED** | Bind `core.mutation.repo_root = tmp_path`; assert filesystem effects (not `run_once` detail fields) |
| E2e success assertions on `changed_files` / `backup_paths` | `KeyError` despite `status=ok` | **TEST_EXPECTATION_OUTDATED** | `run_once()` surfaces `status`/`outcome` only; verify backups via `tmp_path/guardian_backups/` |

**Not changed (out of milestone scope):**

- `tests/test_review_queue_smoke.py::TestRestartTolerance` — **GLOBAL_STATE_LEAK** / shared `REPORTS/review_queue.jsonl`
- `tests/test_ui_smoke.py` (2 failures) — **UI residual**

---

## Files changed

| File | Change |
|------|--------|
| `tests/test_gateways_smoke.py` | WebReader replay context; FileWriter `repo_root` + relative paths; full FileWriter approval context |
| `tests/test_e2e_workflow.py` | Isolated core config; `mutation.repo_root` binding; protected-path review workflow; filesystem assertions |
| `docs/GATEWAY_SMOKE_TEST_REPAIR.md` | This report |

**Not changed:** `config/autonomy.json`, API/server routes, execution code, approval implementation handlers.

---

## Tests quarantined?

**No.** All fixes are expectation/contract alignment and test isolation. No tests marked skip/xfail.

---

## Targeted gateway tests after

**Primary files:**

```bash
python -m pytest tests/test_gateways_smoke.py tests/test_e2e_workflow.py -q
```

| Result | Count |
|--------|-------|
| Passed | **18** |
| Failed | **0** |
| Exit | 0 |

**Broad `-k` filter:**

```bash
python -m pytest -q -k "gateway or smoke or e2e"
```

| Result | Count |
|--------|-------|
| Passed | **70** |
| Failed | **3** (UI smoke ×2, review-queue restart ×1 — out of scope) |
| Exit | 1 |

---

## Related safety gates (post-repair)

| Check | Command | Result |
|-------|---------|--------|
| API approval files | `python -m pytest tests/test_elysia_api_approval_implementation.py tests/test_approval_store_smoke.py -q` | **23 passed**, exit 0 |
| Passive Phase 2 | six `test_live_action_*` modules | **92 passed**, exit 0 |
| Safe Observer (text) | `python scripts/run_elysia_dry_run_report.py --mode real-planning` | **SAFE**, exit 0, `execution_call_count: 0` |
| Safe Observer (JSON) | `... --json` | **SAFE**, exit 0 |
| Safe-stack smoke | `python scripts/run_safe_stack_smoke_tests.py` | **454 passed**, exit 0 |
| Full collection | `python -m pytest --collect-only -q` | **449 collected**, exit 0 |

---

## Proof gateway safety was not weakened

- Gateway smoke tests still mock network/subprocess; no live internet or shell execution in smoke paths.
- Approval replay tests validate **context-hash matching** (fail-closed on mismatch) — not bypassed.
- `/approve`, `/status`, `/implement` API paths unchanged (`57e66bb` passive contract); **23/23** API approval tests pass.
- No new routes, no autonomy enablement, no live execution run during repair.

---

## Safety statement

- **Autonomy enabled?** No — `config/autonomy.json` remains `"enabled": false`
- **Live execution run?** No
- **Tools/capabilities executed?** No (Safe Observer: `execution_call_count: 0`)
- **New API/server routes?** No
- **Execution code added?** No
- **Approval safety weakened?** No

---

## Remaining blocker clusters

| Cluster | Status after this milestone |
|---------|----------------------------|
| Gateway smoke (`test_gateways_smoke.py`) | **Resolved** — 14/14 |
| E2E mutation workflow (`test_e2e_workflow.py`) | **Resolved** — 4/4 |
| Artifact/run_once policy | Open |
| UI residual (`test_ui_smoke.py`) | Open — 2 failures in broad `-k` filter |
| Router/task telemetry | Open |
| Auto cleanup / environment cleanup | Open |
| Broad approval-adjacent (`test_review_queue_smoke` restart tolerance) | Open — 1 failure in broad `-k` filter |
