# Self-improvement proposal queue

## Design (proposal-only)

Self-improvement is **record-and-review**, not autonomous repair:

1. Detect an issue or learning outcome  
2. **Create proposal** (structured row)  
3. **Rank** for triage (priority score)  
4. **Inspect** via API or JSONL  
5. Human (or Cursor / Codex) reviews and may author a patch **outside** this queue  

This subsystem **does not**:

- Apply patches or mutate the repository  
- Run shell commands or spawn subprocesses  
- Call LLMs or wire autonomy loops  
- Store raw Think–Decide–Act traces or other high-risk blobs in proposals  

Status updates through the API only change persisted proposal fields (status + optional review note).

## Storage

- **Canonical queue (source of truth):** `data/runtime/self_improvement_proposals.jsonl`  
- **Legacy brain queue (historical / opt-in duplicate):** `data/runtime/brain_self_improvement_queue.jsonl`  

`JsonlSelfImprovementQueue` appends a **canonical** proposal when the brain pipeline enqueues self-improvement.  
Legacy JSONL writes are **retired by default**. To temporarily re-enable dual-write (legacy row + canonical proposal), set:

```text
ELYSIA_LEGACY_SELF_IMPROVEMENT_QUEUE=1
```

Truthy values: `1`, `true`, `yes`, `on`. Existing legacy files are **not** deleted or rewritten automatically.

## Schema (`SelfImprovementProposal`)

| Field | Notes |
|--------|--------|
| `proposal_id` | Stable id per row (e.g. `prop_` + hex) |
| `created_at` | UTC ISO-8601 with `Z` suffix |
| `source` | e.g. `brain_pipeline` |
| `source_trace_id` | Links to `brain_pipeline_id` when known |
| `category` | `bug`, `test_gap`, `architecture`, `prompt`, `memory`, `dashboard`, `safety`, `performance`, `docs`, `unknown` |
| `title`, `problem_summary`, `proposed_change`, `expected_benefit` | Short text; redacted on read/API |
| `evidence` | Small dict; blocked keys (raw traces) stripped |
| `affected_files` | Paths as strings |
| `risk_level` | `low`, `medium`, `high`, `blocked`, `unknown` |
| `priority_score`, `confidence` | `0.0`–`1.0` |
| `status` | See below |
| `requires_human_review` | Default `true` |
| `blocked_reason` | Optional |
| `tags` | String list |
| `metadata` | Scalar-safe metadata only on persist; API may expose `review_note` from `status_note` |

## Status values

- **Lifecycle:** `proposed` → `reviewing` → `accepted` \| `rejected` \| `deferred` → optionally `implemented`  
- **POST `/status` allowed targets:** `reviewing`, `accepted`, `rejected`, `deferred`, `implemented` (not `proposed`; cannot “reset” via API)

## HTTP API (Elysia `RuntimeAPIServer`)

Base path: `/api/self-improvement/proposals`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/self-improvement/proposals` | List latest proposals (`?limit=`, max 200), **sanitized** |
| `GET` | `/api/self-improvement/proposals/<proposal_id>` | One proposal, **sanitized** |
| `POST` | `/api/self-improvement/proposals/<proposal_id>/status` | Update status only |

Body for POST:

```json
{
  "status": "accepted",
  "note": "optional human note"
}
```

These routes do not run implementation, proposals v2 approval flows, or shell.

## Brain trace summary

`GET /api/brain/trace/latest` (via `load_latest_brain_trace_summary`) includes:

- `self_improvement_queued` — from transition marker `self_improvement_enqueued`  
- `self_improvement_proposal_count` — count of canonical proposals whose `source_trace_id` matches the trace’s `brain_pipeline_id`  

Full proposal bodies are **not** embedded in the trace response.

## Using proposals with Cursor / Codex

1. Pull the list or a single id from the API or open the JSONL file.  
2. Treat `proposed_change`, `affected_files`, and `evidence` as **hints** only.  
3. Implement changes in a normal PR / patch workflow; mark the proposal `implemented` in the API when done (optional housekeeping).

## Control panel dashboard

On the **Dashboard** tab (`UIControlPanel`), the **Brain Trace & Self-Improvement** card shows:

- **Latest Brain Trace** — compact fields from `GET /api/brain/trace/latest` (no raw TDA dump).
- **Self-Improvement Proposals** — list from `GET /api/self-improvement/proposals`.

**Refresh:** use **Refresh trace** / **Refresh proposals**, or wait for the dashboard’s ~30s poll alongside other meters.

**Change status:** open **View details**, then use **Reviewing / Accepted / Rejected / Deferred / Implemented**.  
Those buttons call `POST /api/self-improvement/proposals/<id>/status` only.

There is **no** apply-patch, run-command, or autonomy trigger in this UI. Marking a proposal `implemented` is bookkeeping only.

## Diagnostics

Read-only script (no mutations beyond what you do manually elsewhere):

```text
python scripts/self_improvement_queue_diagnostic.py
```

Prints canonical path/count, legacy file presence/count, whether legacy dual-write is enabled, status breakdown, top proposals by priority, and a short migration note. It does **not** apply patches or migrate rows automatically.
