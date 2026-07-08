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
