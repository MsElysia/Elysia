# Privileged-control gate — close A–D (handoff to Codex)

Date: 2026-10-25. No merge, push, deploy, launcher change, protected-gate edit, listener, or real autonomy/learning/provider run.

## Candidate

| Item | Value |
|------|--------|
| Base SHA | `38246975afe316d79b7a1f318f9eea34a42244d9` |
| Branch | `cursor/privileged-control-gate-001` |
| Worktree | `C:\Users\Owner\ely-privileged-control-gate-repair` |
| Codex verify WT (untouched) | `C:\Users\Owner\ely-verify-autonomy-gate-3824697` @ `3824697` |

## Repair summary

Shared `_deny_privileged_control_if_blocked(kind=...)`:

| kind | Auth (any bind) | Enabled-state | Contained |
|------|-----------------|---------------|-----------|
| `configure` (`POST /api/autonomy`) | required first; no write on deny | **not** required (may enable when currently disabled) | `contained_startup` → 403 `contained_immutable`, no write |
| `execute` / `dream` / `learning` | required after enabled check | autonomy `enabled is True` | disabled → 403; auth cannot override |

UI: toggle autonomy, dream-cycle, learning/start, execute-cycle send existing `restrictedHeaders()` when tokens are present (loopback inject only; tokens not logged).

## Evidence

| Check | Result |
|-------|--------|
| Baseline red (A–D tests @ 3824697) | 9 failed / 5 passed — `logs/baseline-red.log` |
| Repaired green | 14 + 8 = 22 passed — `logs/repaired-green.log` |
| Contained + status/restricted + gates | **33 passed** — `logs/containment-status-restricted-gate.log` |
| `test_dashboard_listening` | **not run as success criteria**; known 4-fail isolation/`_find_available_port` debt on baseline and prior candidates (ports free). Do not waive. |

## Remaining gaps

- Other legacy control routes (pause/resume, speak, tasks, research, learning settings/link, etc.) may still lack this gate.
- Non-loopback HTML does not embed operator tokens (fail-closed for stock UI on public bind).
- Listening-test isolation / port-fallback product debt remains.
- Do **not** claim overall dashboard security or desktop-launcher readiness from this repair alone.

## Codex next

Independent re-verify sequences A–D + contained immutable configure; if pass, continue contained browser save → retrieve → correct → history → shutdown → restart → recall.
