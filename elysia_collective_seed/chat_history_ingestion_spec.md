# Chat History Ingestion Specification

## Existing baseline

Guardian already contains a historical import script at `scripts/import_chatgpt_export.py` that can parse ChatGPT export JSON files, extract user/assistant messages, and save readable text into personal chatlog storage.

That is useful as a raw-ingest stage, but Elysia Collective needs a second stage that preserves more provenance and separates historical source from derived knowledge.

## Pipeline

```text
ChatGPT export ZIP / extracted JSON
                |
                v
          Raw Import Layer
                |
                v
        Conversation Registry
                |
        +-------+-------+
        |               |
        v               v
 Genesis candidate   unrelated/private
 classifier          quarantine/ignore
        |
        v
  Immutable raw source
        |
        v
 Structured extraction
        |
  +-----+------+---------+----------+
  |            |         |          |
 decisions  concepts  implementations  open questions
  |            |         |          |
  +------------+---------+----------+
                |
                v
        Collective packets
```

## Stage 1: Raw import

Preserve the original exported conversation metadata where available:

- conversation ID;
- original title;
- conversation creation/update timestamps;
- message IDs;
- role;
- message timestamps;
- raw text;
- source export filename;
- cryptographic content hash.

Do not use a generated title as a substitute for the original title when the export contains one.

## Stage 2: Scope classifier

A conversation is a Genesis candidate when it materially concerns Elysia, Project Guardian, Erebus, AI governance/constitution, memory/continuity, agent architecture, self-improvement, mutation, dream cycles, distributed/trusted AI networks, or implementation of those systems.

The classifier should prefer false negatives over importing unrelated personal material. Ambiguous conversations enter a `REVIEW` queue rather than Genesis automatically.

## Stage 3: Immutable source store

Selected raw conversations are stored as immutable Genesis sources. Derived summaries must never overwrite them.

Each source receives:

- `genesis_source_id`;
- original conversation ID;
- SHA-256 hash;
- import timestamp;
- source date range;
- privacy classification;
- source format/version.

## Stage 4: Structured extraction

Extractor agents may emit records of these types:

- `USER_DECISION`
- `CONSTITUTIONAL_PRINCIPLE`
- `PROPOSED_ARCHITECTURE`
- `IMPLEMENTED_COMPONENT`
- `REJECTED_DIRECTION`
- `EXPERIMENT`
- `RESULT`
- `OPEN_QUESTION`
- `NAMED_CONCEPT`
- `VERSION_MILESTONE`

Every record must cite the Genesis source and message IDs or exact source offsets.

## Stage 5: Contradiction-aware consolidation

Do not flatten changing decisions into one timeless summary.

Example:

- early conversation proposes rule X;
- later conversation rejects X;
- final design adopts X'.

Store all three events and link them as a lineage. The latest event may be marked current, but historical states remain visible.

## Constitution handling

The existing AI Constitution/Covenant is a special source class. When found:

1. import exact text into Genesis;
2. hash and version it;
3. identify draft/version labels and chronology;
4. do not silently combine different drafts;
5. create a clause index only after source preservation;
6. derive machine governance rules with explicit clause references.

## Existing importer improvements to consider after ZIP reconciliation

The historical importer currently extracts only user/assistant text and sorts by message timestamp. Collective integration should additionally preserve titles, conversation metadata, message IDs, source hashes, and raw JSON references.

Do not modify the historical importer until the local Guardian ZIP is compared. Prefer a new adapter or v2 importer if backward compatibility matters.

## Deduplication

Use at least two levels:

- exact source deduplication by cryptographic hash;
- semantic duplicate detection for derived concepts/packets.

Semantic matches should link records rather than deleting historical source material.

## Privacy boundary

The ingestion system is not authorized to treat an account-wide export as an account-wide Collective memory. Only project-relevant material should cross from raw import into Genesis. Unrelated private conversations remain outside the collective knowledge base.

## First ingestion experiment

When a ChatGPT export or project conversation bundle is available:

1. import 10 known Elysia/Guardian conversations;
2. manually verify chronology and source fidelity;
3. run structured extraction;
4. compare extracted decisions against the user's known history;
5. measure missed decisions, false imports, duplicate concepts, and chronology errors;
6. only then expand to the larger archive.
