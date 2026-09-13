# Autopilot Task State Machine

**Status:** design-only, runtime disabled.

This state machine prevents workers from treating prose, chat context, or a successful code edit as equivalent to accepted project state.

## States

`DISCOVERED -> SPECIFIED -> READY -> CLAIMED -> EXECUTING -> SUBMITTED -> VERIFYING -> VERIFIED -> INTEGRATION_QUEUE -> COMPLETE`

Exceptional states: `BLOCKED`, `RETRYABLE_FAILURE`, `FAILED`, `HUMAN_REVIEW`, `CANCELLED`.

## Transition requirements

| From | To | Required evidence |
|---|---|---|
| DISCOVERED | SPECIFIED | bounded objective, acceptance criteria, source/provenance |
| SPECIFIED | READY | dependencies resolved; authority/risk check passed |
| READY | CLAIMED | worker capability match; lease ID; expiry |
| CLAIMED | EXECUTING | isolated branch/worktree/sandbox identified for writes |
| EXECUTING | SUBMITTED | completion packet; changed-file/evidence references; tests attempted |
| SUBMITTED | VERIFYING | independent verifier selected where required |
| VERIFYING | VERIFIED | acceptance criteria independently checked; required tests pass |
| VERIFIED | INTEGRATION_QUEUE | integration policy permits queueing; no unresolved severe finding |
| INTEGRATION_QUEUE | COMPLETE | integration evidence recorded, or task was non-integrating by design |

## Block/failure transitions

Any active state may enter `BLOCKED` when a required dependency/source/tool is unavailable. A blocker record must state what is missing and what evidence would unblock it.

Execution/verification may enter `RETRYABLE_FAILURE` when the objective remains valid and a bounded retry is justified. Retry counters are persistent. Exhausted retries become `FAILED` or are decomposed into smaller tasks.

Any state enters `HUMAN_REVIEW` when the next action would expand authority, alter constitutional governance, delete unique history, expand private-data scope, deploy, merge across an active protected gate, or cannot be resolved from machine-visible evidence.

## Lease rules

A claim is a lease, not ownership. It contains `task_id`, `worker_id`, `lease_id`, `claimed_at`, and `expires_at`. Expired leases return to `READY` unless evidence shows an active worker should be renewed. This prevents abandoned agent sessions from permanently trapping work.

## Verification rules

Runtime-affecting writes cannot transition directly from `SUBMITTED` to `VERIFIED` based solely on the producing worker's report. Verification should use a different worker/model/provider when practical plus deterministic tests/static checks where available.

## Follow-up generation

Completion packets may propose follow-up tasks. The orchestrator deduplicates them against open/completed work, checks objective ancestry, dependencies and risk, then either creates `DISCOVERED` tasks or routes them to `HUMAN_REVIEW`. A worker cannot enlarge its own permission scope through a follow-up.

## Audit invariant

Every transition must append an immutable-style event containing timestamp, prior state, next state, actor/worker, reason, evidence references, and relevant task/completion packet IDs. Current state is a projection of the event log, not the only record.
