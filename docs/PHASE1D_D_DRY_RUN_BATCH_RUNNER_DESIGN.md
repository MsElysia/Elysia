# Phase 1d-D — bounded dry-run batch runner design

**Date:** 2026-05-29  
**Current verified HEAD:** `c68831e` — `docs(autonomy): record repeated dry-run trial`  
**Status:** Documentation/design only. No implementation, no autonomy enabled, no live execution.

This design specifies a bounded dry-run batch runner that repeats the existing Phase 1 dry-run cycle a small, hard-capped number of times and collects observation artifacts. It builds on the verified dry-run observation stack (`decision_trace`, `decision_trace_summary`, `dry_run_report`) and the repeated dry-run trial (Phase 1d-C).

---

## 1. Purpose

- Run **N bounded** dry-run cycles (hard-capped).
- Collect `decision_trace`, `decision_trace_summary`, and `dry_run_report` for each cycle.
- Produce a single **batch summary** aggregating per-cycle evidence.
- **Never** execute tools/capabilities/mutation/proposal implementation/WebScout/browser.
- Provide **repeatable evidence** before any future autonomy expansion is considered.

---

## 2. Non-goals

- No live execution.
- No real autonomy mode.
- No scheduler daemon.
- No background service.
- No server/API routes.
- No UI approval route.
- No proposal implementation.
- No WebScout/browser.
- No mutation.
- No scoring/action-selection changes.

---

## 3. Proposed interface

Helper (preferred home: `project_guardian/autonomy_dry_run_guard.py` or a sibling helper module):

```python
def run_phase1_dry_run_batch(max_cycles: int = 3, *, persist: bool = False) -> dict:
    ...
```

- **Hard max cycle limit:** suggested maximum **3** (absolute ceiling **5**). Requests above the ceiling fail closed (see §6).
- **Default `persist=False`.** When `persist=True` (a later option), output is written **only** to a gitignored runtime path (e.g. `data/runtime/...`); never to tracked files.
- Returns a **serializable** batch result (see §4).
- No background loop, no retry loop, no network/browser/subprocess.

---

## 4. Proposed batch result shape

| Field | Meaning |
|-------|---------|
| `batch_id` | Unique id for this batch run |
| `started_at` | ISO-8601 UTC start time |
| `completed_at` | ISO-8601 UTC completion time |
| `requested_cycles` | Cycles requested by caller |
| `completed_cycles` | Cycles actually run |
| `all_dry_run` | True iff every cycle had `dry_run=true` |
| `any_executed` | True iff any cycle had `executed=true` (must be false) |
| `execution_call_count` | Total guarded execution attempts observed (must be 0) |
| `legacy_fallback_reached` | True iff any cycle reached the legacy executor (must be false) |
| `reports` | List of per-cycle `dry_run_report` objects |
| `summary` | Aggregated rollup (counts, all-clear flags) |
| `warnings` | List of any non-fatal anomalies detected |

---

## 5. Per-cycle result requirements

Each cycle in `reports` must satisfy:

- `decision_trace` present
- `decision_trace_summary` present
- `dry_run_report` present
- `executed=false`
- `dry_run=true`
- `dry_run_report.blocked=true`
- capability/tool call count `= 0`
- `mutation_called=false`, `proposal_implementation_called=false`, no WebScout/browser
- `legacy_executor_reached=false`

---

## 6. Safety invariants (fail closed)

The runner must **fail closed** (raise or return an explicit error result without running cycles) if:

- requested cycles exceed the hard max;
- any execution flag is true (`any_executed`, `capability_called`, `mutation_called`, `proposal_implementation_called`);
- any required report (`decision_trace` / `decision_trace_summary` / `dry_run_report`) is missing on a cycle;
- legacy executor fallback is reached;
- `config/autonomy.json` is `enabled` in the committed config (the runner is for dry-run evidence; it must not be used to mask an enabled config).

Additional invariants:

- no background loop;
- no retry loop;
- no network/browser/subprocess.

---

## 7. Testing plan (for later)

- Targeted contract tests for **0, 1, 3, and over-limit** cycle requests.
- Monkeypatch execution methods (`execute_capability_kind`, mutation/proposal/subprocess/browser entry points) to **raise if called**.
- Assert the batch result is **JSON-serializable**.
- Assert **no** mutation/proposal/WebScout/browser calls occur.
- Assert per-cycle invariants (§5) and fail-closed behavior (§6).
- Safe-stack smoke remains passing (report exact count; new contract tests in the included file will raise the smoke total — explain the delta).
- Clean worktree repeated trial (as in Phase 1d-C).

---

## 8. Risk table

| Risk | Mitigation |
|------|------------|
| Loop accidentally becomes unbounded | Hard max constant + fail-closed over-limit check; no `while True`; explicit `for` over a capped range |
| Batch runner mistaken for real autonomy | Name/docs make "dry-run batch" explicit; refuses to run if config enabled; returns evidence only |
| Persistence leaks runtime artifacts into repo | `persist=False` default; when enabled, gitignored runtime path only; tests assert no tracked writes |
| Future server route tries to expose runner | Explicitly out of scope; no routes; design forbids API/UI exposure in Phase 1 |
| Dirty `core.py`/`server.py` hunks contaminate implementation | Implement in guard/helper module from clean HEAD; never reuse dirty hunks; never stage those files |

---

## 9. Recommended implementation scope (for later)

- Helper in the dry-run guard module or a dedicated helper module **only**.
- **No** `core.py` edits unless absolutely necessary.
- **No** `server.py`.
- **No** config change.
- **No** daemon/background task.
- **No** persistence initially (`persist=False`; persistence is a later, gitignored-only option).

---

## 10. Final recommendation

Implement **only after this design is verified**. Keep the first implementation:

- helper-only (no core/server/config/daemon),
- non-persistent,
- hard-capped and fail-closed,
- clean-HEAD based.

This design step does not enable autonomy, does not run live execution, and does not authorize either.
