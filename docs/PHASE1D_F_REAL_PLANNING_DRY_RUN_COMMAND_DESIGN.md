# Phase 1d-F — real-planning dry-run command design

**Date:** 2026-05-30  
**Current verified HEAD:** `835c1ad` — `docs(autonomy): record safe dry-run command baseline`  
**Status:** Documentation/design only. No implementation, no autonomy enabled, no live execution.

This design explains how to move the operator dry-run command from a **deterministic in-memory stub cycle** to Elysia's **committed real dry-run planning path**, while remaining bounded and non-executing.

---

## 1. Purpose

- Use Elysia's **committed real dry-run planning path** (the Phase 1 dry-run wrapper around `GuardianCore.run_autonomous_cycle`).
- Produce `decision_trace`, `decision_trace_summary`, and `dry_run_report` from a more realistic planning pass.
- Remain **bounded** (hard-capped cycles) and **non-executing**.
- Give the operator a more realistic "what Elysia would do" report than the stub.

---

## 2. Non-goals

- No live execution.
- No real autonomy mode.
- No server startup.
- No background loop.
- No daemon.
- No API/UI routes.
- No proposal implementation.
- No WebScout/browser.
- No mutation.
- No scoring/action-selection changes.
- No `config/autonomy.json` enablement.

---

## 3. Proposed command

Two options were considered:

- **(A) Extend the existing script with an explicit flag:** `python scripts/run_elysia_dry_run_report.py --mode real-planning` (default stays `--mode stub`).
- **(B) Separate command:** `python scripts/run_elysia_real_planning_dry_run_report.py`.

**Recommendation: Option A (explicit `--mode real-planning` flag).**

Why A is safer:

- Keeps a single, well-tested entrypoint with the stub path as the **default**; the real path is strictly opt-in.
- Reuses the existing bounded helper, safety evaluator, exit-code semantics, and output formatting — less duplicated surface to audit.
- A separate script risks drift (two safety evaluators) and invites copy-paste of unsafe shortcuts.
- The flag makes the operator's intent explicit in shell history/CI logs, and the hard safety check (see §4) gates it regardless.

---

## 4. Safety model

- **Default remains stub mode.** Real-planning mode must be explicitly requested (`--mode real-planning`).
- **Max cycles hard-capped at 3** (`HARD_MAX_CYCLES`), same as stub mode.
- `config/autonomy.json` remains **enabled=false**; the command refuses real-planning mode if committed config is enabled (fail closed).
- Any in-memory config override (e.g. a stub `_load_autonomy_config` returning `enabled=True`) must be **isolated to the in-memory injected object and dry-run-only**; it must never write `config/autonomy.json`.
- Live execution guard must stay **fail-closed** (the committed Phase 1 wrapper forces dry-run; `dry_run_only:false` is ignored).
- Execution methods (`execute_capability_kind`, mutation/proposal/subprocess/browser entry points) are **monkeypatched/guarded to raise** if reached.
- **No server start**, no browser/network/subprocess.

---

## 5. Integration model

- Use the committed `GuardianCore.run_autonomous_cycle` (which returns through `run_autonomous_phase1_dry_run`) **only if it can be constructed safely without starting the server or live systems**.
- **Prefer dependency injection / stubbed dependencies** over a full app boot: build a minimal `GuardianCore` instance (e.g. via `object.__new__(GuardianCore)`) and inject just the methods the dry-run wrapper needs (`_load_autonomy_config`, `get_next_action`, `_load_mistral_decider_config`, `_autonomy_action_times`), mirroring the committed contract tests.
- **Do not** import or rely on the dirty `core.py` hunks (decision-trace/scoring/legacy edits).
- **Do not** touch `elysia/api/server.py`.
- **Do not** call WebScout or proposal-implementation paths.
- The injected `run_cycle` for `run_phase1_dry_run_batch(...)` wraps one safe real-planning dry-run call per cycle.

---

## 6. Required result invariants

Every cycle must satisfy:

- `decision_trace` present
- `decision_trace_summary` present
- `dry_run_report` present
- `executed=false`
- `dry_run=true`
- `dry_run_report.blocked=true`
- `execution_call_count=0`
- `legacy_fallback_reached=false`
- `mutation_called=false`, `proposal_implementation_called=false`, no WebScout/browser

---

## 7. Fail-closed conditions

Real-planning mode must fail closed (exit nonzero, run no cycles where possible) when:

- `GuardianCore` cannot be safely initialized for dry-run;
- `config/autonomy.json` is enabled in committed state;
- any execution method is reached (guard raises);
- any result lacks required report fields;
- any cycle `executed=true`;
- any legacy fallback reached;
- any browser/network/subprocess attempted;
- cycle count exceeds the hard cap.

---

## 8. Testing plan

- **Keep stub command tests unchanged.**
- Add real-planning command tests with execution methods **monkeypatched to raise**.
- Test that the explicit opt-in flag is required (default is still stub mode).
- Test default still produces stub-mode output.
- Test `config/autonomy.json` remains disabled (committed) during the run.
- Test a clean temp worktree command run.
- Test `--json` output is parseable.
- Test fail-closed behavior on unsafe conditions (executed, missing report, legacy reached, init failure).
- Safe-stack smoke remains passing (report exact count; new contract tests in the included file will raise the total — explain the delta).

---

## 9. Risk table

| Risk | Mitigation |
|------|------------|
| Real planning import causes side effects | Lazy import inside the command; construct via `object.__new__`; inject stubbed deps; no module-level boot |
| `GuardianCore` init starts systems unexpectedly | Avoid full `__init__`; inject only required methods; fail closed if a safe minimal instance can't be built |
| Dirty `core.py`/`server.py` contaminate behavior | Build from clean HEAD; never reuse dirty hunks; never stage those files; verify in clean worktree |
| Real-planning mode mistaken for live autonomy | Explicit `--mode real-planning` flag + docs; refuses if config enabled; reports remain dry-run-only |
| Browser/network/proposal path accidentally reached | Monkeypatch/guard those entry points to raise; assert call counts are 0 in tests |

---

## 10. Recommended first implementation

- Prefer the explicit `--mode real-planning` flag behind a **hard safety check** (refuse if config enabled; guard execution methods).
- Implementation should first add a **non-default, dry-run-only** real-planning path **with tests**, keeping stub mode as default.
- **No persistence.**
- **No server.**
- **No config change.**
- **No dirty file staging.**

---

## 11. Final warning

This design **does not authorize real autonomy or live execution.** It specifies a bounded, opt-in, dry-run-only real-planning report path to be implemented later, only after design verification.
