# No-side-effects and invariants repair

## Starting checkpoint

**HEAD:** `d6b27d8 docs(tests): refresh full runtime classification`

**Date:** 2026-06-04

**Context:** Full runtime refresh reported **10 failures** in safety-relevant clusters (`test_invariants.py` ×5, `test_no_side_effects_*.py` ×5). This milestone repairs or correctly scopes them without enabling autonomy or live execution.

---

## Targeted tests before

**Command:** `python -m pytest -q -k "no_side_effect or side_effect or invariant or invariants or any_executed or execution_call_count or legacy_fallback_reached"`

| Result | Count |
|--------|-------|
| Failed | **10** |
| Passed | 19 |
| Skipped | 1 |
| Duration | ~31.5s |

**Exact file run:** `tests/test_invariants.py`, `tests/test_no_side_effects_{mutation,network,subprocess,task_engine}.py`

---

## Root causes (classified)

| Failure | Classification | Root cause |
|---------|----------------|------------|
| Trust replay (2) | **REAL_SAFETY_REGRESSION** + **TEST_EXPECTATION_OUTDATED** | `WebReader.fetch` used undefined `domain` instead of `host`; approval context in tests did not match current `gate_context` schema |
| Bypass network (1) | **TEST_EXPECTATION_OUTDATED** | Stale `_is_documented_exception` call after TASK-0037 allowlist removal; repo-wide import scan not aligned with gateway-module scope |
| Bypass file/subprocess (2) | **TEST_EXPECTATION_OUTDATED** | Repo-wide AST scan flagged persistence layers; invariant 5 refocused to gateway modules per TASK-0037 |
| `get_pending` (4) | **TEST_EXPECTATION_OUTDATED** | API renamed to `ReviewQueue.list_pending()` |
| Review queue count (4) | **MISSING_TEST_ISOLATION** | Default `REPORTS/review_queue.jsonl` shared across tests |
| Task engine denial (1) | **TEST_EXPECTATION_OUTDATED** | Preflight returns `error`/`MUTATION_PAYLOAD_INVALID` for `..` in payload (same safety: no writes) |

---

## Files changed

| File | Change |
|------|--------|
| `project_guardian/external.py` | Fix `domain` → `host` in approval replay path (NameError / trust denial bug) |
| `tests/test_invariants.py` | Gateway-scoped bypass AST; trust replay context + mock; remove dead `_is_documented_exception` usage |
| `tests/test_no_side_effects_mutation.py` | `list_pending()` + isolated `queue_file` fixture |
| `tests/test_no_side_effects_network.py` | `list_pending()` + isolated `queue_file` fixture |
| `tests/test_no_side_effects_subprocess.py` | `list_pending()` + isolated `queue_file` fixture |
| `tests/test_no_side_effects_task_engine.py` | Assert `MUTATION_PAYLOAD_INVALID` preflight (no writes) |

**Tests quarantined:** **No** — failures repaired or scoped; safety meaning preserved.

---

## Targeted tests after

**Same `-k` filter:**

| Result | Count |
|--------|-------|
| Passed | **29** |
| Failed | **0** |
| Skipped | 1 |
| Duration | ~92.5s |

---

## Safety checks

| Check | Result |
|-------|--------|
| `python scripts/run_elysia_dry_run_report.py` | **SAFE**, exit 0 |
| `python scripts/run_elysia_dry_run_report.py --json` | `"safety_verdict": "SAFE"`, `any_executed: false`, `execution_call_count: 0`, `legacy_fallback_reached: false` |
| `python scripts/run_elysia_dry_run_report.py --mode real-planning` | **SAFE**, exit 0 |
| `python scripts/run_elysia_dry_run_report.py --mode real-planning --json` | Same safety fields, all cycles blocked |
| Passive Phase 2 (6 modules) | **92 passed** |
| Safe-stack smoke | **454 passed** |
| Full collection | **449 tests collected** |

---

## Proof safety was not weakened

- No-side-effects tests still assert **no file writes/backups** on deny/review paths.
- Invariant 5 still **AST-scans gateway modules** and fails on ungated calls outside approved methods (`fetch`, `request_json`, `apply`, `write_file`, `run_command`, `run_command_background`, `__init__` session setup).
- Trust replay tests use **full `gate_context`** matching production `WebReader.fetch`.
- Dry-run reports: **`any_executed=false`**, **`execution_call_count=0`**, **`legacy_fallback_reached=false`**.
- `config/autonomy.json` unchanged (`enabled: false`).

---

## Remaining blocker clusters (unchanged scope)

- API/approval implementation (`test_elysia_api_approval_implementation.py`)
- Gateway smoke drift (`test_gateways_smoke.py`)
- Artifact/run_once policy
- UI residual (`test_ui_smoke.py`, `test_ui_diff_basehash.py`)
- Router/task telemetry clusters
- Environment cleanup (`test_auto_cleanup_effectiveness.py`)

**Repo-wide persistence-layer bypass audit** (pre-TASK-0037 style full-tree AST) is **deferred** — not quarantined as passing; gateway-scoped invariant is the enforced contract.

---

## Safety statement

- Autonomy **not** enabled
- No live execution, tools, capabilities, WebScout, or browser activity run
- No API/server routes or execution/rollback code added
- `config/autonomy.json` → `"enabled": false` (unchanged)

---

## Related docs

- [`docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`](FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md)
