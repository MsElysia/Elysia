# GitHub commands — Issue #23 CWA reconciled handoff (2026-09-11)

**Blocker:** `gh auth status` reported not logged in → `HUMAN_GOVERNANCE_REQUIRED` for remote PR/issue writes.

Product branch already on origin (tip `3c3ead5` includes product `0a2d135`). Handoff docs branch: `docs/handoff-23-cwa-reconciled-20260911`.

```bash
# 1) Auth
gh auth login

# 2) Confirm SHAs
git fetch --all --prune
git rev-parse 0a2d135990e8acd3b2a5bbf7539f082ec448de73
git ls-remote origin refs/heads/cursor/autopilot-003-issue23-cwa-reconciled
git ls-remote origin refs/heads/autopilot-003-issue23-restack

# 3) Open NEW draft PR only (do not retarget/close #34)
gh pr create --draft \
  --repo MsElysia/Elysia \
  --base autopilot-003-issue23-restack \
  --head cursor/autopilot-003-issue23-cwa-reconciled \
  --title "draft: #23 CWA reconciled onto restack tip d791084" \
  --body-file docs/DRAFT-PR-ISSUE-23-CWA-RECONCILED-BODY-ONLY-20260911.md

# 4) Issue comments (do NOT close #23)
gh issue comment 11 --repo MsElysia/Elysia --body-file docs/ISSUE-11-CHECKPOINT-COMMENT-23-CWA-RECONCILED-20260911.md
gh issue comment 23 --repo MsElysia/Elysia --body-file docs/ISSUE-23-STATUS-COMMENT-CWA-RECONCILED-20260911.md
```

**Do not:** merge to main; force-push shared history; mutate `cursor/autopilot-003-issue23-restack-cwa`; rewrite `autopilot-003-issue23-restack`; close PR #34 or Issue #23.
