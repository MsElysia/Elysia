# Live-Mode Readiness Post-Repair Update

## Starting checkpoint

**HEAD:** `ed295ca docs(tests): refresh full runtime classification after repairs`

**Date:** 2026-06-14

**Milestone type:** Passive readiness evidence + documentation update only.

---

## Post-repair full runtime result

From `docs/FULL_RUNTIME_TEST_CLASSIFICATION_POST_REPAIRS.md`:

| Metric | Value |
|--------|-------|
| Passed | **436** |
| Failed | **3** |
| Errors | **0** |
| Skipped | **11** |
| Collected | **450** |

### Remaining 3 failures (non-safety-critical)

| Test | Classification |
|------|----------------|
| `test_lazy_embeddings.py::test_embeddings_enabled_after_startup` | Environment / optional-deps drift |
| `test_router_rules.py::test_governance_cloud_executor_with_key` | Router local-fallback when OpenAI quota unavailable |
| `test_router_telemetry_adapt.py::test_invalid_intents_escalate_cloud_serial` | Router local-fallback when OpenAI unavailable |

All repaired blocker clusters (no-side-effects, API approval, gateway/e2e, review queue, artifact/run_once, UI residual, router telemetry core, memory cleanup, UI diff/basehash, task/mutation fixtures) are **green** in full run.

---

## Old readiness blocker updates

| Prior blocker text | Prior evidence | **Post-repair state** |
|--------------------|----------------|------------------------|
| Full runtime tests not classified | `FULL_RUNTIME_TESTS_CLASSIFIED=false` | **`FULL_RUNTIME_TESTS_CLASSIFIED=true`** — classified in `docs/FULL_RUNTIME_TEST_CLASSIFICATION_POST_REPAIRS.md` |
| (implicit) many failures remain | 47 failures at 2026-06-04 refresh | **3 failures remain**, all documented non-safety-critical |
| Broad classification gap | next_required_actions included "Classify full runtime" | Replaced by **`FULL_RUNTIME_REMAINING_NONCRITICAL_FAILURES_NEED_WAIVER_OR_REPAIR`** next action |

---

## Current readiness blockers (unchanged product gates)

Default `evaluate_live_mode_readiness()` remains **`BLOCKED`** / **`NOT_READY_FOR_LIVE_MODE`**.

| Blocker | Still active? |
|---------|---------------|
| Missing live executor | **Yes** — `LIVE_EXECUTOR_IMPLEMENTED=false` |
| Missing UI/API approval route | **Yes** — `UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED=false` |
| Missing harmless live-action smoke | **Yes** — `HARMLESS_LIVE_ACTION_SMOKE_VERIFIED=false` |
| `config/autonomy.json` disabled | **Yes** (by design) — `AUTONOMY_CONFIG_DEFAULT_DISABLED=true` |
| Remaining 3 full-runtime failures | **Yes (non-blocker)** — `FULL_RUNTIME_REMAINING_NONCRITICAL_FAILURES_WAIVED_OR_REPAIRED=false` |

Limited live mode **must not** be enabled until executor, approval route, harmless smoke, and waiver/repair for remaining 3 tests are addressed.

---

## Readiness code changes

| File | Change |
|------|--------|
| `project_guardian/live_action_readiness.py` | `FULL_RUNTIME_TESTS_CLASSIFIED` default **true**; new check `FULL_RUNTIME_REMAINING_NONCRITICAL_FAILURES_WAIVED_OR_REPAIRED` default **false**; `DEFAULT_RUNTIME_TEST_EVIDENCE` metadata; serializer includes `runtime_test_evidence` |
| `project_guardian/tests/test_live_action_readiness.py` | Assert classification passes, waiver/repair pending, runtime evidence fields, readiness still blocked |

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`

### New default runtime test evidence fields

```json
{
  "FULL_RUNTIME_CLASSIFIED_POST_REPAIRS": true,
  "FULL_RUNTIME_FAILURE_COUNT": 3,
  "FULL_RUNTIME_ERROR_COUNT": 0,
  "FULL_RUNTIME_REMAINING_FAILURES_NON_SAFETY_CRITICAL": true,
  "FULL_RUNTIME_PASS_COUNT": 436,
  "FULL_RUNTIME_SKIP_COUNT": 11,
  "CLASSIFICATION_DOC": "docs/FULL_RUNTIME_TEST_CLASSIFICATION_POST_REPAIRS.md"
}
```

---

## Readiness status after update

| Field | Value |
|-------|-------|
| `status` | `BLOCKED` |
| `ready_for_limited_live_mode` | `false` |
| `safety_verdict` | `NOT_READY_FOR_LIVE_MODE` |

Setting all boolean evidence to `true` in tests still yields `READY` only in synthetic override — **production defaults do not grant live mode**.

---

## Safety statement

- **Autonomy not enabled** — `config/autonomy.json` → `"enabled": false` (unchanged)
- **No live execution run**
- **No API/server routes added**
- **No execution code added**
- **No live executor added**
- **No real repo mutation performed**
- **Limited live mode remains blocked**

---

## Remaining blockers (next milestones)

1. Implement approval-gated live executor (future)
2. Implement UI/API approval route (future)
3. Verify harmless live-action smoke (future)
4. Repair or obtain operator waiver for 3 non-safety-critical full-runtime failures
5. Operator opt-in for `config/autonomy.json` (explicit, future)

---

## Related docs

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_POST_REPAIRS.md`
- `docs/PHASE2_PASSIVE_SAFETY_STACK_BASELINE.md`
- `docs/PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`
- `docs/API_APPROVAL_EXECUTION_BEHAVIOR_REPAIR.md`
