# AUTOPILOT-004 Handoff — Dispatch Foundation

## Task
Advance GitHub issue #8: provider-neutral task dispatcher and worker adapters.

## Worker
ChatGPT-side Autopilot Supervisor.

## Completed

- Added `worker_registry_schema.json` defining provider-neutral worker capabilities, risk permissions, locality, concurrency, independence groups, quality/cost ranking, and outcome counters.
- Added `dispatch_policy.md` defining deterministic eligibility/ranking, atomic claim leases, verification independence, bounded retries, failure classes, duplicate prevention, and the distinction between task completion and protected integration/deployment.

## Evidence

- Commit `23f793fc57ca5564435f3680b766e991fe2cc2ab` — worker registry schema.
- Commit `828e7d10df304b932796f5493d95ce28b836963e` — dispatch policy.
- Existing shared contract verified at `AGENTS.md` on `elysia-collective-0.1-seed`.
- Existing orchestrator/task packet artifacts inspected before this change.

## Files read

- `AGENTS.md`
- `elysia_collective_seed/autopilot/orchestrator_spec.md`
- `elysia_collective_seed/autopilot/task_packet_schema.json`

## Files changed

- `elysia_collective_seed/autopilot/worker_registry_schema.json`
- `elysia_collective_seed/autopilot/dispatch_policy.md`
- this handoff record

## Checks

Manual schema/policy consistency check against the task packet and orchestrator specification. No runtime code was enabled or executed.

## Uncertainties

- Exact Codex/Cursor adapter APIs should be implemented only after their execution surfaces are selected and credentials/runtime boundaries are configured.
- The canonical Guardian runtime is still gated on local archive reconciliation.

## Risks

Low. These are additive design/schema artifacts on an isolated seed branch. They grant no runtime authority.

## Next recommended task

Implement a deterministic, no-provider dry-run dispatcher on `elysia-collective-dryrun` that consumes synthetic task/worker state and proves dependency gating, risk gating, deterministic routing, lease expiry, independent verification, retries, and duplicate follow-up suppression. Keep all real provider adapters disabled.

## Recommended next role
Engineer, followed by independent verifier.
