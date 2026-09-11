# Issue #23 CWA Integration Reconciliation — Durable Handoff (2026-09-11)

**Repo:** MsElysia/Elysia  
**Autopilot:** AUTOPILOT-003 Phase 1 — Issue #23 construct-without-activate (CWA) reconciled onto official restack tip  
**Handoff branch:** `docs/handoff-23-cwa-reconciled-20260911` (docs-only; does **not** rewrite product SHA)  
**GitHub writes this session:** `HUMAN_GOVERNANCE_REQUIRED` (`gh auth status` → not logged in)

---

## CURRENT BASE SHA

`d791084e716dfcfdaa686374276611ebc0e2a0e6`  
Branch: `autopilot-003-issue23-restack` (`origin` matches)  
Message: `restack(#23): add missing GuardianCore test helper dependency`

## SOURCE VERIFIED CWA SHA

`7374820642fad52a6264c86df8632c3a630df592`  
Branch lineage: `cursor/autopilot-003-issue23-restack-cwa` (product B; docs tip `881608c` is inspection-only)  
Predecessor draft PR: **#34** (leave open as lineage evidence; do **not** close; do **not** mutate head branch)  
**Prior PASS does NOT transfer** to the reconciled product.

## COMMON ANCESTOR

`4ff2dc92dd7d9bc393225bce35de9239a9cad6a5`  
`merge-base(7374820, d791084) = 4ff2dc9`  
B and C were siblings under A; reconcile is a semantic port onto C, not a history merge of B.

```
* 0a2d135  PRODUCT — reconcile CWA onto d791084
| * 3c3ead5  docs tip (inspection / residuals) — NOT product
|/
* d791084  BASE — official restack tip
| * 7374820  SOURCE CWA (PASS does not transfer)
|/
* 4ff2dc9  COMMON ANCESTOR
```

## THREE-WAY SEMANTIC MAP

Authoritative map: `docs/ISSUE-23-CWA-RECONCILIATION-MAP-20260911.md` on product/docs tip.

| Class | What |
|-------|------|
| **ALREADY_PRESENT** | Audit `mode=` / bootstrap descriptor; `no_guardian_core` isolation; prior audit docs base |
| **PORT_REQUIRED** | `activate_guardian_core` / `get_existing_guardian_core` / conflict guards; operational bootstrap activate path; `elysia.py` `mode="operational"`; production callers (`elysia_interface`, `run_elysia`, `start_*`); CWA + audit tests + stubs |
| **PORT_WITH_ADAPTATION** | `GuardianCore` construct/`_activated`/`activate()`; tip autonomy companions (`module_activity`, planner readiness logs); helper merge |
| **CONFLICT** | `tests/guardian_core_test_helpers.py` only overlapping file (A…B ∩ A…C) |
| **DOC_ONLY** | CWA docs + inspection reports |
| **OBSOLETE / FORBIDDEN** | Cherry-pick of old CWA lineage; claiming transferred PASS |

## TARGET-ONLY CHANGES PRESERVED

Official restack tip intent from `d791084` preserved as **parent of product**:

- `tests/guardian_core_test_helpers.py` presence / GuardianCore test-helper dependency on restack tip
- Helper merge kept C’s “helpers exist” contract while adopting B’s CWA-aware adaptations (ImportError-tolerant reset, ExitStack patches, optional OpenClawAdapter)
- No rewrite of `autopilot-003-issue23-restack`; no mutation of `cursor/autopilot-003-issue23-restack-cwa`

## CWA CHANGES PORTED

Semantic port from `7374820` onto `d791084`:

- Construct-only `GuardianCore` + `_activated` + explicit `activate()`
- Singleton: `activate_guardian_core`, `get_existing_guardian_core`, construct-only `get_guardian_core`, conflict guards
- Operational path uses `activate_guardian_core` (not ensure-on-init)
- Callers: `elysia.py`, `elysia_interface.py`, `run_elysia.py`, `start_control_panel.py`, `start_ui_panel.py`
- Tip autonomy companions required by ported `core.py` import surface
- CWA + audit bootstrap tests and `_stubs`
- CWA / constructor / port-map docs + reconciliation map

## CONFLICTS RESOLVED

| File | Resolution |
|------|------------|
| `tests/guardian_core_test_helpers.py` | Three-way semantic merge: preserve restack helper-add intent from C; keep B’s CWA-aware resilience (optional OpenClaw, ExitStack, tolerant reset). Product commit message: *Preserve official helper-add intent via CWA-aware helpers from 7374820; prior PASS does not transfer.* |

No other content conflicts. History cherry-pick of B onto C was **not** used.

## FILES CHANGED

Product delta `d791084…0a2d135` (21 files, +1536 / −119):

```
docs/ISSUE-23-AUDIT-BOOTSTRAP.md
docs/ISSUE-23-CONSTRUCT-WITHOUT-ACTIVATE.md
docs/ISSUE-23-CONSTRUCTOR-SIDE-EFFECT-MAP.md
docs/ISSUE-23-CWA-RECONCILIATION-MAP-20260911.md
docs/ISSUE-23-RESTACK-CWA-PORT-MAP.md
elysia.py
elysia_interface.py
elysia_sub_guardian.py
project_guardian/core.py
project_guardian/guardian_singleton.py
project_guardian/module_activity.py
project_guardian/planner_readiness.py
project_guardian/tests/test_dashboard_readiness.py
run_elysia.py
start_control_panel.py
start_ui_panel.py
tests/_stubs/openai.py
tests/_stubs/requests.py
tests/guardian_core_test_helpers.py
tests/test_guardian_audit_bootstrap.py
tests/test_guardian_construct_without_activate.py
```

Docs tip above product (not product): `d0e1905` → `fd53e2d` → `3c3ead5` (dynamic inspection + residual probes / lineage counts).

## TESTS

| Suite | Result |
|-------|--------|
| `tests/test_guardian_construct_without_activate.py` + `tests/test_guardian_audit_bootstrap.py` | **20/20 passed** |
| `compileall` on CWA surfaces | exit 0 |

## CONTROL-PLANE REGRESSION TESTS

Exact historical RECONCILE-22 union (evidence binding, soft-risk adversarial, verifier, lifecycle, seed control-plane): **147 passed**.

(Early map note of 113 + 4 approver smoke fails was superseded by fresh inspection lineage union on product `0a2d135`.)

## DYNAMIC INSPECTION

Report: `docs/AUTOPILOT-003-DYNAMIC-INSPECTION-RECONCILED-20260911.md` on docs tip `3c3ead5` (product under inspection = `0a2d135`).

| Check | Result |
|-------|--------|
| Primary double cycle construct/get/inspect | Both cycles `_activated=False`, `_running=False`; monitors/loop/UI not started |
| Traps (socket / subprocess / Thread.start / provider / planner probe) | **0 hits** both cycles |
| Teardown | singleton cleared; monitoring flags false |

## EAI RESULT

EAI enabled + GuardianLayer off construct probe: **inert** — `_activated=False`, `_running=False`, `thread_starts=0`; `EAISafetyFramework` constructed only (LIVE_SUPPORTING, not operational activation).

## GUARDIANLAYER RESIDUAL

`enable_guardian_layer=True` construct probe: **TIMEOUT** / hang (UNCHANGED_BOUNDED_RESIDUAL). Tip CWA harnesses keep layer disabled. **Not** proven activate leak; **not blocking** for construct gate.

## LEGACY ACTIVATION API RESIDUAL

Public `ensure_monitoring_started` remains callable after construct and can start monitors while `_activated` stays **False** (UNCHANGED_BOUNDED_RESIDUAL; identical class vs source CWA `7374820`). Construct path no longer calls it; authorized start is `activate()` / `activate_guardian_core`.

Additional non-blocking residuals: stale `docs/boot_memory_map.md` (still claims construct-time ensure); Phase B deferred ops deferred by design.

## EXACT NEW PRODUCT SHA

`0a2d135990e8acd3b2a5bbf7539f082ec448de73`  
Branch: `cursor/autopilot-003-issue23-cwa-reconciled`  
Message: `reconcile(#23): port construct-without-activate onto restack tip d791084`  
Docs tip (not product): `3c3ead559ef42171832b31c5a7c4776b596b466e` — already on `origin` (contains product as ancestor; no product rewrite this handoff).

## VEGA VERDICT

**PASS** — confidence **0.88**  
Artifact: `docs/VEGA-ISSUE-23-CWA-RECONCILED-20260911.md`  
Branch: `codex/vega-reverify-23-cwa-reconciled` @ `46e33dac8c3d6b44051bf3491f633fe704052d15`  
Target verified: product `0a2d135` (not docs tip). Source PASS at `7374820` explicitly **not** transferred.

## ARCHITECTURE VERDICT

**READY_FOR_INTEGRATION_REVIEW** — confidence **0.87**  
Artifact: `docs/ARCHITECTURE-REVIEW-ISSUE-23-CWA-RECONCILED-20260911.md`  
Branch: `codex/arch-review-23-cwa-reconciled` @ `d0a03585ea827cea3317b859f65b389f5237ba4e`

## PR

**Intended NEW draft PR** (not an update of #34):

| Field | Value |
|-------|--------|
| Base | `autopilot-003-issue23-restack` (`d791084`) |
| Head | `cursor/autopilot-003-issue23-cwa-reconciled` (product `0a2d135`; tip may show docs `3c3ead5`) |
| Title | `draft: #23 CWA reconciled onto restack tip d791084` |
| Status this session | **NOT OPENED** — `HUMAN_GOVERNANCE_REQUIRED` (no `gh` auth) |

Pasteable body + `gh pr create` command: `docs/DRAFT-PR-ISSUE-23-CWA-RECONCILED-BODY-20260911.md` and `docs/GH-COMMANDS-ISSUE-23-CWA-RECONCILED-HANDOFF-20260911.md` on this handoff branch.

Predecessor **PR #34** remains open as lineage evidence at source CWA `7374820` / head `cursor/autopilot-003-issue23-restack-cwa`. Do **not** close; do **not** mutate its head branch.

## PR #25 STATUS NOT_INHERITED

**NOT_INHERITED.** This reconcile does not claim PR #25 / claim-boundary landed. Map, Vega, and architecture review all mark #25 not inherited unless present and retested on tip.

## ISSUE #23 STATUS

`IMPLEMENTATION_COMPLETE_ON_CURRENT_RESTACK_PENDING_HUMAN_INTEGRATION`

Do **not** close Issue #23. Pasteable status comments for #11 and #23 are on this handoff branch (`docs/ISSUE-11-CHECKPOINT-COMMENT-23-CWA-RECONCILED-20260911.md`, `docs/ISSUE-23-STATUS-COMMENT-CWA-RECONCILED-20260911.md`). Comment posting this session: **blocked** (`HUMAN_GOVERNANCE_REQUIRED`).

## NEXT SMALLEST TASK

1. Human: `gh auth login` (or equivalent), then run commands in `docs/GH-COMMANDS-ISSUE-23-CWA-RECONCILED-HANDOFF-20260911.md` to open the **new** draft PR and post Issue #11 / #23 comments.  
2. Human integration review of draft PR (base restack ↔ reconciled head).  
3. Follow-ups (non-blocking for this gate): gate/deprecate public `ensure_monitoring_started`; refresh `docs/boot_memory_map.md`; GuardianLayer hang investigation when enabled; Phase B remains deferred.  
4. Leave PR #34 open; do not merge to main / force-push shared history / rewrite official restack / mutate `cursor/autopilot-003-issue23-restack-cwa` / close #23 without human decision.

## Prohibitions observed this handoff

- No merge to main  
- No force-push of shared history  
- No mutation of `cursor/autopilot-003-issue23-restack-cwa`  
- No rewrite of official `autopilot-003-issue23-restack`  
- No close of PR #34 or Issue #23  
- No product SHA rewrite (handoff lives on docs branch only)
