# Phase 1d-B — clean dry-run observability design

**Date:** 2026-05-28  
**Current verified HEAD:** `6c2d440` — `docs(autonomy): triage dirty phase one hunks`  
**Status:** Documentation/design only. No production code changed, no autonomy enabled, no live execution run.

This design defines a clean, dry-run-only observability surface that can be implemented later from committed HEAD **without** reusing the dirty `project_guardian/core.py` decision-trace/scoring hunks or any `elysia/api/server.py` hunks.

---

## 1. Purpose

The dry-run observability surface exists to:

- Record **why** a dry-run action was proposed (proposed action + summary + source/cycle).
- Record **why** it was blocked (live-execution guard reasons, dry-run-only policy).
- Record **what would have happened** without executing it (proposed action kind only; no execution).
- Help **compare repeated dry-run cycles** later (stable `trace_id`/`cycle_id` and consistent fields) without enabling live execution.

It is observability for the existing Phase 1 dry-run path only. It does not add any new capability.

---

## 2. Explicit non-goals

This surface must **not**:

- enable or perform live execution
- execute any tool/capability
- perform any mutation
- perform any proposal implementation
- perform any WebScout/browser activity
- change scoring behavior
- change archetype selection behavior
- change legacy harvest behavior
- influence action selection in any way

It is read/record-only relative to the dry-run decision that already occurs.

---

## 3. Proposed data shape

A small, serializable decision-trace dictionary (all fields JSON-safe):

| Field | Type | Meaning |
|-------|------|---------|
| `trace_id` | str (uuid) | Unique id for this trace record |
| `timestamp` | str (ISO-8601 UTC) | When the trace was produced |
| `source` | str | Entry source (e.g. `run_autonomous_cycle`) |
| `cycle_id` | str | Dry-run cycle id (matches existing guard cycle id) |
| `proposed_action` | str | Raw proposed action string (may be empty) |
| `proposed_action_kind` | str | Coarse classification (e.g. `use_capability`, `execute_self_task`, `none`) |
| `proposed_action_summary` | str | Short, truncated human label; no payloads/secrets |
| `dry_run` | bool | Always `true` in Phase 1 |
| `executed` | bool | Always `false` in Phase 1 |
| `block_reasons` | list[str] | Guard/policy reasons (e.g. `live_execution_disabled`, `autonomy_context_denied`, `dry_run_only`) |
| `live_execution_guard` | dict | Compact guard metadata (`allowed`, `reasons`, `forced_dry_run`) |
| `capability_called` | bool | Always `false` in Phase 1 |
| `mutation_called` | bool | Always `false` in Phase 1 |
| `proposal_implementation_called` | bool | Always `false` in Phase 1 |
| `legacy_executor_reached` | bool | Always `false` in Phase 1 |
| `notes` | str | Optional free-text note; no execution side effects |

Example shape (illustrative only, not committed code):

```json
{
  "trace_id": "f1e2...",
  "timestamp": "2026-05-28T00:00:00+00:00",
  "source": "run_autonomous_cycle",
  "cycle_id": "2ef9...",
  "proposed_action": "use_capability/test",
  "proposed_action_kind": "use_capability",
  "proposed_action_summary": "uc:test",
  "dry_run": true,
  "executed": false,
  "block_reasons": ["live_execution_disabled", "autonomy_context_denied", "dry_run_only"],
  "live_execution_guard": {"allowed": false, "forced_dry_run": true, "reasons": ["..."]},
  "capability_called": false,
  "mutation_called": false,
  "proposal_implementation_called": false,
  "legacy_executor_reached": false,
  "notes": ""
}
```

---

## 4. Safety invariants

The following must hold for every Phase 1 trace:

- `executed` must always be `false`.
- `dry_run` must always be `true`.
- `capability_called` must be `false`.
- `mutation_called` must be `false`.
- `proposal_implementation_called` must be `false`.
- `legacy_executor_reached` must be `false`.
- Trace creation must have **no side effects** except optional **gitignored** local audit/report output.
- Trace must **not** influence action selection or scoring in this phase.

These invariants should be asserted directly in contract tests (see §6).

---

## 5. Proposed implementation plan (for later)

Minimal, dry-run-only, clean-HEAD based:

1. **Helper placement:** Add a small helper, preferably **not** in `core.py`. Natural home is the existing guard module `project_guardian/autonomy_dry_run_guard.py` (or a new sibling like `autonomy_dry_run_trace.py`) so `core.py` stays untouched beyond what HEAD already contains.
2. **Wiring point:** Build/emit the trace **only** inside `run_autonomous_phase1_dry_run` / `_autonomy_phase1_dry_run` (the existing dry-run wrapper). Do not wire into `_get_next_action_impl` or the scoring path (that is the quarantined dirty hunk).
3. **Reuse existing guard output:** Populate `live_execution_guard` and `block_reasons` from the guard metadata already produced by `_evaluate_autonomy_live_execution_guard` — no new guard logic.
4. **Persistence:** Reuse `append_autonomy_dry_run_audit` (gitignored `data/runtime/...`) or a sibling report writer; never write into tracked paths.
5. **Do not** touch `elysia/api/server.py`.
6. **Do not** implement approval routes.
7. **Do not** implement WebScout expansion.
8. **Do not** reuse the dirty `core.py` trace helpers wholesale; if any formatting is borrowed, it must be rewritten as dry-run-only and reviewed independently.

---

## 6. Test plan (for later)

To be run when implementation lands (all from a **clean worktree at committed HEAD**):

1. **Clean worktree smoke:** `python scripts/run_safe_stack_smoke_tests.py` → expect `408 passed, 3 warnings` (plus any new trace tests).
2. **Targeted contract tests** for the trace helper and its wiring.
3. **`dry_run_only: false` override attempt** still blocked (stub config `enabled=True`, `dry_run_only=False`) → trace still shows `dry_run=true`, `executed=false`.
4. **Monkeypatch `execute_capability_kind`** to raise `AssertionError` if called → assert it is never invoked.
5. **Assert trace fields**: `executed=false`, `dry_run=true`, `capability_called=false`, `mutation_called=false`, `proposal_implementation_called=false`.
6. **Assert legacy executor not reached** (`legacy_executor_reached=false`; static check that dry-run return precedes legacy branch).

---

## 7. Risk table

| Item | Risk | Action |
|------|------|--------|
| Dirty `core.py` decision-trace hunk (groups 1–2) | medium | **Rewrite** as dry-run-only in guard module; **do not stage** the dirty version |
| Dirty `core.py` archetype scoring hunk (group 4) | high | **Quarantine**; out of scope for observability |
| Dirty `core.py` legacy harvest tweak (group 5) | high | **Quarantine**; legacy path, defer |
| Dirty `core.py` chatlog memory gate (group 3) | low | Unrelated; handle on separate PR if ever |
| Dirty `server.py` implementation/WebScout hunks | high | **Quarantine**; do not touch server.py |
| Trace output persistence | low | **Gitignored only**; no repo contamination, no tracked writes |
| Trace influencing selection | high if violated | Forbidden; trace is record-only, asserted by tests |

---

## 8. Final recommendation

Proceed to implementation **only after this design is verified**. Implementation should be:

- **minimal** — smallest helper + single wiring point in the existing dry-run wrapper
- **dry-run-only** — no execution, no scoring/selection changes
- **clean-HEAD based** — built from committed HEAD, not from dirty `core.py`/`server.py`

No autonomy enabled, no live execution run, no real autonomy run by this design step.
