# Elysia Genesis Archive

The Genesis Archive preserves the recoverable historical development of Elysia / Project Guardian as source history for the Elysia Collective.

## Rules

1. Genesis records are append-only historical artifacts. Later agents may annotate or challenge them, but should not silently rewrite the original record.
2. Every entry must distinguish among:
   - **USER_DECISION**: an explicit user-selected principle, requirement, or direction.
   - **IMPLEMENTED**: code or repository structure known to have existed.
   - **PROPOSED**: an idea discussed but not yet verified as implemented.
   - **REPOSITORY_EVIDENCE**: a claim grounded in inspected repository code/logs/backups at a recorded path/blob/commit.
   - **RECOVERED_SUMMARY**: a historical fact recovered from conversation context where the raw transcript has not yet been imported.
   - **INTERPRETATION**: a conclusion drawn from evidence that is not itself a direct source statement.
3. Raw conversations, when later available, outrank summaries. A raw-source import should be linked to the corresponding recovered-summary entry rather than replacing it.
4. Repository evidence establishes what a file/log recorded at the inspected version; it does not automatically prove which version was active at runtime unless boot-path/runtime provenance is also verified.
5. Uncertainty, contradictions, and unresolved questions are preserved explicitly.
6. Unrelated personal information must not be imported simply because it appears in the same ChatGPT account.
7. Material from outside contributors must be kept separate from the private Genesis archive unless deliberately published or imported.

## Current provenance level

The first chronology is a **recovered summary layer**, assembled from available historical conversation context plus the current GitHub repository. It is not yet a complete raw transcript archive.

Repository-backed bounded tranches may be added when sufficiently strong primary artifacts exist even before the conversation export is recovered. These tranches must preserve exact paths/hashes where practical and clearly separate evidence from interpretation.

## Bounded tranches

- `tranches/2025-05_dream_mutation_loop.md` — repository-backed reconstruction of the May 2025 DreamEngine → MutationEngine loop, early self-improvement controls, recorded mutation events, later Guardian formalization, failure modes, and unresolved provenance questions.
- `tranches/2024-12_to_2026-09_identity_governance_collective_turn.md` — recovered and repository-backed reconstruction of the identity/governance concepts that later became the Elysia Collective, including adversarial review and unresolved continuity questions.
- `tranches/2026-04_to_2026-09_memory_continuity_provenance_lineage.md` — reconstruction of Guardian memory/persona continuity evolving toward immutable Genesis provenance, lineage, contradiction preservation, and layered Collective memory.
- `tranches/2026-04_to_2026-09_capability_realism_bounded_tools.md` — repository-backed reconstruction of tool discovery evolving into operational capability awareness, bounded browser/execution surfaces, and staged capability adoption with explicit governance.

## Highest-priority primary-source recovery

When the user's local Guardian archive and selected ChatGPT export/project material are available, reconcile this archive against:

1. original AI Constitution / Elysia Covenant drafts and version history;
2. December 2024 Elysia/Erebus founding conversations;
3. January 2025 Python-core conversations/code;
4. April–May 2025 Constitution, DreamEngine, MutationEngine, Meta-Agent, Rebuild Manifest, and modular-architecture conversations;
5. local Guardian project versions not present on GitHub;
6. later ChatGPT Project/export conversations containing implementation and governance decisions.

Do not overwrite earlier Genesis entries during reconciliation. Attach primary-source links, corrections, confidence changes, and supersession relationships so the history of recovery itself remains auditable.