# Draft PR — Issue #23 CWA reconciled onto restack tip

## Suggested title

`draft: #23 CWA reconciled onto restack tip d791084`

## `gh pr create` (run after `gh auth login`)

```bash
gh pr create --draft \
  --repo MsElysia/Elysia \
  --base autopilot-003-issue23-restack \
  --head cursor/autopilot-003-issue23-cwa-reconciled \
  --title "draft: #23 CWA reconciled onto restack tip d791084" \
  --body-file docs/DRAFT-PR-ISSUE-23-CWA-RECONCILED-BODY-ONLY-20260911.md
```

Run from a checkout that has the body-only file, or paste the body from that file / the body section below.

## PR body

```markdown
## Summary

- **New** draft PR for Issue #23 construct-without-activate (CWA) **reconciled** onto official restack tip `d791084e716dfcfdaa686374276611ebc0e2a0e6`.
- **Product SHA:** `0a2d135990e8acd3b2a5bbf7539f082ec448de73` on `cursor/autopilot-003-issue23-cwa-reconciled` (docs tip `3c3ead5` is inspection/residuals only — not product).
- **Predecessor PR #34** verified the prior CWA port at `7374820642fad52a6264c86df8632c3a630df592` on `cursor/autopilot-003-issue23-restack-cwa`. Leave #34 open as lineage evidence; do not close; do not mutate its head. **This PR is the reconciliation onto the newer restack tip**, not a retitle of #34.
- **Old PASS does not transfer.** Fresh independent Vega + Architecture gates were run on product `0a2d135`.

## Lineage

| Role | SHA |
|------|-----|
| Common ancestor | `4ff2dc92dd7d9bc393225bce35de9239a9cad6a5` |
| Source verified CWA (PASS does not transfer) | `7374820642fad52a6264c86df8632c3a630df592` |
| Official restack base | `d791084e716dfcfdaa686374276611ebc0e2a0e6` |
| **New product** | `0a2d135990e8acd3b2a5bbf7539f082ec448de73` |

Semantic port (not history cherry-pick). Only content conflict: `tests/guardian_core_test_helpers.py` — merged to preserve tip helper-add intent + CWA-aware adaptations.

## Gates (fresh on `0a2d135`)

| Gate | Verdict | Artifact |
|------|---------|----------|
| Vega | **PASS** 0.88 | `docs/VEGA-ISSUE-23-CWA-RECONCILED-20260911.md` on `codex/vega-reverify-23-cwa-reconciled` |
| Architecture | **READY_FOR_INTEGRATION_REVIEW** 0.87 | `docs/ARCHITECTURE-REVIEW-ISSUE-23-CWA-RECONCILED-20260911.md` on `codex/arch-review-23-cwa-reconciled` @ `d0a0358` |
| CWA tests | **20/20** | construct-without-activate + audit bootstrap |
| Control-plane (#22 lineage union) | **147 passed** | |
| Dynamic inspection | both cycles inert | `docs/AUTOPILOT-003-DYNAMIC-INSPECTION-RECONCILED-20260911.md` @ docs tip `3c3ead5` |

## Residuals (non-blocking)

- Public `ensure_monitoring_started` can start monitors without flipping `_activated`
- GuardianLayer hang when `enable_guardian_layer=True`
- Stale `docs/boot_memory_map.md`
- Phase B deferred by design
- **PR #25: NOT_INHERITED**

## Status

`IMPLEMENTATION_COMPLETE_ON_CURRENT_RESTACK_PENDING_HUMAN_INTEGRATION`

Do **not** merge to main from this draft without human integration decision. Issue #23 stays open.

## Handoff

`docs/ISSUE-23-CWA-RECONCILIATION-HANDOFF-20260911.md` on `docs/handoff-23-cwa-reconciled-20260911`
```

## Issue comment commands

```bash
gh issue comment 11 --repo MsElysia/Elysia --body-file docs/ISSUE-11-CHECKPOINT-COMMENT-23-CWA-RECONCILED-20260911.md
gh issue comment 23 --repo MsElysia/Elysia --body-file docs/ISSUE-23-STATUS-COMMENT-CWA-RECONCILED-20260911.md
```

Do **not** close #23. Do **not** close #34.
