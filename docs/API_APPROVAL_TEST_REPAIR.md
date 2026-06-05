# API / approval test repair

## Starting checkpoint

**HEAD:** `e99bc9a fix(tests): repair no-side-effects invariants`

**Date:** 2026-06-04

**Scope:** `tests/test_elysia_api_approval_implementation.py` (9 failures in full-runtime refresh) and passive approval contract alignment with Phase 2 design (approval does not imply execution).

---

## Targeted tests before

**Exact files:**

```bash
python -m pytest tests/test_elysia_api_approval_implementation.py tests/test_approval_store_smoke.py -q
```

| Result | Count |
|--------|-------|
| Failed | **9** (`test_elysia_api_approval_implementation.py`) |
| Passed | 14 (`test_approval_store_smoke.py` + 1 chat test) |
| Exit | 1 |

**Broad `-k` filter** (includes unrelated gateway/e2e tests): 17 failed — out of milestone scope.

---

## Root causes (classified)

| Symptom | Classification |
|---------|----------------|
| `auto_implement_on_approval` TypeError | **STALE_API_EXPECTATION** — tests assumed unmerged server constructor flag |
| Approve returns no `implementation` block | **TEST_EXPECTATION_OUTDATED** — passive `/approve` only records approval |
| `/implementation/preview` 404 | **STALE_API_EXPECTATION** — route never existed; dry-run uses `POST .../implement` |
| WebScout kwargs mismatch | **STALE_API_EXPECTATION** — server passes `(topic, domain)` only |
| Injected implementer ignored on `/implement` | **MISSING_TEST_FIXTURE** — `RuntimeAPIServer._implementer` unused by route handler |

No **APPROVAL_CONTRACT_REGRESSION** in `ApprovalStore` / Phase 2 packet tests.

---

## Files changed

| File | Change |
|------|--------|
| `tests/test_elysia_api_approval_implementation.py` | Rewritten to passive approve + explicit implement; added/tracked in repo |
| `elysia/api/server.py` | Use injected `implementer` on existing `POST /implement` when provided (test harness only; no new routes) |
| `docs/API_APPROVAL_TEST_REPAIR.md` | This document |

**Tests quarantined:** **No**

---

## Targeted tests after

```bash
python -m pytest tests/test_elysia_api_approval_implementation.py tests/test_approval_store_smoke.py -q
```

| Result | Count |
|--------|-------|
| Passed | **23** |
| Failed | **0** |
| Exit | 0 |

**Contract enforced by tests:**

- `POST /api/proposals/<id>/approve` → `{status, proposal_id}` only; ignores `auto_implement`
- `POST /api/proposals/<id>/status` → status update only; ignores `implement`
- `POST /api/proposals/<id>/implement` → optional `dry_run`; separate from approval
- `GET /api/proposals/<id>/implementation` → status metadata only (no side effects)

---

## Safety checks

| Check | Result |
|-------|--------|
| Passive Phase 2 (6 modules) | **92 passed** |
| Safe Observer `--mode real-planning` | **SAFE**, exit 0 |
| Safe Observer `--mode real-planning --json` | `any_executed=false`, `execution_call_count=0`, `legacy_fallback_reached=false` |
| Safe-stack smoke | **454 passed** |
| Full collection | **449 tests collected** |

---

## Proof approval safety was not weakened

- Approval endpoint does **not** auto-implement (tests assert `implementer.calls == []` after approve).
- `auto_implement` / `implement` JSON flags are **ignored** on passive routes.
- Real file mutation tests require **explicit** `POST /implement` after approve (isolated `tmp_path` fixtures).
- No new routes; no autonomy enablement; no live executor wiring.

---

## Remaining blocker clusters

- Gateway smoke drift (`test_gateways_smoke.py`)
- Artifact/run_once policy (`test_artifact_policy_*.py`, `test_apply_mutation_task.py`)
- UI residual (`test_ui_smoke.py`, `test_ui_diff_basehash.py`)
- Router/task telemetry (`test_router_*`, `test_task_execution.py`)
- Environment cleanup (`test_auto_cleanup_effectiveness.py`)
- Other approval-adjacent failures under broad `-k` (e2e workflow, gateway replay) — **not** in `test_elysia_api_approval_implementation.py`

---

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged)
- No live execution, tools, capabilities, WebScout, or browser activity run for this milestone
- **No new** API/server routes added
- No rollback or live executor code added
- Approve remains passive; implement remains operator-initiated via existing route

---

## Related docs

- [`docs/FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md`](FULL_RUNTIME_TEST_CLASSIFICATION_REFRESH.md)
- [`docs/NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md`](NO_SIDE_EFFECTS_INVARIANTS_REPAIR.md)
- [`docs/PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`](PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md)
