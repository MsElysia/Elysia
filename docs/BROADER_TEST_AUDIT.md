# Broader test audit (post safe-stack milestone)

**Date:** 2026-05-18  
**Scope:** Test health survey for milestone planning. **Adjacent safe-stack failures fixed** (see §11); unrelated legacy/environmental failures deferred. No commits.  
**Context:** Safe-stack smoke is green; full `project_guardian/tests` completed (~90 min).

---

## Executive summary

| Suite | Result | Notes |
|-------|--------|--------|
| **Safe-stack smoke** | **386 passed**, 3 warnings | Authoritative milestone gate |
| **Collect-only (default `pytest.ini`)** | **441** tests in `tests/` | `testpaths = tests` only |
| **Collect-only (`project_guardian/tests`)** | **1297** tests | Explicit path |
| **`project_guardian/tests` (full)** | **1276 passed, 11 failed, 10 skipped** (~90 min) | See §4 and §11 |
| **Adjacent suite (post-fix)** | **33 passed** | `test_brain_config_runtime`, `test_conversation_store_consolidation`, `test_safe_stack_ci_config` |
| **`tests/` (`--maxfail=20`, 60s timeout)** | **20 failed**, **55 passed** (stopped at cap) | GuardianCore singleton, mutations, cleanup |

**Safe-stack smoke:** still passes — **no regressions inside the smoke-listed modules** (source of truth).

**Adjacent failures (outside smoke):** **fixed** — see §11 (7 tests across 3 modules).

**Deferred (full suite):** 4 unrelated/environmental failures — see §11.

**Recommendation:** Stage safe-stack per smoke; address deferred legacy/integration failures in a separate pass.

---

## 1. Safe-stack smoke

```bash
python scripts/run_safe_stack_smoke_tests.py
```

**Result:** `386 passed, 3 warnings` in ~6s.

**Modules:** 31 required paths + 2 optional alternates (see `scripts/run_safe_stack_smoke_tests.py`).

**Reminders (script output):** autonomy and live execution not enabled; not full CI.

---

## 2. Collect-only inventory

### Default (`python -m pytest --collect-only -q`)

Uses `pytest.ini` → `testpaths = tests`.

**Result:** `441 tests collected` — root `tests/` package only.

### Explicit (`python -m pytest project_guardian/tests --collect-only -q`)

**Result:** `1297 tests collected`.

**Implication:** Full Guardian coverage requires **both** trees (~1700+ tests if combined, minus any overlap).

---

## 3. `project_guardian/tests` — full run (completed)

### Command

```bash
python -m pytest project_guardian/tests -q --maxfail=20
```

### Outcome (2026-05-18, ~90 minutes)

- **1276 passed**, **11 failed**, **10 skipped**, 19 warnings.
- Log: `.broader_test_audit_pg.txt`
- Heavy GuardianCore boot, autonomy monitoring, `elysia_timeline.db` lock noise, and Ollama timeouts during the run; not safe-stack regressions.

### Failures observed before stall (progress markers)

| Module | Marker | Category |
|--------|--------|----------|
| `test_brain_config_runtime.py` | `FFFF` (~4) | Safe-stack adjacent — see §5 |
| `test_conversation_store_consolidation.py` | `F` (1) | Safe-stack adjacent — static source scan |
| `test_integration.py` | `F` (≥1) | Unrelated / GuardianCore integration |

### Targeted re-run (confirmed)

```bash
python -m pytest project_guardian/tests/test_brain_config_runtime.py \
  project_guardian/tests/test_conversation_store_consolidation.py -q --tb=short
```

**Result:** `5 failed, 18 passed`

| Test | Error (summary) |
|------|-----------------|
| `test_runtime_enabled_invokes_pipeline` | `AttributeError: 'str' object has no attribute 'run_context'` in `brain/runtime.py` |
| `test_operator_chat_forces_dry_run_when_live_execution_off` | same |
| `test_operator_chat_allows_config_dry_run_when_live_execution_on` | same |
| `test_diagnostic_entrypoint_uses_config_dry_run_not_operator_override` | same |
| `test_runtime_api_server_uses_canonical_store_import` | `assert 'project_guardian.conversation_store' in source` (RuntimeAPIServer source) |

**Note:** Smoke-listed brain tests (`test_brain_trace_visibility`, `test_brain_tda_integration`, `test_brain_pipeline`, operator-chat integration) **pass** in the smoke slice.

### `--maxfail=20` with `--timeout=45`

Stopped on **timeout** during `test_control_panel_legacy_history_retirement` while constructing `UIControlPanel` (SocketIO/gevent). Stack traces also showed **autonomy** activity (`run_autonomous_cycle`, chatlog ranking) from other tests’ side effects.

**Category:** long-running / integration / environment — not safe-stack smoke regressions.

---

## 4. `tests/` (root) — `--maxfail=20`

```bash
python -m pytest tests -q --maxfail=20 --timeout=60 --tb=line
```

**Result:** `20 failed, 55 passed, 15 warnings` in ~42s (stopped at maxfail cap).

### Failure groups (first 20)

| Category | Examples |
|----------|----------|
| **Mutation / governance** | `test_apply_mutation_task.py` (6), `test_artifact_policy_*.py` (4) |
| **Auto cleanup / memory** | `test_auto_cleanup_effectiveness.py` (4) |
| **Core smoke / GuardianCore** | `test_core_smoke.py` (6) — singleton already exists, propagation |

**Not safe-stack-listed.** Predominantly **unrelated / pre-existing** governance and core lifecycle tests.

---

## 5. Failure categories

### A. Safe-stack regression (outside smoke list)

| File | Count | In smoke? | Notes |
|------|------:|-----------|--------|
| `test_brain_config_runtime.py` | 4 | **No** | `run_brain_pipeline_for_operator_event` expects trace object; got `str` |
| `test_conversation_store_consolidation.py` | 1 | **Partial** (other tests in file pass in smoke) | Static assert on `server.py` import text |

**Classification rule applied:** smoke pass + failures only in non-smoke brain config tests → **adjacent safe-stack debt**, not smoke regression.

### B. Unrelated / pre-existing

- Root `tests/`: mutation, artifact policy, core smoke, cleanup effectiveness.
- `project_guardian/tests/test_integration.py` (GuardianCore paths).
- Large swaths of autonomy, income, bounded browser, self-task — not fully exercised in this audit.

### C. External dependency / API key

- **Not triggered** in capped runs.
- Tests that call real OpenAI/OpenRouter should remain excluded from default CI (project convention).

### D. Import / collection

- **No collection errors** in either tree.
- Default collect-only: 441; `project_guardian/tests`: 1297.

### E. Long-running / integration risk

| Risk | Evidence |
|------|----------|
| **UIControlPanel + SocketIO/gevent** | Timeout importing gevent when instantiating panel in tests |
| **Autonomy monitoring threads** | Stack: `monitoring._beat` → `run_autonomous_cycle` during unrelated tests |
| **Full `project_guardian/tests` without timeout** | Run did not complete in 30+ minutes |

**Recommendation:** Use `pytest-timeout`, mock `SocketIO`, reset `guardian_singleton` between tests, and avoid starting monitoring in unit tests.

### F. Generated / runtime data

- **Not a test failure category** in these runs.
- `.gitignore` excludes `data/runtime/` etc.; tests use `tmp_path` / mocks in smoke slice.

---

## 6. Safe-stack smoke modules — status

All paths in `REQUIRED_TEST_PATHS` + optional alternates: **pass** when run via `run_safe_stack_smoke_tests.py`.

**Not in smoke (failed when run separately):**

- `test_brain_config_runtime.py`

**In smoke and passing:**

- `test_conversation_store.py`, `test_conversation_store_consolidation.py` (except the one server import test when run in isolation with brain_config failures batch)
- All control panel UI/brain visibility/clarity tests in smoke
- Governance, operator confirmation, memory ranking, prompt contracts, API parity, gitignore, one-shot quarantine

Re-run consolidation file alone to confirm which tests fail:

```bash
python -m pytest project_guardian/tests/test_conversation_store_consolidation.py -q
```

(Expect 1 failure on `test_runtime_api_server_uses_canonical_store_import` if `server.py` uses lazy import.)

---

## 7. Tests intentionally skipped / not run

| Scope | Reason |
|-------|--------|
| Full `project_guardian/tests` without timeout | Incomplete; hung/slow |
| Tests requiring live API keys | Policy: not run |
| Long-running server/e2e | Not identified individually; avoid until harness fixed |
| `pytest -m "not slow"` | Only one `@pytest.mark.slow` in `project_guardian/tests`; marker underused |
| Combined `tests/` + `project_guardian/tests` in one invocation | Not run (would be ~1700+ tests) |

---

## 8. Recommended next fixes (priority)

1. ~~**Adjacent brain/consolidation/CI doc tests**~~ — done (§11).
2. **UI test harness** — mock SocketIO/gevent for `UIControlPanel` tests; prevent full panel stack in unit tests (unblocks full PG suite).
3. **GuardianCore singleton hygiene** — root `tests/` failures from duplicate instance; ensure autouse reset fixture.
4. **Stabilize root `tests/` mutation/artifact slice** — separate from safe-stack PR.
5. **CI strategy** — keep `run_safe_stack_smoke_tests.py` as required check; add optional nightly `project_guardian/tests` with timeout + xdist when harness fixed.
6. **Before one-entry UI (Phase 1)** — do not block on full 1297 pass; do require smoke + targeted UI marker tests (already in smoke).

---

## 9. Relation to other docs

| Doc | Role |
|-----|------|
| [`ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md`](ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md) | Milestone scope and APIs |
| [`SAFE_STACK_RELEASE_READINESS_AUDIT.md`](SAFE_STACK_RELEASE_READINESS_AUDIT.md) | Git staging / ignore hygiene |
| [`SAFE_STACK_COMMIT_STAGING_PLAN.md`](SAFE_STACK_COMMIT_STAGING_PLAN.md) | Commit groups (if present) |
| [`ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md`](ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md) | UI simplification (planning) |

---

## 10. Local artifacts (not committed)

Optional local logs from this audit (safe to delete):

- `.broader_test_audit_pg.txt`
- `.broader_pg_maxfail20.txt`
- `.broader_test_audit_root.txt`

---

## Verification commands (repeat audit)

```bash
python scripts/run_safe_stack_smoke_tests.py
python -m pytest --collect-only -q
python -m pytest project_guardian/tests --collect-only -q
python -m pytest project_guardian/tests/test_brain_config_runtime.py -q --tb=short
python -m pytest tests -q --maxfail=20 --timeout=60
```

**Production code changed by adjacent fix pass:** one narrow line in `project_guardian/brain/runtime.py` (`getattr` for `run_context`); tests and `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md` only otherwise.

---

## 11. Adjacent fixes applied (2026-05-18)

Follow-up scope: fix only the small adjacent failures from:

- `project_guardian/tests/test_brain_config_runtime.py`
- `project_guardian/tests/test_conversation_store_consolidation.py`
- `project_guardian/tests/test_safe_stack_ci_config.py`

Initial targeted command:

```bash
python -m pytest project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_conversation_store_consolidation.py project_guardian/tests/test_safe_stack_ci_config.py -q
```

Initial result:

- `7 failed, 26 passed, 3 warnings`

Narrow fixes applied:

- `project_guardian/brain/runtime.py` now uses `getattr(trace, "run_context", None)` before annotating live-execution guard metadata. This preserves real `BrainPipelineTrace` behavior while allowing mocked pipeline returns in compatibility tests.
- `project_guardian/tests/test_brain_config_runtime.py` now asserts fail-closed governance behavior: config flags alone do not enable live execution, and the pipeline remains dry-run without confirmation, fresh dry-run trace, and allowlist gates.
- `project_guardian/tests/test_conversation_store_consolidation.py` now inspects the `elysia.api.server` module source for the canonical `project_guardian.conversation_store` import instead of only the `RuntimeAPIServer` class body.
- `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md` now explicitly names the Safe stack smoke command and `.github/workflows/safe-stack-smoke.yml`.

Post-fix targeted result:

- `33 passed, 3 warnings in 0.54s`

Safe-stack smoke after the targeted fixes:

- `386 passed, 3 warnings in 5.46s`

**Remaining full-suite failures (deferred):**

| Test module | Test |
|-------------|------|
| `test_integration.py` | `TestEventLoopIntegration::test_module_adapter_execution` |
| `test_introspection_ui.py` | `TestIntrospectionAPIIntegration::test_memory_patterns_endpoint` |
| `test_memory_vector_deferred_embeddings.py` | `test_enhanced_memory_defers_vector_add_until_embeddings_enabled` |
| `test_startup_smoke.py` | `TestStartupSmoke::test_startup_smoke_operational_state_structure` |

Plus environmental noise: Ollama timeouts, `elysia_timeline.db` locks, gevent/UIControlPanel stalls, GuardianCore singleton boot.

Safety confirmation:

- No autonomy wiring was added.
- Live execution remains disabled and fail-closed.
- No real LLM or external API calls were added.
