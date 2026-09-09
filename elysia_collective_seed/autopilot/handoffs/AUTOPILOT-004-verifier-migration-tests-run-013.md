# AUTOPILOT-004 verifier migration test checkpoint

Status: implementation-driving regression checkpoint
Scope: PR #15 / `autopilot-004-verifier-lifecycle-impl`

## Durable change

Added `tests/test_autopilot_verifier_ledger_migration.py` to pin the additive SQLite migration requirement before implementation.

The regression fixture creates the exact pre-verifier `tasks`/`events` shape, including an existing task with `attempt=2` and an existing audit event. Opening that database through `TaskLedger` is required to:

- add the six verifier lifecycle columns without dropping/recreating the task table;
- preserve the existing task payload, status, attempt count, and event detail;
- remain idempotent when the same ledger is opened again;
- avoid duplicate migration columns or synthetic history loss.

## Expected current state

These tests are specification-first and are expected to fail on the current implementation because `_init_schema()` still lacks the additive migration. They must not be treated as acceptance evidence until the implementation lands and exact-head CI passes.

## Handoff

Next bounded step: implement the idempotent migration in `TaskLedger._init_schema()` using schema introspection plus additive `ALTER TABLE ... ADD COLUMN` operations, then run/verify these tests. After migration is green, implement verifier submit/claim/accept/reject/reap operations and the remaining lifecycle contract tests.

No provider invocation, Guardian runtime wiring, network/subprocess execution, merge, deployment, external posting, credential/private-chat access, destructive archive action, or authority expansion was performed.
