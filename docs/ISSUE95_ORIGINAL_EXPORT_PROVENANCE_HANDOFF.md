# Issue #95: original-export provenance continuation

Status: IMPLEMENTED / LOCAL DRAFT / independent exact-SHA verification pending.
Worker: Codex in ChatGPT Work. No second worker verdict is claimed.
Branch: `codex/issue95-provenance-reprocessing`.
Exact base: PR #100 `bf6c72cf397de2a5ef8d9a0bcaccd86462b0e577`.
Product SHA: resolve this handoff's containing commit with `git rev-parse HEAD`.

## Inspected current state

Read Issue #95 and all seven comments, Issue #11/checkpoints, PR #100 metadata,
ChatGPT ingestion/import, memory intelligence, approved-memory store/search/context,
Brain bridge expansion, related tests, existing preview/apply CLIs and Safe Stack.
Issue #95 v1 is already independently verified at PR #97
`9c35991715eb4160e346ecda286ef73a0ffd7577`; the read-only bridge is verified at
the exact PR #100 base above. Those verified scopes are reused.

The remaining defect addressed here: the normal apply path preserved only rendered
(and possibly truncated) conversation text, not the original export JSON. Preview
bound the input by size only, accepting a same-size content edit.

## Changes

- `project_guardian/local_ingestion/chatgpt_export_ingest.py`: preview hashes exact
  input bytes; apply checks that hash before ingestion writes and derives parsing,
  origin preservation and rendering from the same loaded byte snapshot. Old previews
  without the digest fail closed and require a fresh preview.
- `project_guardian/local_ingestion/memory_intelligence.py`: additive origin linkage
  reuses the existing raw artifact directory. One exact export snapshot is shared
  by its conversation records. Validate origin digest/identity, segment index/ID,
  rendering parameters and exact derived text on query and expansion. Highlight
  expansion also returns `original_raw_source` and `original_source_id`.
- `project_guardian/tests/test_memory_intelligence_ingestion.py`: 16 new cases for
  original bytes through truncation, deleted-input expansion, same-size edits,
  missing legacy preview hashes, malformed/forged origin segments and references,
  modified raw exports, and shared origin artifacts across multiple conversations.
  Existing idempotency test now expects two raw artifacts for one conversation:
  derived text plus original JSON. Existing assertions otherwise retained.
- This handoff records task state and review evidence.

## Additive record example

```json
{
  "origin_source": {
    "source_id": "<source-v1 hash>",
    "source_sha256": "<exact export-byte digest>",
    "source_identity": "conversations.json",
    "raw_source_path": "memory_intelligence/raw_sources/<source-id>.bin",
    "segment": {
      "conversation_index": 0,
      "conversation_id": "conv-memory-intel",
      "max_conversation_chars": 160
    }
  }
}
```

Chunk/highlight offsets continue to refer to the exact rendered-text source.
The original export uses conversation segment linkage, not misleading JSON byte offsets.
Query retains existing machine-readable text/tag/source recall reasons. Canonical
selection, candidate-only proposals and tag provenance retain existing behavior.

## Validation

Python 3.12.14 with pytest 9.1.1; all writes used synthetic/disposable destinations.
Focused command: `python -m pytest -q` with:

- `project_guardian/tests/test_memory_intelligence_ingestion.py`
- `project_guardian/tests/test_chatgpt_export_ingest.py`
- `project_guardian/tests/test_memory_intelligence_brain_bridge.py`
- `project_guardian/tests/test_approved_memory_store.py`
- `project_guardian/tests/test_approved_memory_search.py`
- `project_guardian/tests/test_approved_memory_context.py`
- `project_guardian/tests/test_local_memory_pipeline_smoke.py`

Result: **137 passed**. Safe Stack (`python scripts/run_safe_stack_smoke_tests.py`):
**583 passed**, including the inherited NumPy-blocked production-ingestion breaker.
`git diff --check`: clean.

Normal-path proof used the existing non-test `scripts/preview_chatgpt_export.py`
and `scripts/apply_chatgpt_export.py --apply` in separate subprocesses, twice,
with a synthetic representative ChatGPT mapping export. Input: 4,295 exact bytes,
SHA-256 `a90cde4aff601e2644889db1b496aa586245c76182dbc7ec378e525aacbcd108`.
Rendering was bounded to 160 characters.

Before: zero candidates/intelligence artifacts.
First apply: one candidate, one record, two raw artifacts; three highlights.
Second apply: zero staged, one duplicate candidate, one unchanged intelligence
record; all three intelligence artifacts byte-for-byte unchanged.
After deleting the input file, all three highlights expanded to the exact original
4,295 bytes. Recall reasons included text relevance, tag match and source relation.
The committed multi-conversation proof also establishes one shared origin artifact.

## Boundaries and next limitation

No provider calls, embeddings, autonomy activation, ordinary startup wiring,
live-memory mutation, approved-memory promotion, runtime external writes, permission
changes, merge, deployment or governance release. No GitHub writes were performed.
The branch is local; no remote draft PR or hosted exact-head result is claimed.

Old v1 records remain readable and acquire origin linkage only on explicit reapply
from an available original export; lost originals cannot be reconstructed. Old
preview files must be regenerated. Whole-export preservation can retain conversations
outside a preview limit, so the operator must select an export they intend to preserve.
JSON is reparsed on provenance validation; large-export performance is not established.
This does not add semantic LLM enrichment or compact numeric tags.

Next task: independent exact-SHA falsification of origin/segment linkage, a NumPy-free
CLI run, unchanged candidate-only tags and repeated apply; no broader gate release.
