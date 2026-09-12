# Memory Review Approved Promotion Live-Write Design Authorization Gate

The live-write design authorization gate exists. It records
`AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`. It authorizes design-proposal
readiness only after verification. It does not authorize live-write
implementation. It does not authorize live memory writes. It does not
authorize vector DB writes. Future live-write design still requires a
separate design-proposal campaign. Future live-write implementation
requires a separate explicit campaign after design approval.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched.
server.py, core.py, and config/autonomy.json are untouched.

This campaign authorizes design-gate validation only. It does not design
the live-write path. It does not implement the live-write path.

`ready_for_future_live_write_design=true` means only that a separate future
design-proposal campaign may be started after this gate is verified. It
does not mean design is implemented. It does not mean live writes are
allowed.

Run:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke.py --json
```

The command writes:

- `approved_promotion_live_write_design_authorization_gate/live_write_design_authorization_gate.json`
- `approved_promotion_live_write_design_authorization_gate/LIVE_WRITE_DESIGN_AUTHORIZATION_GATE.md`

## Design-only phrase

- Phrase: `AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`
- Valid authorization authorizes a future live-write design-proposal campaign only.

## Authorization

- `authorized_for_live_write_design_proposal: true` only for the valid case
- `authorized_for_live_write_implementation: false`
- `authorized_for_live_memory_write: false`
- `authorized_for_vector_db_write: false`
- `live_memory_write_allowed: false`
- `vector_db_write_allowed: false`
- `ready_for_future_live_write_design: true` after this gate is verified
- `requires_separate_live_write_design_campaign: true`
- `requires_separate_live_write_implementation_campaign: true`
- `requires_separate_operator_approval_for_live_write: true`

## Fail-closed cases

- Missing design authorization artifact fails closed.
- Invalid design authorization phrase fails closed.
- Mismatched receipt hash fails closed.
- Mismatched receipt tamper hash fails closed.
- Receipt not PASS fails closed.
- Receipt tamper not PASS fails closed.
- Authorization claiming live-write implementation fails closed.
- Authorization claiming live memory write fails closed.
- Authorization claiming vector DB write fails closed.

To inspect artifacts after a run:

```powershell
python scripts/run_memory_review_approved_promotion_live_write_design_authorization_gate_smoke.py --json --base-dir .\tmp\ap-live-write-design-authorization-gate --keep-temp
```

Then inspect:

- `tmp\ap-live-write-design-authorization-gate\approved_promotion_live_write_design_authorization_gate\live_write_design_authorization_gate.json`
- `tmp\ap-live-write-design-authorization-gate\approved_promotion_live_write_design_authorization_gate\LIVE_WRITE_DESIGN_AUTHORIZATION_GATE.md`
- `tmp\ap-live-write-design-authorization-gate\approved_promotion_live_write_design_authorization_gate\authorization_cases\`

## Live-write design proposal

The live-write design proposal exists. It records
`AUTHORIZE_LIVE_WRITE_DESIGN_PROPOSAL_ONLY`. It records a design proposal
only. It does not implement the live-write path. It does not authorize live
memory writes. It does not authorize vector DB writes. Future live-write
implementation requires a separate explicit campaign after design
approval. Separate operator approval is still required for live writes.
Models/embeddings/accounts/network are not called. `elysia/api/server.py`,
`project_guardian/core.py`, and `config/autonomy.json` are untouched. See
[`MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_DESIGN_PROPOSAL.md`](MEMORY_REVIEW_APPROVED_PROMOTION_LIVE_WRITE_DESIGN_PROPOSAL.md).
