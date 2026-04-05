# UI / Control Panel Specification

## Artifact & History Policy

The FastAPI UI is a **read-only control surface** for:
- Displaying `run_once` and acceptance status/history
- Displaying and managing review requests and approvals
- Creating task/mutation payload files via explicit user actions

The UI **must not** perform any hidden writes beyond:
- Writing `REPORTS/run_once_last.json` and `REPORTS/run_once_history/*` via Core when `/control/run-once` is invoked
- Writing `REPORTS/acceptance_last.*` and `REPORTS/acceptance_history/*` only when acceptance actually runs
- Appending to `REPORTS/review_queue.jsonl` when enqueueing review requests
- Updating `REPORTS/approval_store.json` when explicit approve/deny actions are taken

No artifacts may be written on deny/review outcomes except review queue entries.