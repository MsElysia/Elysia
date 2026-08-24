# Memory Review Approved Promotion Final Readiness Operator Acceptance Gate Tamper Evidence

Final readiness operator acceptance gate tamper-evidence exists. This
dry-run/local smoke builds a clean acceptance gate report, validates it as
`PASS`, then writes isolated corrupted copies that must return `FAIL`.

A clean acceptance gate report validates `PASS`. Corrupted acceptance gate
reports validate `FAIL`.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke.py --json
```

## Covered failures

Covered failures include phrase changes, hash mismatches, missing acceptance
case, invalid case marked pass, valid case marked fail, live-write
authorization, vector-write authorization, future campaign requirement
removal, and unsafe metadata.

- `malformed_json`
- `missing_required_gate_field`
- acceptance phrase changed
- acceptance artifact missing but valid=true
- acceptance artifact, source packet, and source tamper-evidence hash mismatches
- packet tamper evidence not PASS
- clean packet not PASS
- missing acceptance case
- invalid case marked PASS
- valid case marked FAIL
- invalid cases not failed closed
- valid acceptance not dry-run-only
- live memory / vector DB write authorization flags
- future separate live-write campaign requirement removed
- operator_required / dry_run / local_only flipped
- unsafe metadata (`model_called`, `embeddings_used`, live writes, network, autonomy)

## Why it is safe

- Valid acceptance remains dry-run-only.
- Live memory writing remains blocked.
- Vector DB writing remains blocked.
- No live memory/vector write path is implemented.
- Future live write requires a separate explicit campaign.
- Models/embeddings/accounts/network are not called.
- `elysia/api/server.py`, `project_guardian/core.py`, and
  `config/autonomy.json` are untouched.

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_final_readiness_operator_acceptance_gate_tamper_evidence_smoke.py --json --base-dir .\tmp\ap-final-acceptance-gate-tamper --keep-temp
```

Then inspect:

- the clean acceptance gate report
- `tmp\ap-final-acceptance-gate-tamper\tampered_acceptance_gate_reports\`
