# Disabled GitHub Synchronization Planning Contract

Status: specification-only; disabled by default.

## Purpose
Define a provider-neutral boundary that translates already-authorized Elysia task/completion state into proposed GitHub Issue/PR synchronization operations without performing network writes. This contract is a planning surface only and does not authorize GitHub mutation.

## Safety invariants
1. The planner MUST be pure: input state in, proposed operations out. It MUST NOT call GitHub, spawn subprocesses, invoke providers/models, read credentials, merge/close PRs, deploy, post externally, or modify Guardian runtime state.
2. Default execution interface MUST be a no-op. A future write-capable executor is a separate authority surface and remains disabled until explicitly approved under AGENTS.md and project governance.
3. `external_write`, `deployment`, `sensitive_data`, and `privileged` task risk classes MUST produce a refusal/human-gate result unless the exact operation has separately recorded human approval. Planning alone MUST NOT convert approval requirements into authority.
4. Proposed operations MUST be limited to bounded synchronization metadata such as: issue status/labels, task identifiers, branch/PR references, verification state, and redacted evidence summaries. No merge, auto-merge, PR close, branch deletion, release, deployment, secret mutation, or repository-administration operation may be proposed.
5. Private chatlogs, credentials, tokens, raw sensitive payloads, and unrelated personal data MUST NOT enter proposed GitHub payloads. Inputs marked sensitive/private must be replaced by a non-content provenance reference or redaction marker.

## Input contract
The planner consumes immutable snapshots containing:
- task packet validated against `task_packet_schema.json`;
- optional completion packet validated against `completion_packet_schema.json`;
- current known GitHub synchronization snapshot (issue/PR IDs, revision/version marker, prior operation fingerprints);
- explicit approval record when required by risk class.

The planner must not infer missing approval from repository access, worker identity, prior success, or conversational context.

## Proposed operation envelope
Each proposal must contain:
- deterministic `operation_id` derived from task ID + target + operation kind + expected source revision + normalized payload;
- `task_id`;
- target kind (`issue` or `pull_request`);
- target identifier;
- operation kind from an allowlist;
- expected source revision/state;
- redacted normalized payload;
- reason/evidence references;
- approval requirement and approval reference if applicable.

The operation allowlist is intentionally narrow: metadata/status synchronization and additive audit/handoff comments only. Executor-specific network actions are out of scope.

## Idempotency and duplicate prevention
- Replanning identical state MUST produce the same `operation_id` and normalized proposal.
- If an operation fingerprint is already recorded as applied, the planner MUST return `noop_already_applied` rather than proposing a duplicate.
- Additive comments/handoffs MUST include a stable task/evidence fingerprint so retries cannot create duplicate audit spam.

## Stale-state refusal
The planner MUST refuse mutation planning when its expected task revision, lease owner, completion packet, verification state, issue/PR revision marker, or prior-operation set conflicts with the supplied synchronization snapshot. The result must be `stale_state` with no proposed write. Stale data is never resolved by last-write-wins behavior.

## Verification semantics
- Producer completion may synchronize a `verifying` state but MUST NOT synchronize terminal `completed` for consequential write work until independent verification is recorded.
- A producer may not create a proposal that represents its own independent verification.
- Failed verification may propose bounded status/evidence synchronization only; it cannot widen task scope or authority.

## Required static tests before implementation is accepted
1. Identical inputs produce identical operation IDs and payloads.
2. Previously applied fingerprint produces no-op, not a duplicate proposal.
3. Revision/state mismatch produces `stale_state` and zero proposed operations.
4. No proposal can encode merge, auto-merge, PR close, branch deletion, release, deployment, secret, credential, or repository-administration actions.
5. Sensitive/private input content is absent from serialized proposal payloads.
6. High-authority risk classes refuse without an explicit matching approval record.
7. Completion of consequential writes remains `verifying` until independent verification evidence exists.
8. No-op executor performs zero network/subprocess/provider calls.

## Future implementation boundary
A later implementation may add a pure `plan_sync(...)` function and injectable `NoOpSyncExecutor`. Any real GitHub executor must be developed and reviewed as a separate gated task. This specification grants no external-write authority.
