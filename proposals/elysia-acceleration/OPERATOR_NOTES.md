# Operator notes — self-build pipeline

## Corpus vs index (what updates when)

| Stage | On disk (under `learned/.../local_ai_selfbuild/`) | When it runs |
|-------|-----------------------------------------------------|--------------|
| Corpus rows | `local_ai_selfbuild_*.jsonl` (manifest / corpus files per corpus module) | Auto-learning admits a row that passes topics + relevance |
| RAG text chunks | `rag_chunks_latest.jsonl` | When `should_run_selfbuild_rag_export` is true (e.g. after new corpus rows, or `local_ai_selfbuild_rag_export_each_run`) |
| Embeddings | `chunk_embeddings_index.jsonl` + `chunk_embeddings.f32.bin` | When `should_run_selfbuild_embed_export` is true and `local_ai_selfbuild_embed_enabled` |

**Rule of thumb:** if inject is empty but corpus grew, you likely need RAG export and/or embed export to run before the next inject.

## Auto-learning cadence (template)

- Default interval is `interval_hours` in `config/auto_learning.json` (often **6**).
- Manual trigger: use whatever path you already use to run auto-learning / Guardian maintenance (same entrypoint as scheduled runs).
- If Ollama is slow, keep `local_ai_selfbuild_embed_each_run` **false** and rely on “corpus changed” gates so you do not embed every idle cycle.

## Tuning `min_score` / `top_k` (Task 2)

1. Run ~10 real chats with inject enabled.
2. After each session: `python scripts/elysia_selfbuild_operator.py last-rag` (or read `meta["selfbuild_rag"]` from your UI).
3. Change **one** of `local_ai_selfbuild_rag_inject_min_score`, `..._top_k`, `..._max_chars`; restart backend; repeat.

Record final values here when stable:

- `min_score`: *(fill)*
- `top_k`: *(fill)*
- `max_chars`: *(fill)*

## Standing missions (Task 6 — fill for your life)

1. *(e.g. Home lab / homelab automation)*
2. *(e.g. Creative writing / worldbuilding)*
3. *(e.g. Project Guardian development)*
4. *(optional)*
5. *(optional)*

Align `local_ai_selfbuild_topics` / keywords in `config/auto_learning.json` with these missions so admitted rows stay high-signal.
