### SOURCE VERIFIED PRODUCT

- SHA: `776647f80f7d08810f1655c7a2b02fe597c385af`
- Branch (historical): `cursor/guardian-23-construct-without-activate`
- Role: **reference only** — source Vega/dynamic PASS **does not transfer** to the restack product.

### TARGET BASE

- Port start tip: `4ff2dc92dd7d9bc393225bce35de9239a9cad6a5` (`autopilot-003-issue23-restack` at port time)
- Official restack tip at handoff fetch: `d791084e716dfcfdaa686374276611ebc0e2a0e6` (`restack(#23): add missing GuardianCore test helper dependency`)
- Product was **not** fast-forwarded onto `d791084`; merge-base with current restack tip remains `4ff2dc9`. Integration may need reconcile onto tip before merge.

### TARGET PRODUCT

- Branch: `cursor/autopilot-003-issue23-restack-cwa`
- SHA: `7374820642fad52a6264c86df8632c3a630df592` (**confirmed on origin**; docs tip `881608c` = inspection report only)
- Single product commit: `fix(guardian): restack construct-without-activate onto AUTOPILOT-003 (#23)`
- Worktree (implementation): `.worktrees/autopilot-003-issue23-restack`

### SEMANTIC PORT MAP

- `docs/ISSUE-23-RESTACK-CWA-PORT-MAP.md` (on product SHA `7374820`)
- Rule: port **semantics**; do **not** cherry-pick / merge `776647f` history wholesale.

### FILES CHANGED

Relative to target base `4ff2dc9` → product `7374820` (20 files, +1468 / −100):

- `project_guardian/core.py` — construct-safe `_initialize_system` + explicit `activate()`
- `project_guardian/guardian_singleton.py` — singleton conflict / get_existing / bg guard
- `elysia_sub_guardian.py`, `elysia.py`, callers (`run_elysia.py`, `start_*`, `elysia_interface.py`)
- `project_guardian/module_activity.py`, `project_guardian/planner_readiness.py` (lineage helpers)
- Tests: `tests/test_guardian_audit_bootstrap.py`, `tests/test_guardian_construct_without_activate.py`, stubs/helpers
- Docs: Issue #23 CWA / audit / side-effect map / port map

### TESTS

- Issue #23 CWA suites previously: **20/20** (`test_guardian_audit_bootstrap` + `test_guardian_construct_without_activate`)
- Vega reconfirm: **20 passed** at product SHA `7374820` (see VEGA)

### TARGET-LINEAGE REGRESSION TESTS

- Prior control-plane / #22 lineage spot: **147** tests reported in prior orchestrator notes (environment-dependent; not re-executed in this handoff turn)
- Vega note: some lineage collections may ERROR on missing `pyttsx3` without stub installer — treat as **environment residual**, not automatic CWA falsification

### DYNAMIC INSPECTION

- **DONE for restack product `7374820`**
- Report: `docs/AUTOPILOT-003-DYNAMIC-INSPECTION-RESTACK-20260911.md` on `cursor/autopilot-003-issue23-restack-cwa` @ `881608c`
- Method: construct / `get_guardian_core` only (no `activate()`, probes, or loop starts); double cycle + supplemental EAI pass
- Key results: both primary cycles `_activated=False`, `_running=False`; zero socket/subprocess/Thread/provider/probe trap hits during construct/inspect/teardown; fresh component classifications in report
- Source-only report `docs/AUTOPILOT-003-DYNAMIC-INSPECTION-CWA-20260911.md` @ `d6c5ad3` remains reference for SHA `776647f` only

### VEGA

- Report: `docs/VEGA-ISSUE-23-RESTACK-CWA-REVERIFY-20260911.md`
- Branch: `codex/vega-reverify-23-restack-cwa` @ `40bebe6`
- Target SHA verified: `7374820642fad52a6264c86df8632c3a630df592`
- **Verdict: PASS** (confidence 0.86)

### ARCHITECTURE REVIEW

- Report: `docs/ARCHITECTURE-REVIEW-ISSUE-23-RESTACK-CWA-20260911.md`
- Branch: `codex/arch-review-23-restack-cwa` @ `998c60d`
- Product SHA reviewed: `7374820642fad52a6264c86df8632c3a630df592`
- **Verdict: READY_FOR_INTEGRATION_REVIEW** (confidence 0.84)

### KNOWN NON-INHERITED VERIFICATION (PR #25 not inherited)

- **PR #25 claim-boundary is NOT inherited** by this restack unless the claim-boundary product surface is present **and** retested on this tip.
- Architecture review explicitly: no #25 claim-boundary surface was proven as part of `7374820`; manifest “preserve #22/#25” language is a port requirement, **not** evidence #25 landed.
- Do not treat #25 verification as satisfied by Issue #23 CWA restack alone.

### REMAINING ISSUES

1. Public `ensure_monitoring_started` can start monitors/loop **without** setting `_activated` (parallel/legacy API residual; construct path does not call it).
2. Stale `docs/boot_memory_map.md` still claims `_initialize_system` starts monitoring — false on `7374820`.
3. Phase B deferred ops after `activate` (operational nuance; not construct collapse).
4. Official `autopilot-003-issue23-restack` tip moved to `d791084` after port base `4ff2dc9` — reconcile before merge if required.
5. **NEW (bounded follow-up):** `GuardianLayer` construct can hang when `enable_guardian_layer=True` (0 `Thread.start` hits — construct stall in fingerprint path, not an activate leak). Tip CWA tests already set `enable_guardian_layer=False`. Not gate FAIL; do not reopen full CWA repair unless construct-time operational activation is proven.
6. Cosmetic: CWA doc branch header may still name source branch.

### NEXT BOUNDED TASK

1. Human/governance: authenticate `gh` → open/update this **draft** PR; post CURRENT ENGINEERING CHECKPOINT on #11 and status on #23.
2. Optional bounded follow-up: investigate/fix `GuardianLayer` construct hang when enabled (Windows fingerprint / `platform.processor()` path) — keep out of default CWA inspect config until fixed.
3. Integration: reconcile product onto current `autopilot-003-issue23-restack` tip (`d791084`) if required; do **not** FF-overwrite product blindly.
4. Leave #23 open with `IMPLEMENTATION_COMPLETE_ON_RESTACK_PENDING_INTEGRATION` until policy + verifier support close.
