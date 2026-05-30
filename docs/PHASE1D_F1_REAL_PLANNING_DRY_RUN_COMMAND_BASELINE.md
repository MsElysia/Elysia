# Phase 1d-F.1 — real-planning dry-run command baseline

**Date:** 2026-05-30  
**Milestone:** Phase 1d-F.1 real-planning dry-run command mode  
**Implementation commits:**

- `726367e` — `feat(autonomy): add real-planning dry-run command mode`
- `38caa99` — `fix(autonomy): suppress dry-run command audit writes by default`

This baseline records the real-planning dry-run command mode after audit-write suppression. It does **not** authorize real autonomy or live execution.

---

## Changed files (across implementation + fix)

- `scripts/run_elysia_dry_run_report.py`
- `project_guardian/tests/test_dry_run_autonomy_phase1_contract.py`

No `project_guardian/core.py` or `elysia/api/server.py` hunks were staged. No config changes.

---

## Commands

```
python scripts/run_elysia_dry_run_report.py
python scripts/run_elysia_dry_run_report.py --json
python scripts/run_elysia_dry_run_report.py --mode real-planning
python scripts/run_elysia_dry_run_report.py --mode real-planning --json
```

---

## Behavior

- default mode is `stub`
- real-planning mode is explicit opt-in (`--mode real-planning`)
- hard cap remains `3` (`HARD_MAX_CYCLES`)
- uses `run_phase1_dry_run_batch(...)`
- real-planning drives the committed `GuardianCore.run_autonomous_cycle` via minimal safe construction (`object.__new__`) + injected dry-run-only stubs
- no full app/server boot
- no live execution
- no tools/capabilities/mutation/proposal implementation/WebScout/browser activity
- no file writing by default
- `--write-audit` is explicit opt-in only

---

## Verified command matrix

| Command | Result |
|---------|--------|
| stub text | exit 0, SAFE |
| stub json | exit 0, parseable, `safe=true` |
| real-planning text | exit 0, SAFE |
| real-planning json | exit 0, parseable, `safe=true` |

Real-planning details: `completed_cycles=3`, `any_executed=false`, `execution_call_count=0`, `legacy_fallback_reached=false`.

---

## Audit-write suppression

- **Root cause:** real-planning routes through the committed dry-run path, which calls `append_autonomy_dry_run_audit(...)` and appends to `data/runtime/autonomy_dry_run_audit.jsonl` per cycle.
- **Fix:** the command patches `append_autonomy_dry_run_audit` to an in-memory no-op by default for command runs (no change to global audit semantics). Opt-in `--write-audit` re-enables the append.
- **Verification:** audit line count stayed unchanged (233 → 233) across all four default command runs.

---

## Verified gates

| Gate | Result |
|------|--------|
| Targeted dry-run contract tests | **64 passed, 3 warnings** |
| Safe-stack smoke | **450 passed, 3 warnings** |
| Full collection (Cursor) | **441 tests collected** |
| Full collection (Codex) | **400 tests collected** (clean temp worktree) |

**Collection count mismatch** (441 vs 400) remains documented as environment/path/discovery-dependent unless separately investigated (see `docs/PHASE1C2_COLLECTION_REPAIR_BASELINE.md`). The safe-stack smoke count rose 446 → 450 because four new audit-suppression contract tests were added to the already-included Phase 1 contract file.

---

## Safety statements

- **No real autonomy run.**
- **No live execution run.**
- **No tools/capabilities/mutation/proposal implementation/WebScout/browser activity.**
- **No scoring/action-selection/archetype/legacy-harvest/server-route changes.**
- `project_guardian/core.py` and `elysia/api/server.py` remained dirty/unstaged.
- `config/autonomy.json`: **enabled=false** (unchanged).
- Phase 1 autonomy remains dry-run only; `dry_run_only:false` remains ignored/blocked.

---

## Explicit note

This is **real-planning dry-run only**, not real autonomy. It drives the committed dry-run planning path with injected, isolated, dry-run-only stubs and reports what Elysia would propose — without executing anything.

## Explicit warning

This command and baseline **do not authorize live execution.**

---

## Final verdict

**PASS** for the real-planning dry-run command baseline.
