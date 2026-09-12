# Memory Review Approved Promotion Operator Handoff Smoke

This dry-run/local smoke turns a validated approved-promotion bundle into an
operator handoff package. It is a staging package for human review only, not a
live memory write path.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_operator_handoff_smoke.py --json
```

The command builds a clean approved-promotion bundle, validates the clean
promotion manifest, runs the approved-promotion tamper-evidence smoke, then
writes:

- `approved_promotion_operator_handoff/operator_handoff.json`
- `approved_promotion_operator_handoff/OPERATOR_CHECKLIST.md`
- `approved_promotion_operator_handoff/README.md`

## Handoff coverage

- Includes approved and edited promotion items.
- Keeps rejected candidates excluded and counts the exclusion.
- Includes the promotion manifest path and hash.
- Includes the tamper-evidence result and requires `PASS`.
- Requires all tamper cases to be detected before marking the handoff ready for
  operator review.
- Creates an operator checklist and records its SHA-256 hash.
- Marks the handoff ready for operator review only.
- Marks the handoff not ready for live memory write.
- Requires explicit operator approval for any future live promotion.
- Blocks future live write because live memory writing is intentionally not
  implemented or enabled in this dry-run campaign.

## Why it is safe

- Uses local fixtures and temporary workspaces only.
- Writes handoff files only inside the temp workspace.
- Does not write live runtime memory.
- Does not write vector DB data.
- Does not call models.
- Does not call embeddings.
- Does not use live accounts.
- Does not add UI actions, browser calls, POST forms, or routes.
- Leaves `elysia/api/server.py`, `project_guardian/core.py`, and
  `config/autonomy.json` untouched.

Expected safety fields:

- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `live_vector_db_written: false`
- `account_api_network_accessed: false`
- `autonomy_enabled: false`
- `ready_for_operator_review: true`
- `ready_for_live_memory_write: false`
- `future_live_write_allowed: false`
- `requires_explicit_operator_approval: true`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_operator_handoff_smoke.py --json --base-dir .\tmp\approved-promotion-operator-handoff --keep-temp
```

Then inspect:

- `tmp\approved-promotion-operator-handoff\approved_promotion_operator_handoff\operator_handoff.json`
- `tmp\approved-promotion-operator-handoff\approved_promotion_operator_handoff\OPERATOR_CHECKLIST.md`

## Explicit approval gate

The next dry-run gate is available through:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approval_gate_smoke.py --json
```

That smoke keeps the handoff blocked by default and requires an explicit local
approval artifact tied to the current `operator_handoff.json` hash. Missing
approval, invalid approval tokens, mismatched handoff hashes, and stale handoff
ids fail closed. The documented token is
`APPROVE_DRY_RUN_MEMORY_PROMOTION_STAGING_ONLY`, and a valid token allows
dry-run staging only. It does not allow live memory writing, does not write
vector DB data, does not call models or embeddings, does not use live accounts,
and does not add UI actions or routes. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` remain untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVAL_GATE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVAL_GATE.md).

## Operator-approved dry-run staging

After a valid handoff and a valid explicit operator approval, dry-run
operator-approved staging coverage is available through:

```powershell
python scripts/run_memory_review_approved_promotion_operator_approved_staging_smoke.py --json
```

Staging only happens after both the handoff and approval gate pass. Missing or
invalid approval fails closed. Valid approval allows dry-run staging only.
Staging includes approved and edited promotion items, keeps rejected items
excluded, and records promotion, handoff, and approval-gate hashes. Staging is
not live memory write readiness. Live memory writing is not implemented or
enabled. Vector DB writing is not implemented or enabled. The campaign does not
call models or embeddings, does not use live accounts, and does not add UI
actions or routes. `elysia/api/server.py`, `project_guardian/core.py`, and
`config/autonomy.json` remain untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING.md`](MEMORY_REVIEW_APPROVED_PROMOTION_OPERATOR_APPROVED_STAGING.md).
