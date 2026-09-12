# Memory ranking and compression (advisory)

## Canonical package

**Use:** `project_guardian.memory_ranking` (implementation in `memory_ranking/ranking.py`).

**Legacy only:** `project_guardian.brain.memory_ranking` re-exports the same symbols and must not contain separate logic, so older `from project_guardian.brain.memory_ranking import …` continues to work without duplicating types.

Do **not** add a `project_guardian/memory/` package: it would shadow `project_guardian/memory.py` (`MemoryCore`).

This document describes the **advisory** memory ranking layer under `project_guardian.memory_ranking`. It scores memories, ranks them, and emits **compression or archive proposals** without mutating `MemoryCore` or other stores unless you explicitly build a separate executor in the future.

## Scores

Each memory is summarized into sub-scores in `[0, 1]`:

| Field | Meaning |
| --- | --- |
| `relevance_score` | Lexical overlap with the current goal / observation text (neutral if no goal). |
| `recency_score` | Decays with age of `last_used_at` or `created_at`. |
| `frequency_score` | Grows with `access_count` (log-scaled). |
| `confidence_score` | Uses explicit `confidence` when present, otherwise a neutral default. |
| `user_importance_score` | High when `user_marked_important` / strong priority / “user prefers” style cues. |
| `strategic_value_score` | Higher when a `linked_goal` is present. |
| `failure_prevention_score` | Higher when `failure_related` or postmortem-style language is present. |
| `compression_priority` | Higher when value is low and text is long vs `max_raw_memory_chars`. |
| `retention_priority` | Higher when value and user-importance are high. |

The scalar **`memory_value_score`** is a weighted mean of the first seven components using weights from `config/memory_ranking.json`.

## Default weights

See `config/memory_ranking.json` → `memory_ranking.weights`. Defaults:

- relevance 0.25  
- recency 0.10  
- frequency 0.10  
- confidence 0.15  
- user_importance 0.15  
- strategic_value 0.15  
- failure_prevention 0.10  

## Why dry-run is default

`memory_ranking.enabled` defaults to **false** and `dry_run` defaults to **true** so ranking never changes production behavior until you deliberately enable it. Proposals always carry `dry_run: true` for high-value paths; archive/compress actions inherit `cfg.dry_run`.

## Compression proposals

`propose_memory_compression` returns a list of `MemoryCompressionProposal` objects with:

- `action`: `keep_full`, `compress`, `archive`, or `review_manually`  
- `proposed_summary`: deterministic `[compressed] …` text (secrets redacted via `trace_visibility.redact_sensitive`)  
- `risk_of_loss`, `reason`, `original_value_score`  

**Safety:** v1 **never** proposes `delete`. Commitments, deadlines, “user prefers”, “high risk”, and similar strings are routed to **`review_manually`** before any automatic compression.

## Inspecting ranking output

- **Brain trace:** with `context["rank_memory"] = True`, the pipeline adds `run_context["memory_ranking"]` with counts and top scores (never raises).  
- **Lesson metadata:** when `memory_ranking.enabled` is true **or** `rank_memory` is set in the pipeline context, `memory.remember(..., memory_ranking={...})` receives a small metadata dict. Failures in ranking are swallowed.  
- **Read-only API:** `GET /api/memory/ranking/summary` returns a sanitized advisory summary for operator visibility. It reads bounded recent conversation messages when available and reports `enabled`, `dry_run`, `mutation_allowed: false`, `delete_allowed: false`, proposal counts, top ranked previews, and advisory compression/review proposals.
- **Control panel:** the Dashboard shows a **Memory Ranking** panel with a refresh-only action. It does not apply, compress, archive, delete, or mutate memories.
- **Script:** `python scripts/memory_ranking_diagnostic.py` prints config and sample proposals.

The visibility endpoint is intentionally read-only. It does not load raw full traces, call LLMs, scan large memory directories, or expose secrets.
- **Control panel:** Dashboard → **Brain Trace & Self-Improvement** → **Memory Ranking** → **Refresh ranking**. Label: *Read-only advisory ranking. No memory changes are applied.* There are no apply/compress/delete/archive buttons.

## Future live compression

Planned follow-ups (not implemented here):

1. An explicit job that applies proposals to a **copy** of rows, with human approval gates.  
2. Optional LLM refinement via `review_memory_scores_with_llm(..., reviewer=callable)` — still subject to manual-review rules for commitments.  
3. Vector / duplicate-aware features once stable signals exist.

## Import note

Use **`from project_guardian.memory_ranking import …`**. The brain shim **`project_guardian.brain.memory_ranking`** re-exports the same objects. This layout avoids a `memory/` **package** that would shadow **`project_guardian.memory`** (`memory.py` / `MemoryCore`).
