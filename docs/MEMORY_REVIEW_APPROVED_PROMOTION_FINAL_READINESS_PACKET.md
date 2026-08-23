# Memory Review Approved Promotion Final Readiness Packet

This dry-run/local smoke builds the current approved-promotion safety chain and
writes one operator-readable packet. The packet answers what would be promoted,
why it is approved, which hashes prove it was not tampered with, which safety
checks passed, why live writing is still blocked, and what future explicit
milestone would be required.

The final readiness packet exists. It summarizes the approved-promotion safety
chain. It is dry-run only.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_packet_smoke.py --json
```

The command writes:

- `approved_promotion_final_readiness_packet/final_readiness_packet.json`
- `approved_promotion_final_readiness_packet/FINAL_READINESS_README.md`

## Coverage

- Approved and edited items are included.
- Rejected candidates remain excluded.
- Source hashes are recorded for the bundle, promotion manifest, operator
  handoff, approval gate, staging manifest, staging tamper evidence, live-write
  blockade, and live-write blockade tamper evidence.
- The safety chain records `PASS` for promotion bundle, promotion tamper
  evidence, operator handoff, operator approval gate, operator-approved
  staging, staging tamper evidence, live-write blockade, and live-write
  blockade tamper evidence.
- `ready_for_live_memory_write` remains `false`.
- `future_live_write_allowed` remains `false`.
- `requires_future_live_write_milestone` remains `true`.

## Why it is safe

- Live memory writing remains blocked.
- Vector DB writing remains blocked.
- No live memory/vector write path is implemented.
- Future live write requires a separate explicit milestone.
- Models/embeddings/accounts/network are not called.
- `elysia/api/server.py`, `project_guardian/core.py`, and
  `config/autonomy.json` are untouched.

Expected safety fields:

- `verdict: PASS`
- `ready_for_operator_review: true`
- `ready_for_operator_approved_staging: true`
- `ready_for_live_memory_write: false`
- `future_live_write_allowed: false`
- `requires_explicit_operator_approval: true`
- `requires_future_live_write_milestone: true`
- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `live_vector_db_written: false`
- `account_api_network_accessed: false`
- `autonomy_enabled: false`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_packet_smoke.py --json --base-dir .\tmp\ap-final-readiness --keep-temp
```

Then inspect:

- `tmp\ap-final-readiness\approved_promotion_final_readiness_packet\final_readiness_packet.json`
- `tmp\ap-final-readiness\approved_promotion_final_readiness_packet\FINAL_READINESS_README.md`
