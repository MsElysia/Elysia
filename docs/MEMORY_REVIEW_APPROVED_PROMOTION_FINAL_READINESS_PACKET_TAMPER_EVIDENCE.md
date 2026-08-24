# Memory Review Approved Promotion Final Readiness Packet Tamper Evidence

Final readiness packet tamper-evidence exists. This dry-run/local smoke builds a
clean final readiness packet, validates it as `PASS`, then writes isolated
corrupted copies that must return `FAIL`.

A clean final readiness packet validates `PASS`. Corrupted packet copies
validate `FAIL`.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke.py --json
```

## Covered failures

Covered failures include hash mismatches, item edits, rejected inclusion,
safety-chain edits, live-write flag changes, missing blocked reasons, missing
future milestone requirement, and unsafe metadata.

- `malformed_json`
- `missing_required_packet_field`
- README and all source hash mismatches
- approval token phrase missing
- approved or edited item removed
- edited promoted text changed
- rejected item included
- promotion/exclusion count mismatches
- missing or failed safety-chain stage
- live-write readiness flags flipped
- future milestone requirement removed
- missing blocked reasons
- missing future-milestone operator next step
- unsafe metadata

## Why it is safe

- Live memory writing remains blocked.
- Vector DB writing remains blocked.
- No live memory/vector write path is implemented.
- Future live write requires a separate explicit milestone.
- Models/embeddings/accounts/network are not called.
- `elysia/api/server.py`, `project_guardian/core.py`, and
  `config/autonomy.json` are untouched.

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_packet_tamper_evidence_smoke.py --json --base-dir .\tmp\ap-final-readiness-tamper --keep-temp
```

Then inspect:

- the clean final readiness packet
- `tmp\ap-final-readiness-tamper\tampered_final_readiness_packets\`

## Final readiness operator acceptance gate

The final readiness operator acceptance gate exists. Missing acceptance fails
closed. An invalid acceptance phrase fails closed. A mismatched packet hash
fails closed. A mismatched tamper-evidence hash fails closed. Valid acceptance
only accepts final dry-run readiness. Valid acceptance does not authorize live
memory writes. Valid acceptance does not authorize vector DB writes. Future live
write still requires a separate explicit campaign.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_OPERATOR_ACCEPTANCE_GATE.md`](MEMORY_REVIEW_APPROVED_PROMOTION_FINAL_READINESS_OPERATOR_ACCEPTANCE_GATE.md).
