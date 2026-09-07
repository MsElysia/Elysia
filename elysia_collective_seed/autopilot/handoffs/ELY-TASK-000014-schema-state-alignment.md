# ELY-TASK-000014 — Task schema/runtime state alignment

## Objective
Keep the provider-neutral task packet contract aligned with the runtime ledger state machine without enabling runtime providers or Guardian execution.

## Finding
The AUTOPILOT-004 ledger treats `verifying` and `human_review` as explicit non-dispatchable control states, but the task packet JSON Schema did not permit those values. That allowed runtime state to diverge from the durable interchange contract.

## Changes
- Added `verifying` and `human_review` to `task_packet_schema.json` status enum.
- Added a regression assertion that all current runtime control states are declared by the schema.

## Safety
Schema/test-only change on isolated branch `autopilot-004-schema-state-alignment`. No provider invocation, Guardian runtime wiring, network/subprocess execution, deployment, external posting, credential access, or merge.

## Evidence
- Source ledger: `elysia_collective_seed/autopilot/task_ledger.py` defines `verifying` and `human_review` as non-dispatchable states.
- Contract: `elysia_collective_seed/autopilot/task_packet_schema.json` now admits both states.
- Regression: `elysia_collective_seed/autopilot/test_task_schema_alignment.py::test_task_schema_declares_runtime_control_states`.

## Handoff
Independent verification should run the existing AUTOPILOT CI/test suite on this branch. If green, this bounded repair can be incorporated into the AUTOPILOT-004 draft branch without changing its draft/unmerged integration gate.
