# Memory Review Approved Promotion Final Readiness Operator Acceptance Gate

The final readiness operator acceptance gate exists. This dry-run/local smoke
rebuilds a valid final readiness packet and its tamper evidence, then requires a
separate explicit operator acceptance artifact before that packet can be treated
as accepted dry-run readiness.

Missing acceptance fails closed. An invalid acceptance phrase fails closed. A
mismatched packet hash fails closed. A mismatched tamper-evidence hash fails
closed. Valid acceptance only accepts final dry-run readiness. Valid acceptance
does not authorize live memory writes. Valid acceptance does not authorize
vector DB writes. Future live write still requires a separate explicit campaign.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke.py --json
```

The command writes:

- `approved_promotion_final_readiness_operator_acceptance_gate/operator_acceptance_gate.json`
- `approved_promotion_final_readiness_operator_acceptance_gate/OPERATOR_ACCEPTANCE_GATE_README.md`

## Acceptance phrase

The explicit dry-run acceptance phrase is:

```text
ACCEPT_FINAL_DRY_RUN_READINESS_PACKET_ONLY
```

A valid acceptance artifact must include that phrase and:

- `source_final_readiness_packet_sha256` matching the current packet hash
- `source_final_readiness_tamper_evidence_sha256` matching the current
  tamper-evidence hash
- packet tamper evidence verdict `PASS`
- `accepted_for_final_dry_run_readiness: true`
- `accepted_for_live_memory_write: false`
- `accepted_for_vector_db_write: false`
- `ready_for_future_live_write_design: false`
- `requires_separate_live_write_campaign: true`
- `live_memory_write_allowed: false`
- `vector_db_write_allowed: false`
- `dry_run: true`
- `local_only: true`

## Fail-closed cases

- `missing_acceptance_artifact`
- `invalid_acceptance_phrase`
- `mismatched_packet_hash`
- `mismatched_tamper_evidence_hash`
- `tamper_evidence_not_pass`
- `acceptance_claims_live_memory_write`
- `acceptance_claims_vector_db_write`

The valid case is `valid_final_dry_run_acceptance`.

## Why it is safe

- Valid acceptance only accepts final dry-run readiness.
- Valid acceptance does not authorize live memory writes.
- Valid acceptance does not authorize vector DB writes.
- Future live write still requires a separate explicit campaign.
- Models/embeddings/accounts/network are not called.
- `elysia/api/server.py`, `project_guardian/core.py`, and
  `config/autonomy.json` are untouched.

Expected safety fields for the valid scenario:

- `verdict: PASS`
- `acceptance_phrase: ACCEPT_FINAL_DRY_RUN_READINESS_PACKET_ONLY`
- `operator_acceptance_valid: true`
- `accepted_for_final_dry_run_readiness: true`
- `accepted_for_live_memory_write: false`
- `accepted_for_vector_db_write: false`
- `ready_for_future_live_write_design: false`
- `requires_separate_live_write_campaign: true`
- `live_memory_write_allowed: false`
- `vector_db_write_allowed: false`
- `model_called: false`
- `embeddings_used: false`
- `live_memory_written: false`
- `live_vector_db_written: false`
- `account_api_network_accessed: false`
- `autonomy_enabled: false`

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_smoke.py --json --base-dir .\tmp\ap-final-acceptance-gate --keep-temp
```

Then inspect:

- `tmp\ap-final-acceptance-gate\approved_promotion_final_readiness_operator_acceptance_gate\operator_acceptance_gate.json`
- `tmp\ap-final-acceptance-gate\approved_promotion_final_readiness_operator_acceptance_gate\OPERATOR_ACCEPTANCE_GATE_README.md`
- `tmp\ap-final-acceptance-gate\approved_promotion_final_readiness_operator_acceptance_gate\acceptance_cases\`
