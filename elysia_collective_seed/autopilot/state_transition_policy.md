# Autopilot State Transition Policy

This policy makes task movement deterministic enough for multiple disposable workers to share one durable ledger without relying on conversational memory.

## Invariants

1. A task has exactly one authoritative status in the ledger.
2. A task may have at most one active execution lease.
3. A lease never grants more authority than the task packet already grants.
4. Expired leases may be reclaimed; their prior attempt remains in the event log.
5. A worker may submit a completion packet, but may not mark its own runtime-changing write task `completed` when independent verification is required.
6. Verification must be performed by a worker outside the producer's `independence_group` when a suitable worker is available.
7. Every state transition appends an immutable event. Current state can be reconstructed from events.
8. Human/governance gates cannot be bypassed by retries, task splitting, follow-up generation, or worker substitution.
9. A follow-up task inherits the parent's authority ceiling unless an explicit gate raises it.
10. No task can transition to `completed` while a required check is failed, not run without justification, or a required review is unresolved.

## Normal transitions

```text
queued -> claimed -> running -> review -> completed
                    |       |        |
                    |       |        +-> running   (repair)
                    |       +----------> blocked
                    +------------------> blocked

blocked -> queued       (blocker resolved)
claimed -> queued       (lease expired/released)
running -> queued       (retryable worker failure)
review  -> rejected     (verified unacceptable/non-repairable result)
completed -> archived   (task record retention lifecycle only)
```

Transitions not shown above are invalid unless a versioned migration explicitly permits them.

## Claim / lease protocol

The local SQLite ledger enforces execution eligibility itself. Its trusted
constructor `execution_workers` registry must explicitly authorize the requesting
worker; an absent registry denies execution. The bridge's legacy worker/state
arguments cannot supply authority. Dependencies are read from authoritative task
rows, and missing or non-completed dependencies deny the lease. Human approval,
protected/unknown risk and malformed authorization policy fail closed.

These checks run in the same immediate transaction as acquisition, renewal or
expired recovery. Renewal of an eligible live lease does not consume another
attempt; recovery does. Initial task admission/import and process-owned registry
configuration remain trusted coordinator operations, not worker APIs.

A claim operation must atomically verify:
- task status is `queued`;
- all dependencies are `completed`;
- no active lease exists;
- worker is enabled and supports the task class;
- worker risk allowance includes the task's risk class;
- required locality/tool capabilities are satisfied;
- human approval, if required before execution, is recorded.

On success:
- increment task attempt;
- create a unique lease ID;
- set `claimed_at` and `expires_at`;
- transition `queued -> claimed`;
- append a `claimed` event.

A worker must heartbeat before lease expiry for long tasks. Loss of heartbeat does not erase work; it only makes the task reclaimable after the lease expires.

## Completion handling

A completion packet is validated against `completion_packet_schema.json` and the task acceptance criteria.

- `blocked`: transition to `blocked`, preserve blocker evidence.
- `failed`: retry only if attempts remain and failure is retryable; otherwise `blocked` or `rejected`.
- `partial`: preserve artifacts/evidence and create the smallest bounded continuation if authorized.
- `completed` read-only/low-risk task: may advance directly when all checks pass and no independent review is required.
- `completed` runtime-changing write task: transition to `review`, then route to an independent verifier.

The producer's claim that work is complete is evidence, not verification.

## Verification handling

Verifier checks:
- acceptance criteria individually;
- changed-file scope;
- tests/static checks;
- provenance and historical-loss risks where relevant;
- safety/authority boundaries;
- whether the completion packet accurately describes the result.

Pass -> append `verification_passed`, transition `review -> completed`.

Repairable fail -> append `verification_failed`, transition `review -> running` only after a new producer/repair lease is granted.

Non-repairable or authority-violating result -> `rejected` or `human_review` gate as appropriate.

## Retry policy

Retries must not become infinite self-healing loops.

Default maximum attempts comes from the task packet. Before retrying, record the failure mode. Prefer changing strategy or worker when the same failure repeats. When attempts are exhausted, mark the task `blocked` with machine-visible evidence and generate a diagnostic follow-up only if it stays inside existing authority.

## Duplicate follow-up prevention

Before queueing a proposed follow-up, normalize and compare:
- parent task;
- objective;
- files/systems in scope;
- acceptance criteria;
- open task references.

If an equivalent open task exists, attach evidence/dependency information to it instead of creating another task.

## Human gates

A task enters a human/governance gate when it requests authority beyond current policy, including protected merges during reconciliation, deployment, new private-data scope, destructive loss of unique history, Constitution changes, financial/credential authority, or disabling audit/safety/rollback controls.

The gate record must identify the exact requested authority and evidence. Approval for one gate does not imply approval for broader future actions.
