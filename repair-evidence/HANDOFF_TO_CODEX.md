# Autonomy execute-cycle gate repair — handoff to Codex

Date: 2026-10-25. No merge, push, deploy, desktop-launcher change, protected-gate edit, listener launch, or real autonomy cycle.

## Candidate

| Item | Value |
|------|--------|
| Baseline SHA | `6c819ba80b0a6db626992a92d3ac96644e800005` |
| Repair branch | `cursor/autonomy-execute-cycle-contained-gate-001` |
| Repair worktree | `C:\Users\Owner\ely-autonomy-execute-cycle-repair` |
| Codex source WT (untouched) | `C:\Users\Owner\ely-windows-browser-accept-contained` @ `6c819ba` |
| Primary install | untouched @ `0760798bc3ecb036c92fca456670c67e901c7ed7` |

## Defect → repair

Unauthenticated `POST /api/autonomy/execute-cycle` returned 200 and reached `run_autonomous_cycle` while `autonomy_config.enabled=False`.

**Repair:** `_deny_autonomy_execute_cycle_if_blocked()` runs before any cycle call:
1. Deny (403) when autonomy `enabled is not True`, or state missing/invalid/unavailable.
2. On loopback (restricted auth available), require `X-Elysia-Identity` / `X-Elysia-Token` dashboard-operator (401). Auth does **not** override disabled autonomy.
3. `enabled=True` only passes the entry gate; `run_autonomous_cycle` retains approval/policy checks.

Dashboard JS for execute-cycle now sends `restrictedHeaders()` when tokens are present (same mechanism as restricted fact routes).

## Adjacent routes inspected (narrow scope)

| Route | Calls `run_autonomous_cycle`? | Action |
|-------|-------------------------------|--------|
| `POST /api/autonomy/execute-cycle` | Yes | **Gated** |
| `GET /api/next-action` | No (`get_next_action` only) | Identified; not gated (informational) |
| `POST /api/control/dream-cycle` | No (dreams module) | Remaining gap — unauthenticated cycle-like control |
| `POST /api/autonomy` (set enabled) | No (writes config) | Remaining gap — can flip enabled without auth |

## Evidence

| Check | Result |
|-------|--------|
| Baseline red | 7 failed / 1 passed — `repair-evidence/logs/baseline-red.log` |
| Repaired green | 8 passed — `repair-evidence/logs/repaired-green.log` |
| Security probe (disabled + intercept) | status 403, calls 0 — `repair-evidence/logs/extended-containment-security-repaired.json` |
| Contained startup | 4/4 passed |
| Status / restricted panel | 7/7 passed (incl. status_timestamp) |
| Dashboard idempotent + readiness | passed |
| `test_dashboard_listening` | 4 failed — **pre-existing env** (host port 5000 occupied; `_dashboard_started` cascade). Same failure on Codex baseline WT. Not introduced by this repair. |

## Remaining security gaps (do not claim dashboard secure)

- Unauthenticated `POST /api/autonomy` can enable autonomy.
- Unauthenticated `POST /api/control/dream-cycle`, learning start, and other legacy control routes.
- Unauthenticated `GET /api/next-action` still exposes planning output.
- Non-loopback panels skip operator auth (by design of restricted routes); autonomy-disabled gate still applies.
- This repair alone does **not** make the entire dashboard secure.

## Codex next steps

Independent security verification of this candidate, then continue browser acceptance: save → retrieve → correct → history → shutdown → restart → recall on the contained entry (`scripts/start_contained_browser_memory.py`). Do not retarget the desktop launcher.
