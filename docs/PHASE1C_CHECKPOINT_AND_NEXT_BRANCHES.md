# Phase 1c checkpoint and next branches

## Current verified HEAD

- `0a3fe66` — `docs(safe-stack): record collection repair baseline`

## Verified milestone chain

- Phase 1b.2 clean-checkout smoke repair: PASS
- Phase 1c dry-run autonomy trial: PASS
- Phase 1c.1 trial documentation: PASS
- Phase 1c.2 full pytest collection repair: PASS
- Phase 1c.3 collection baseline documentation: PASS

## Current gates

- Safe-stack smoke: `408 passed, 3 warnings`
- Full pytest collection: succeeds
- Full runtime pytest: not passing; baseline documented (`98 failed, 274 passed, 9 skipped, 60 errors in 116.37s`)
- Autonomy config: `config/autonomy.json` remains `enabled=false`
- Dry-run autonomy: verified
- Live execution: not enabled and not run

## Dirty worktree risks

- `project_guardian/core.py` remains dirty and unstaged
- `elysia/api/server.py` remains dirty and unstaged
- Broader dirty worktree may contain unrelated files
- Do not use `git add -A`
- Do not stage risky hunks casually

## Explicit safety boundary

This checkpoint does **not** authorize:

- real autonomy
- live tool execution
- mutation execution
- proposal implementation
- WebScout/browser execution

## Recommended next branches

### Branch A — dirty hunk triage

- Inspect, quarantine, and split `project_guardian/core.py` dirty decision-trace/scoring/chatlog hunks
- Inspect, quarantine, and split `elysia/api/server.py` proposal/WebScout hunks
- Do not mix this with autonomy execution work

### Branch B — dry-run observability

- Add better dry-run audit/report surfaces only
- No live execution
- No config enablement

### Branch C — full runtime pytest debt

- Classify current 98 failures and 60 errors
- Separate safe failures from risky mutation/WebScout/subprocess suites

### Branch D — controlled Phase 1d design

- Design-only plan for repeated dry-run cycles
- No execution yet

## Recommended next step

Prefer Branch A or Branch B before any repeated dry-run cycle.
