# Memory Review Approved Promotion Live-Write Design Proposal

The live-write design proposal exists. It records
`AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`. It records a design proposal
only.

It does not implement the live-write path. It does not authorize live
memory writes. It does not authorize vector DB writes. Future live-write
implementation requires a separate explicit campaign after design
approval. Separate operator approval is still required for live writes.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_design_proposal_smoke.py --json
```

The command writes:

- `approved_promotion_live_write_design_proposal/live_write_design_proposal.json`
- `approved_promotion_live_write_design_proposal/live_write_design_proposal_report.json`
- `approved_promotion_live_write_design_proposal/LIVE_WRITE_DESIGN_PROPOSAL.md`

## Recorded authorization

- Phrase: `AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`
- Accepted checkpoint tag: `memory_review_approved_promotion_live_write_design_authorization_gate_clean_1`
- Accepted checkpoint hash: `a5b4f7ef480bc591fa9ef95d63adc8bf0b64f88a`

## Authorization

- `authorized_for_live_write_design_proposal: true` only for the valid case
- `authorized_for_live_write_implementation: false`
- `authorized_for_live_memory_write: false`
- `authorized_for_vector_db_write: false`
- `live_memory_write_allowed: false`
- `vector_db_write_allowed: false`
- `live_write_implemented: false`
- `ready_for_live_write_implementation: false`
- `requires_separate_live_write_implementation_campaign: true`
- `requires_separate_operator_approval_for_live_write: true`

## Proposal scope

- Future live memory writes, if ever implemented, would remain dry-run blocked by default and would require a later implementation campaign.
- Future vector DB writes, if ever implemented, would remain dry-run blocked by default and would require that same later implementation campaign.
- Any later implementation campaign must keep `config/autonomy.json` `enabled=false` unless a separate explicit autonomy campaign is accepted.
- Any later implementation campaign must leave `project_guardian/core.py` and `elysia/api/server.py` untouched unless a separate explicit campaign names them.
- Any later live write would still require a distinct operator approval phrase that is not `AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`.
- This proposal does not add write APIs, UI routes, POST actions, watchers, daemons, schedulers, model calls, embedding calls, or network access.

## Fail-closed cases

- Missing design proposal artifact fails closed.
- Invalid design authorization phrase fails closed.
- Mismatched gate hash fails closed.
- Gate not PASS fails closed.
- Proposal claiming live-write implementation fails closed.
- Proposal claiming live memory write fails closed.
- Proposal claiming vector DB write fails closed.
- Proposal omitting a separate implementation campaign fails closed.

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_design_proposal_smoke.py --json --base-dir .\tmp\ap-live-write-design-proposal --keep-temp
```

Then inspect:

- `tmp\ap-live-write-design-proposal\approved_promotion_live_write_design_proposal\live_write_design_proposal.json`
- `tmp\ap-live-write-design-proposal\approved_promotion_live_write_design_proposal\LIVE_WRITE_DESIGN_PROPOSAL.md`
- `tmp\ap-live-write-design-proposal\approved_promotion_live_write_design_proposal\proposal_cases\`
