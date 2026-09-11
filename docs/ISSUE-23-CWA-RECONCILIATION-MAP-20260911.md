# Issue #23 CWA Integration Reconciliation Map

**Date:** 2026-09-11  
**Phase:** AUTOPILOT-003 Phase 1 — refresh + three-way map only (no product port)  
**Map branch:** `cursor/autopilot-003-issue23-cwa-reconciled` @ map commit (parent = C)  
**Repo:** MsElysia/Elysia

## Confirmed tips (after `git fetch --all --prune`)

| Ref | Role | Exact SHA | Notes |
|-----|------|-----------|-------|
| A | Old port base | `4ff2dc92dd7d9bc393225bce35de9239a9cad6a5` | `restack(#23): isolate GuardianCore test state` — **exists** |
| B | Verified CWA **product** | `7374820642fad52a6264c86df8632c3a630df592` | On `cursor/autopilot-003-issue23-restack-cwa` — **exists** |
| C | Official restack tip | `d791084e716dfcfdaa686374276611ebc0e2a0e6` | `origin/autopilot-003-issue23-restack` — **exists**; local branch name absent pre-map |
| Docs tip | Inspection-only | `881608c83fc0ec19261924034eea6e809b4b6ede` | Local + `origin/cursor/autopilot-003-issue23-restack-cwa` tip; **one commit above B** (`docs/...DYNAMIC-INSPECTION...` only) |

**Product vs docs tip:** Use **B (`7374820`)** for CWA product semantics. Do **not** treat `881608c` as product.

**Ancestry:** B and C are **siblings** under A (neither is ancestor of the other). `merge-base(B,C) = A`.

```
* 7374820  B  CWA product port
| * d791084  C  test helper dependency only
|/
* 4ff2dc9  A
```

## Branch existence check

| Branch | Local | Remote |
|--------|-------|--------|
| `cursor/autopilot-003-issue23-cwa-reconciled` | **Created this phase** (worktree from C) | **Not present** on `origin` at map start |
| Prior reconcile in progress? | **No** — safe to proceed with Phase 1 map | |

## Worktree dirty notes (do not discard)

| Worktree | HEAD / branch | Dirty? |
|----------|---------------|--------|
| `Project guardian` (main WT) | `elysia-local-reconciliation-20260909-1657` @ `4d9fceb` | **Yes** — modified docs/Python + many untracked REPORTS artifacts |
| `.worktrees/autopilot-003-issue23-restack` | `cursor/autopilot-003-issue23-restack-cwa` @ `881608c` | **Yes** — untracked inspect scripts/JSON/`_dash_out.txt` |
| `.worktrees/autopilot-003-issue23-restack-inspect-7374820` | detached `7374820` | **Yes** — untracked inspect outputs |
| `.worktrees/docs-dyn-insp-restack-20260911` | docs branch @ `ccab6c4` | Clean |
| `.worktrees/handoff-23-restack-cwa-pr` | `codex/handoff-23-restack-cwa-pr` | Clean |
| `.worktrees/vega-reverify-23-cwa` | `codex/vega-reverify-23-cwa` | Clean |
| `.worktrees/vega-23-restack-check` | `codex/vega-23-restack-check` | Untracked `.vega-ci-check/` |
| `.worktrees/autopilot-003-issue23-cwa-reconciled` | this map branch @ C | Map file only (Phase 1) |

Many other guardian-* worktrees exist; none named `*cwa-reconciled*` before this phase.

## Auth / GitHub status

- `gh auth status`: **not logged in** (no `gh` session). Public API used instead.
- **PR #34:** open **draft**; `mergeable=false`  
  - URL: https://github.com/MsElysia/Elysia/pull/34  
  - title: `draft: AUTOPILOT-003 #23 restack construct-without-activate (CWA)`  
  - base: `autopilot-003-issue23-restack` @ `d791084…`  
  - head: `cursor/autopilot-003-issue23-restack-cwa` @ `881608c…` (docs tip; product still `7374820`)
- **Issue #11 newest CURRENT ENGINEERING CHECKPOINT** (`2026-09-11T22:04:53Z`, comment id `5641159193`):  
  Status `IMPLEMENTATION_COMPLETE_ON_RESTACK_PENDING_INTEGRATION`; Architecture `READY_FOR_INTEGRATION_REVIEW`; product `7374820`; official restack tip `d791084` not FF’d; Vega PASS; dynamic inspection DONE on docs tip; residual `GuardianLayer` hang when enabled; next = draft PR #34; leave #23 open; no merge main / force-push / deploy.  
  Note: later #11 comments still flag `#29/#30/#31 HUMAN_GOVERNANCE_REQUIRED` and Erebus recurrence (#33) — checkpoint recency alone does not clear governance interlock.
- **Issue #23 latest comment** (`2026-09-11T22:05:07Z`): same status summary; Vega/Arch/inspection DONE; PR #34 opened; #23 remains open.

## Three-way logs / stats

### `git log --oneline A..B`
```
7374820 fix(guardian): restack construct-without-activate onto AUTOPILOT-003 (#23)
```

### `git log --oneline A..C`
```
d791084 restack(#23): add missing GuardianCore test helper dependency
```

### `git diff --stat A...B` (20 files, +1468/−100)
CWA product + docs + tests + tip-autonomy companions (`module_activity`, planner_readiness helpers, stubs).

### `git diff --stat A...C` (1 file, +99)
```
tests/guardian_core_test_helpers.py | 99 +++++++++++++++++++++++++++++++++++++
```

### Overlapping files (A…B ∩ A…C)
**Only:** `tests/guardian_core_test_helpers.py`

### Commit `d791084` (C tip)
- **Message:** `restack(#23): add missing GuardianCore test helper dependency`
- **Diff:** adds `tests/guardian_core_test_helpers.py` (99 lines) — dependency for GuardianCore test isolation on official restack.
- **vs B helpers:** B blob longer / evolved (ImportError-tolerant reset, ExitStack patches, optional OpenClawAdapter). **Must merge**, not overwrite blindly.

## Classification table (CWA semantics: B → C)

Legend relative to **official tip C (`d791084`)**.

| # | Semantic change (from B / CWA) | Primary files | Class | Rationale |
|---|--------------------------------|---------------|-------|-----------|
| 1 | Audit `mode=` / `GuardianBootstrapAudit` / `describe_guardian_bootstrap` | `elysia_sub_guardian.py` | **ALREADY_PRESENT** | On C via earlier restack (`9b21e00` lineage); B mostly docstring + operational activate wiring |
| 2 | `no_guardian_core` / singleton test isolation marker | tests/conftest (prior) | **ALREADY_PRESENT** | On A/C via `a7face8` |
| 3 | Audit bootstrap docs (prior restack slice) | `docs/ISSUE-23-AUDIT-BOOTSTRAP.md` (partial) | **ALREADY_PRESENT** / **DOC_ONLY** refresh | Base docs on C; B may extend — treat delta as DOC_ONLY |
| 4 | Construct-only `GuardianCore` + `_activated` + `activate()` | `project_guardian/core.py` | **PORT_WITH_ADAPTATION** | Absent on C (construct still activates via `ensure_monitoring_started`); rewrite onto C tip core — do not wholesale replace tip |
| 5 | `activate_guardian_core` / `get_existing_guardian_core` / conflict guards / construct-only `get_guardian_core` | `project_guardian/guardian_singleton.py` | **PORT_REQUIRED** | Missing on C (only get/reset/ensure) |
| 6 | Operational bootstrap uses `activate_guardian_core` (not ensure-on-init) | `elysia_sub_guardian.py` | **PORT_REQUIRED** | C operational path still `ensure_monitoring_started` |
| 7 | `elysia.py` passes `mode="operational"` | `elysia.py` | **PORT_REQUIRED** | C still `init_guardian_core(config=self.config)` → TypeError risk vs required `mode` |
| 8 | Production callers activate / construct-safe | `elysia_interface.py`, `run_elysia.py`, `start_control_panel.py`, `start_ui_panel.py` | **PORT_REQUIRED** | B deltas not on C |
| 9 | Tip autonomy: `module_activity.py` (+ core imports) | `project_guardian/module_activity.py`, `core.py` | **PORT_WITH_ADAPTATION** | New on B; required if porting B’s core import surface; adapt to C core rather than blind add if unused |
| 10 | Tip autonomy: planner readiness log helpers | `project_guardian/planner_readiness.py`, `tests/...dashboard_readiness.py` | **PORT_WITH_ADAPTATION** | Additive on B; keep if core port references `log_autonomy_*` |
| 11 | CWA unit tests | `tests/test_guardian_construct_without_activate.py` | **TEST_ONLY** / **PORT_REQUIRED** | Missing on C; port with product |
| 12 | Audit bootstrap tests | `tests/test_guardian_audit_bootstrap.py` | **TEST_ONLY** / **PORT_REQUIRED** | Missing on C |
| 13 | Test stubs (`openai` / `requests`) | `tests/_stubs/*` | **TEST_ONLY** / **PORT_REQUIRED** | Support CWA tests |
| 14 | GuardianCore test helpers | `tests/guardian_core_test_helpers.py` | **CONFLICT** / **PORT_WITH_ADAPTATION** | **Only true overlap**; C has base helpers, B has superseding adaptations — three-way merge preserving C tip + B resilience |
| 15 | CWA / constructor / port-map docs | `docs/ISSUE-23-CONSTRUCT-WITHOUT-ACTIVATE.md`, `...SIDE-EFFECT-MAP.md`, `...RESTACK-CWA-PORT-MAP.md`, audit doc delta | **DOC_ONLY** | Port after/with product; no runtime effect |
| 16 | Dynamic inspection report tip | `docs/AUTOPILOT-003-DYNAMIC-INSPECTION-RESTACK-20260911.md` @ `881608c` | **DOC_ONLY** | Not product; optional after reconcile |
| 17 | Cherry-pick / merge of old CWA lineage (`776647f`) | history | **OBSOLETE** / **FORBIDDEN** | Semantic port only; PASS does not transfer |
| 18 | OpenClawAdapter hard dependency in helpers | helper patch style | **OBSOLETE** on tip | B already optionalizes; keep that adaptation when merging helpers |

### Summary counts
- **ALREADY_PRESENT:** audit mode boundary, marker, prior audit docs base  
- **PORT_REQUIRED:** singleton activate/get_existing/conflicts; operational activate path; `elysia.py` mode; UI/run callers; CWA+audit tests+stubs  
- **PORT_WITH_ADAPTATION:** `core.py` CWA rewrite; tip autonomy companions; helper merge  
- **CONFLICT:** `tests/guardian_core_test_helpers.py` (content merge)  
- **DOC_ONLY:** CWA docs + inspection tip  
- **TEST_ONLY:** CWA/audit tests (still must land for gate)  
- **OBSOLETE:** wholesale old-lineage cherry-pick; hard OpenClaw helper assumption  

## Recommended next implementation steps (Phase 2+)

**Do not mutate** `cursor/autopilot-003-issue23-restack-cwa` or rewrite official `autopilot-003-issue23-restack`. Work only on `cursor/autopilot-003-issue23-cwa-reconciled` (from C).

1. **Merge helpers first** — three-way merge `tests/guardian_core_test_helpers.py` (A/C base + B adaptations).  
2. **Port singleton** — `project_guardian/guardian_singleton.py` (`get_existing_*`, `activate_guardian_core`, conflict checks, construct-only get).  
3. **Adapt `core.py`** — introduce `_activated` + `activate()`; remove construct-time `ensure_monitoring_started`; bring `module_activity` / planner log helpers only as needed for tip compile.  
4. **Port operational boundary** — `elysia_sub_guardian.py` operational → `activate_guardian_core`.  
5. **Fix callers** — `elysia.py` (`mode="operational"`), `elysia_interface.py`, `run_elysia.py`, `start_control_panel.py`, `start_ui_panel.py`.  
6. **Add tests + stubs** — `tests/test_guardian_construct_without_activate.py`, `tests/test_guardian_audit_bootstrap.py`, `tests/_stubs/*`.  
7. **Docs** — CWA docs from B; optionally inspection doc from `881608c`.  
8. **Verify** — CWA suite + compileall + lineage/control-plane; do not claim Vega PASS transfer; leave official restack / CWA branch untouched until explicit integration step.  
9. **PR strategy** — update/replace draft #34 head to reconciled branch when product port lands; expect conflict resolution vs current divergent head.

## Prohibitions observed this phase
- No merge to main  
- No force-push  
- No mutation of `cursor/autopilot-003-issue23-restack-cwa`  
- No rewrite of official `autopilot-003-issue23-restack`  
- No cherry-pick of product yet  

## Map artifact path
`docs/ISSUE-23-CWA-RECONCILIATION-MAP-20260911.md`  
Worktree: `C:\Users\Owner\Project guardian\.worktrees\autopilot-003-issue23-cwa-reconciled`
