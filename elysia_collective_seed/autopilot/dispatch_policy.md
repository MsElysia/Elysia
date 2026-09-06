# Autopilot Dispatch Policy

This policy is provider-neutral and runtime-disabled until the canonical Guardian runtime is verified.

## Eligibility

A worker is eligible only when all of the following are true:

1. `enabled=true` in the worker registry.
2. The task class is listed in the worker's `task_classes`.
3. The task risk class is listed in the worker's `risk_classes`.
4. Every task dependency is in a terminal successful state.
5. Any locality requirement can be satisfied by the worker.
6. The worker is not over its concurrency limit.
7. The task does not require human approval, or that approval is already recorded.

Workers never infer additional authority from a task description.

## Deterministic ranking

Eligible workers are ranked by this tuple, lowest value winning where applicable:

1. explicit `preferred_worker` match;
2. required capability coverage, with complete coverage required;
3. historical success ratio for the task class when enough observations exist;
4. `quality_rank`;
5. `cost_rank`;
6. active load;
7. stable lexical `worker_id` tie-break.

The dispatcher must record the candidates considered and the reason the selected worker won. Routing must be reproducible from the same registry/task state.

## Claim lease

A task moves `queued -> claimed` only through an atomic claim operation containing:

- task ID;
- worker ID;
- lease ID;
- claimed timestamp;
- lease expiry;
- attempt number.

A worker may move its leased task to `running`. An expired lease returns the task to `queued` unless the maximum attempt count has been reached. Late completion packets from expired leases are evidence only and cannot mutate accepted task state.

## Verification independence

Runtime-affecting writes require independent verification. A verifier must not share the same execution identity as the producer. When practical, prefer a different `independence_group`, provider, or model family. If no independent verifier is available, the task remains in `review` rather than silently self-approving.

Read-only/documentation tasks may use mechanical checks as verification when their acceptance criteria are completely machine-verifiable.

## Retry and failure

Failures are classified as:

- `TRANSIENT_WORKER_FAILURE`
- `TASK_UNDERSPECIFIED`
- `TEST_FAILURE`
- `POLICY_BLOCK`
- `MISSING_DEPENDENCY`
- `MISSING_CAPABILITY`
- `HUMAN_GATE`
- `PERMANENT_FAILURE`

Transient failures may retry with bounded backoff. Test failures normally route back to the producer or another implementation worker with the verifier evidence attached. Missing capability/dependency failures create a bounded follow-up proposal when allowed by the orchestrator policy. Human gates do not retry automatically.

## Duplicate prevention

Before accepting a proposed follow-up task, compare:

- normalized objective;
- source refs;
- files in scope;
- parent task;
- open dependency graph.

A likely duplicate is linked to the existing task instead of creating parallel work. The system must preserve the proposal as evidence even when deduplicated.

## Integration state

`completed` means the task's acceptance criteria and required verification passed. It does **not** imply merge to `main`, deployment, or external execution. Those are separate gated actions.
