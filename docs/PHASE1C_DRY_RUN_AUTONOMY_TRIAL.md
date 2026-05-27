# Phase 1c dry-run autonomy trial

## Scope

This document records the Phase 1c verification-only dry-run autonomy trial.

- Milestone: Phase 1c dry-run autonomy trial
- Verified HEAD: `f9f4785` (`fix(safe-stack): add brain memory ranking shim for clean smoke`)
- Trial mode: bounded dry-run only
- Warning: this verification does **not** authorize real autonomy or live execution

## Clean worktree verification

- Clean committed HEAD was used for the trial
- Safe-stack smoke result from clean worktree: `408 passed, 3 warnings`
- Dry-run trial path: `GuardianCore.run_autonomous_cycle(stub)`
- Stub settings used for worst-case override attempt:
  - `enabled=True`
  - `dry_run_only=False`
- Committed config state remained:
  - `config/autonomy.json` -> `enabled=false`

## Result evidence

- `executed=false`
- `dry_run=true`
- `reason=dry_run_only`
- `live_execution_guard.allowed=false`
- `forced_dry_run=true`
- `execute_capability_kind calls=0`

## Blocked paths confirmed

The trial confirmed these paths were blocked or not reached:

- live execution
- tool/capability execution
- mutation
- proposal implementation
- WebScout/browser activity
- legacy executor fallback

## Runtime artifact note

- A dry-run audit line was created only inside the temporary clean worktree runtime area
- The audit file is gitignored runtime output
- Temporary worktree was removed after verification

## Dirty worktree preservation note

The original dirty worktree was preserved during verification:

- `project_guardian/core.py` remained dirty and unstaged
- `elysia/api/server.py` remained dirty and unstaged
- No clean/reset/stash/discard operations were performed on those files

## Verifier result

- Codex verifier result: `PASS`
- Final verdict: `PASS` for clean-HEAD dry-run autonomy trial

## Explicit safety warning

This Phase 1c verification record confirms dry-run guard behavior only. It does not authorize enabling autonomy, enabling live execution, or running real autonomy mode.
