# Elysia Control Surface (Single Source of Truth)

CURRENT_TASK: NONE

EXECUTION_RULES:
- Cursor Agent may ONLY act on CURRENT_TASK.
- Cursor Agent may ONLY modify files listed in the task SCOPE.
- Cursor Agent must run ACCEPTANCE steps exactly.
- Cursor Agent must write results to /REPORTS/AGENT_REPORT.md and append /CHANGELOG.md.

NOTES:
- Architecture decisions are made outside Cursor (human + ChatGPT). Cursor is execution-only.
- If any instruction is ambiguous, Cursor stops and reports ambiguity in AGENT_REPORT.
