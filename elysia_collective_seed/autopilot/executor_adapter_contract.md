# Disabled Executor Adapter Contract

Status: sandbox-only design contract. This document does not authorize or implement live provider invocation, network/subprocess execution, Git mutation, GitHub write transport, credential access, deployment, or external posting.

## Purpose

Define the fail-closed boundary between an already-authorized task claim and any future executor adapter. The current deterministic dispatcher selects workers but does not execute provider work. This contract makes the missing execution boundary explicit without activating it.

## Invocation envelope

A future adapter invocation MUST bind all of the following before any execution-capable implementation may be considered:

- `task_id` and immutable `task_digest`;
- `worker_id` and worker/provider identity;
- `claim_id`, `lease_id`, and lease expiry;
- repository identity;
- isolated target branch;
- exact expected starting commit SHA;
- approved capability set and risk class;
- unique attempt ID;
- human-approval reference when the task packet requires one.

The adapter MUST reject an envelope when any bound value is missing, stale, malformed, inconsistent with authoritative ledger state, or broader than the task packet's approved authority.

## Dry-run result envelope

The sandbox adapter may return only a deterministic terminal simulation result containing:

- the same task/worker/claim/lease/attempt identity;
- `outcome` in `would_execute`, `refused`, or `blocked`;
- normalized refusal/block reason when applicable;
- expected repository/branch/start-SHA binding;
- approved capabilities echoed exactly, never expanded;
- evidence records sufficient to reconstruct the decision.

`would_execute` means only that the envelope passed contract validation. It MUST NOT be represented as task completion, repository mutation, provider success, or verification PASS.

## Mandatory refusal conditions

The dry-run adapter MUST fail closed for at least:

1. expired or unknown claim/lease;
2. worker mismatch or unregistered worker;
3. repository mismatch;
4. branch mismatch or non-isolated branch;
5. current/expected starting SHA mismatch;
6. requested capability not present in the approved capability set;
7. risk-class escalation;
8. missing required human approval;
9. attempt identity reuse or mismatch;
10. completion/result claiming files, commits, PRs, provider output, or other side effects that did not occur.

## Safety invariants

This slice MUST remain deterministic and side-effect free. Tests must be able to run without credentials, network access, subprocess execution, provider SDKs/CLIs, Git mutation, GitHub writes, Guardian runtime activation, or live adapter registration.

No adapter described by this contract may infer authority from prose, branch names, caller-supplied capabilities, or a preferred-worker field alone. Authoritative task/claim/lease state and approved capabilities must be supplied by the trusted control-plane boundary.

## Acceptance for the next implementation slice

A disabled deterministic adapter and tests should demonstrate: valid envelopes normalize identically; every mandatory refusal condition fails closed; no authority can be added by adapter input; stale head/claim/lease state is rejected; simulated terminal evidence cannot masquerade as a completion packet; and importing/running the adapter performs no provider, network, subprocess, Git, GitHub-write, or runtime action.

Any live provider adapter, credential plumbing, repository mutation, or external-write transport is a separate governance-gated product and is explicitly out of scope.