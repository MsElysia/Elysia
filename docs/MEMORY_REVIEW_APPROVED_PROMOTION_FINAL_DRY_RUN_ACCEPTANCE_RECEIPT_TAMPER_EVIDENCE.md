# Memory Review Approved Promotion Final Dry-Run Acceptance Receipt Tamper Evidence

Final dry-run acceptance receipt tamper evidence exists. This dry-run/local
smoke builds a clean final dry-run acceptance receipt, validates it as
`PASS`, then writes isolated corrupted copies that must return `FAIL`.

A clean receipt validates PASS. Corrupted receipt copies validate FAIL.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke.py --json
```

## Covered failures

Covered failures include phrase changes, checkpoint changes, source hash
changes, upstream verdict changes, live-write authorization, vector-write
authorization, live-write design authorization, future campaign requirement
removal, missing blocked reasons, missing next steps, and unsafe metadata.

- `malformed_json`
- `missing_required_receipt_field`
- operator acceptance phrase changed
- operator acceptance phrase invalid
- accepted checkpoint tag changed
- accepted checkpoint hash changed
- source packet, packet tamper, gate, and gate tamper hash mismatches
- upstream packet/gate/tamper verdicts changed from PASS
- accepted_for_final_dry_run_readiness=false
- live memory / vector DB write authorization flags
- live-write design authorization
- future separate live-write campaign requirement removed
- missing blocked reasons
- missing operator next steps
- dry_run / local_only flipped
- unsafe metadata (`model_called`, `embeddings_used`, live writes, network, autonomy)

## Why it is safe

Receipt acceptance remains dry-run-only. Live memory writing remains blocked.
Vector DB writing remains blocked. Live-write design remains blocked. Future
live-write design requires a separate explicit campaign. Future live-write
implementation requires a separate explicit campaign after design approval.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched.
server.py, core.py, and config/autonomy.json are untouched.

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_final_dry_run_acceptance_receipt_tamper_evidence_smoke.py --json --base-dir .\tmp\ap-final-dry-run-acceptance-receipt-tamper --keep-temp
```

Then inspect:

- the clean acceptance receipt
- `tmp\ap-final-dry-run-acceptance-receipt-tamper\tampered_acceptance_receipts\`

## Live-write design authorization gate

The live-write design authorization gate exists. It records
`AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`. It authorizes design-proposal
readiness only after verification. It does not authorize live-write
implementation. It does not authorize live memory writes. It does not
authorize vector DB writes. Future live-write design still requires a
separate design-proposal campaign. Future live-write implementation
requires a separate explicit campaign after design approval.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched.
server.py, core.py, and config/autonomy.json are untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_DESIGN_AUTHORIZATION_GATE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_DESIGN_AUTHORIZATION_GATE.md).
