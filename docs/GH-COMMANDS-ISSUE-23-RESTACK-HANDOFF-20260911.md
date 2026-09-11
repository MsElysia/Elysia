# After: gh auth login (or set GH_TOKEN)

# From worktree: .worktrees/handoff-23-restack-cwa-pr
# Or any checkout that has docs/DRAFT-PR-ISSUE-23-RESTACK-CWA-BODY-ONLY-20260911.md

gh pr create --repo MsElysia/Elysia --draft \
  --base autopilot-003-issue23-restack \
  --head cursor/autopilot-003-issue23-restack-cwa \
  --title "draft: AUTOPILOT-003 #23 restack construct-without-activate (CWA)" \
  --body-file "docs/DRAFT-PR-ISSUE-23-RESTACK-CWA-BODY-ONLY-20260911.md"

gh issue comment 11 --repo MsElysia/Elysia --body-file "docs/ISSUE-11-CHECKPOINT-COMMENT-23-RESTACK-20260911.md"
gh issue comment 23 --repo MsElysia/Elysia --body-file "docs/ISSUE-23-STATUS-COMMENT-20260911.md"
