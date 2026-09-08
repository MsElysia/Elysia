# ELY-TASK-000015 completion / handoff

## Task
Define the disabled GitHub synchronization planning contract before any live GitHub adapter implementation.

## Worker
ChatGPT-side supervisor; governance/design role.

## Branch
`autopilot-004-github-sync-contract`, isolated from AUTOPILOT-004 verified development head `ef4f419e2ea71b3d75f21ee93963caf3ac7fce39`.

## Files read
- `AGENTS.md`
- `elysia_collective_seed/autopilot/task_packet_schema.json`
- `elysia_collective_seed/autopilot/completion_packet_schema.json`
- AUTOPILOT-004 issue/handoff history
- current draft PR metadata

## Files changed
- Added `elysia_collective_seed/autopilot/github_sync_contract.md`
- Added this handoff record.

## Checks / evidence
- Contract is specification-only and contains no executable network/provider/runtime code.
- Contract explicitly requires a pure planner and default no-op executor.
- Contract forbids merge/auto-merge/PR-close/branch-delete/release/deployment/secret/admin proposals.
- Contract defines deterministic idempotency, duplicate prevention, stale-state refusal, redaction, independent-verification semantics, and human-gate inheritance.
- Contract enumerates required static tests before implementation acceptance.
- First contract commit: `2fb8458dffa2c7320919ce9392ba8ddb7aaa57e5`.

## Claims
1. This step narrows and documents the GitHub synchronization boundary without enabling external-write authority.
2. The next implementation can be tested entirely as pure/static behavior before any real GitHub executor exists.

## Uncertainties / risks
- The pure planner and no-op executor are not implemented yet.
- Required static tests are not yet executable evidence.
- No live GitHub executor is authorized by this task.

## Next recommended task
On this isolated lineage, implement the smallest pure `plan_sync(...)` + `NoOpSyncExecutor` surface and static tests covering all eight cases in the contract. Then obtain independent review/CI before incorporating it into PR #12. Do not add a real GitHub writer.

## Safety disposition
No merge to seed/main, deployment, provider invocation, Guardian runtime wiring, external posting, credential/private-chatlog access, or authority expansion performed.
