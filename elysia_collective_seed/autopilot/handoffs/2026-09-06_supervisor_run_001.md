# Autopilot Supervisor Handoff 001

## Task
Advance the highest-priority safe unblocked work while local historical archives and primary Constitution sources remain unavailable.

## Selected work
AUTOPILOT-004 provider-neutral dispatcher groundwork is unblocked and can proceed without enabling runtime agents.

## Completed
- Added `worker_registry.json` with provider-neutral capability/risk metadata for ChatGPT, Codex, Cursor, and optional local workers.
- Added `task_state_machine.md` defining normal, blocked, retry, verification, human-review, lease, and follow-up transitions.
- Added `audit_event_schema.json` so state transitions can be recorded as auditable events rather than mutable chat-only state.

## Safety posture
- All artifacts are design/configuration only and explicitly runtime-disabled where applicable.
- No provider credentials or external-write authority were added.
- No merge to `main`, deployment, local private-data access, or destructive archive operation occurred.

## Blockers retained
- AUTOPILOT-001 authoritative Constitution/Genesis recovery still needs primary historical sources.
- AUTOPILOT-002 full reconciliation still needs access to the user's local Guardian/Elysia archive.
- AUTOPILOT-003 can only become final after local reconciliation, though GitHub-baseline static work may continue.

## Recommended next role
Engineer, then independent verifier.

## Recommended next bounded task
Implement a runtime-disabled in-memory/disk test ledger that enforces the documented transition graph, leases, retries, and append-only audit events against synthetic tasks. Add tests proving invalid direct transitions and authority-expanding follow-ups are rejected. Do not connect real Codex/Cursor execution yet.
