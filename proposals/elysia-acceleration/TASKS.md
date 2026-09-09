# Elysia acceleration — task checklist

**Artifacts added (this pass):** `README.md`, `OPERATOR_NOTES.md`, `AUDIT_PARALLEL.md`, `ROUTING_FALLBACK_MATRIX.md`, `replay_prompts.jsonl`, `replay_runs.md`, `scripts/elysia_selfbuild_operator.py`, `scripts/run_replay_prompts.py`.

Context: speed up the loop *experience → corpus → embeddings → RAG inject → measurable quality*, and reconnect **parallel AI** paths where they still exist but may be unwired or underused.

Parallel code still in tree (audit first, then fix gaps):

- `project_guardian/orchestration/pipelines/parallel.py` — `ParallelCompareAndJudgePipeline` (`parallel_compare_and_judge`)
- `project_guardian/orchestration/router/rules.py` — when `pipeline = parallel_compare_and_judge`
- `elysia.py` — `ThreadPoolExecutor` for parallel memory condensation chunks
- Tests: `project_guardian/tests/test_orchestration_parallel.py`, `test_router_telemetry_adapt.py` (parallel escalation / revert)

---

## Task 1 — Tighten the learning loop

- [x] Document or script the **auto-learning cadence** you want (interval + manual trigger). → `OPERATOR_NOTES.md` + `elysia_selfbuild_operator.py status` shows `interval_hours`.
- [ ] Align `local_ai_selfbuild_rag_export_each_run` / `local_ai_selfbuild_embed_each_run` with **Ollama + disk** capacity so embeddings stay fresh without backlog. *(You set flags; notes in OPERATOR_NOTES.)*
- [x] Add one **operator note** (comment in `config/auto_learning.json` or short README section) describing “when corpus updates vs when index updates.” → `OPERATOR_NOTES.md` table.

**Done when:** After a normal day of use, `rag_chunks_latest.jsonl` and `chunk_embeddings.f32.bin` are not stale relative to new admitted rows (define “stale” as you prefer, e.g. under 24h or same session).

---

## Task 2 — Make retrieval trustworthy faster

- [ ] Use **`meta["selfbuild_rag"]`** (and `[UnifiedLLM] selfbuild_rag` logs) on ~10 real turns; record skips vs applies.
- [ ] Tune **one knob at a time**: `local_ai_selfbuild_rag_inject_min_score`, then `top_k`, then `max_chars`.
- [ ] If `skip=query_embed_empty` or `missing_artifacts` dominates, fix **model pull / paths** before changing scores.

**Done when:** You have a short note (bullet list) of final values and why, and empty-inject rate matches intent.

---

## Task 3 — Deliberate practice (replay pack)

- [x] Create a **small fixed prompt set** (3–10 prompts) covering planning, summarization, and one Guardian-specific task. → `replay_prompts.jsonl` + `run_replay_prompts.py`.
- [ ] Run the pack **weekly** (or on demand script); capture `selfbuild_rag` meta + answer quality notes.
- [x] Optional: store replay transcripts under `learned/` or a `replay_logs/` folder for diff over time. → `replay_runs.md` (append rows; move under `learned/` if you prefer).

**Done when:** Replay pack exists in repo or your notes, and at least one baseline run is recorded.

---

## Task 4 — Operator leverage (visibility + safety)

- [x] Single place to see **last turn** `selfbuild_rag` (debug panel, log tail helper, or small CLI). → `python scripts/elysia_selfbuild_operator.py last-rag` (scans `elysia_unified.log` + external mirror); `status` lists candidate log paths.
- [x] One action to **backup** `learned/.../local_ai_selfbuild/` (zip or copy script). → `python scripts/elysia_selfbuild_operator.py backup [--dest …]`.
- [ ] Optional: thin **toggle** UI or script for inject/embed without hand-editing JSON every time.

**Done when:** You can answer “did RAG run last chat?” in under 30 seconds without spelunking.

---

## Task 5 — Parallel “brains” (routing + capacity)

- [ ] Confirm **local models are pulled** and timeouts in config match your hardware.
- [ ] When cloud is blocked, verify **unified route** still completes locally and learning hooks still run where intended.
- [ ] Map which **modules** still call cloud-only paths without local fallback. → Start from `ROUTING_FALLBACK_MATRIX.md`.

**Done when:** Short matrix: task type × provider × fallback behavior, filled from code or runtime checks.

---

## Task 6 — Mission clarity (corpus quality)

- [ ] Write **3–5 standing missions** in plain language (e.g. home lab, creative, Project Guardian dev). → Template in `OPERATOR_NOTES.md`.
- [ ] Align `local_ai_selfbuild_topics` / `local_ai_selfbuild_keywords` (and min relevance) so self-build admits **high-signal** rows.
- [ ] Prune or archive noisy corpus periods if needed (after backup). → Run `backup` before pruning.

**Done when:** Topics/keywords match missions; you can skim new `local_ai_selfbuild` rows and mostly agree they belong.

---

## Task 7 — Parallel AI processing (audit + wire-up)

- [x] Trace **orchestration router** from a real `TaskRequest` to `RouteDecision.pipeline` — confirm `parallel_compare_and_judge` is still reachable under the rules you care about (critique, governance, telemetry escalation tests). → `AUDIT_PARALLEL.md`.
- [ ] If parallel is **never selected** in production config, document why or restore conditions in `rules.py` / decider config. *(Compare your `config/llm_router.yaml` to defaults.)*
- [x] Review **`elysia.py` memory condensation** parallel chunk path: `max_workers`, error handling, and whether it still matches current memory layout. → `AUDIT_PARALLEL.md` § memory.
- [x] Add or refresh **one integration test** or manual checklist: “force parallel pipeline → two branches → judge picks one.” → Existing tests listed in `AUDIT_PARALLEL.md`; run pytest on those files when touching router.

**Done when:** You can demonstrate one end-to-end parallel path in dev (or document blockers with file/line references).

---

## Suggested order

1. Task 7 (audit) — rediscover what parallel still does today.  
2. Task 4 — visibility makes every other task faster.  
3. Tasks 1 → 2 → 6 — corpus and retrieval in lockstep.  
4. Task 5 — resilience.  
5. Task 3 — compounding quality over calendar time.
