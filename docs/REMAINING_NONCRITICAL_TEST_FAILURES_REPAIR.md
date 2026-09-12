# Remaining Non-Critical Test Failures Repair

## Starting checkpoint

**HEAD:** `6d305d0 fix(autonomy): update passive live readiness evidence`

**Date:** 2026-06-14

**Milestone type:** Narrow test-only repairs + passive readiness evidence update.

---

## Exact 3 failures (from post-repair classification)

| # | Test | Module |
|---|------|--------|
| 1 | `test_embeddings_enabled_after_startup` | `tests/test_lazy_embeddings.py` |
| 2 | `test_governance_cloud_executor_with_key` | `tests/test_router_rules.py` |
| 3 | `test_invalid_intents_escalate_cloud_serial` | `tests/test_router_telemetry_adapt.py` |

---

## Before results

**Command:**

```bash
python -m pytest tests/test_lazy_embeddings.py::test_embeddings_enabled_after_startup \
  tests/test_router_rules.py::test_governance_cloud_executor_with_key \
  tests/test_router_telemetry_adapt.py::test_invalid_intents_escalate_cloud_serial -q -v
```

| Outcome | Count |
|---------|-------|
| Passed | 2 |
| Failed | 1 |
| Exit code | 1 |

**Raw output (local):** `REPORTS/_remaining_noncritical_before.txt`

### Before failure detail

| Test | Failure | Notes |
|------|---------|-------|
| `test_embeddings_enabled_after_startup` | `add_memory` not called | `remember("Test memory")` skipped by `is_embedding_entirely_skipped` (text < 16 chars) |
| `test_governance_cloud_executor_with_key` | (passed in isolation; failed in full run) | Full-run: `openai_insufficient_quota` → local fallback `ollama:llama3.2:3b` |
| `test_invalid_intents_escalate_cloud_serial` | (passed in isolation; failed in full run) | Full-run: `openai_unavailable_local_fallback` → `ollama:mistral` |

---

## Classifications

| Test | Classification |
|------|----------------|
| `test_embeddings_enabled_after_startup` | **LAZY_EMBEDDINGS_SCHEMA_DRIFT** / **TEST_EXPECTATION_OUTDATED** — memory noise gates evolved; short test string no longer triggers embedding path |
| `test_governance_cloud_executor_with_key` | **ROUTER_FALLBACK_CONTRACT_DRIFT** / **ENVIRONMENT_DEPENDENT** — test assumed cloud executor when OpenAI quota/degraded state blocks routing |
| `test_invalid_intents_escalate_cloud_serial` | **ROUTER_FALLBACK_CONTRACT_DRIFT** / **ENVIRONMENT_DEPENDENT** — same; policy correctly falls back locally when `openai_usable_for_routing()` is false |

**Not classified as:** safety regression, passive-contract regression, or waiver-only (all three repaired with test-only changes).

---

## Repairs chosen (no waivers)

| Test | Repair |
|------|--------|
| Lazy embeddings | Use substantive memory text (≥16 chars, passes embed gates) and `priority=0.6` |
| Router governance cloud | `monkeypatch` `openai_usable_for_routing` → `True` for deterministic cloud-escalation assertion |
| Router telemetry cloud | Same `openai_usable_for_routing` mock — no runtime behavior change |

**No production code changed.** Runtime local-fallback when OpenAI unavailable remains correct.

---

## Files changed

- `tests/test_lazy_embeddings.py`
- `tests/test_router_rules.py`
- `tests/test_router_telemetry_adapt.py`
- `project_guardian/live_action_readiness.py` — evidence counts updated; waiver check now passes
- `project_guardian/tests/test_live_action_readiness.py` — assert repaired evidence
- `docs/REMAINING_NONCRITICAL_TEST_FAILURES_REPAIR.md` — this document

**Not changed:** `project_guardian/core.py`, `elysia/api/server.py`, `config/autonomy.json`

---

## After results (exact 3 tests)

**Command:** same as before

| Outcome | Count |
|---------|-------|
| Passed | 3 |
| Failed | 0 |
| Exit code | 0 |
| Duration | ~8.2s |

---

## Full pytest

**Command:** `python -m pytest -q`

See `REPORTS/_remaining_noncritical_full_pytest.txt` for full-run outcome after repairs.

**Actual:** **439 passed, 0 failed, 11 skipped**, exit 0, ~524s. Full runtime suite is **clean**.

---

## Readiness impact

| Field | Before | After |
|-------|--------|-------|
| `FULL_RUNTIME_FAILURE_COUNT` | 3 | **0** |
| `FULL_RUNTIME_REMAINING_FAILURES_WAIVED_OR_REPAIRED` | false | **true** |
| `ready_for_limited_live_mode` | false | **false** (unchanged) |
| `status` | BLOCKED | **BLOCKED** (unchanged) |

Full-runtime test gate cleared. **Limited live mode remains blocked** by:

- Missing live executor
- Missing UI/API approval route
- Missing harmless live-action smoke
- `config/autonomy.json` disabled by design

---

## Safety statement

- **Autonomy not enabled** — `config/autonomy.json` → `"enabled": false`
- **No live execution run**
- **No API/server routes added**
- **No live executor added**
- **No execution code added**
- **No real repo mutation performed**
- **Readiness not marked READY**

---

## Remaining blockers

1. Approval-gated live executor (future)
2. UI/API approval route (future)
3. Harmless live-action smoke (future)
4. Operator opt-in for autonomy config (future)

---

## Related docs

- `docs/FULL_RUNTIME_TEST_CLASSIFICATION_POST_REPAIRS.md`
- `docs/LIVE_MODE_READINESS_POST_REPAIR_UPDATE.md`
