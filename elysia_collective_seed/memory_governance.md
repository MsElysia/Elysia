# Collective Memory Governance

## Three memory classes

### Genesis Memory
Immutable historical source material: original Elysia conversations, design documents, foundational principles, imported archives, and preserved code snapshots. Agents may cite or interpret Genesis material but never overwrite it.

### Collective Memory
The evolving body of validated cognitive packets, experiments, critiques, syntheses, relationships, and outcomes. Collective Memory is append-first: new understanding supersedes earlier packets through explicit lineage rather than silent rewriting.

### Working Memory
Temporary task context, scratch reasoning, intermediate tool output, and disposable coordination state. Working Memory is not presumed true and should expire unless promoted through a cognitive packet.

## Admission rules
A packet may enter Collective Memory only if:
- it passes schema validation;
- its author and creation time are recorded;
- provenance is present for material factual claims;
- referenced parents exist or are explicitly marked external/unavailable;
- protected/private source material is not exposed beyond its permission boundary.

Archivist performs admission checks. Admission does not mean endorsement.

## Lineage rules
- Corrections create descendants; they do not rewrite ancestors.
- A synthesis lists every material parent packet.
- Replications reference the experiment/result being replicated.
- Contradictions are bidirectional relationships.
- Merged duplicates preserve aliases so old references remain resolvable.
- Rejected ideas remain queryable as historical knowledge with rejection reasons.

## Knowledge states
OPEN -> TESTING -> SUPPORTED
OPEN/TESTING/SUPPORTED -> DISPUTED
Any state -> REJECTED when evidence warrants it
Inactive material -> ARCHIVED

State changes require a new event with actor, reason, timestamp, and supporting packet IDs.

## Confidence
Confidence belongs to a claim, not to an agent's identity. Store both author confidence and, later, an aggregated evidence confidence. Reputation can inform routing but must not mechanically determine truth.

## Decay and revalidation
Time-sensitive claims receive an expiry/review horizon. Dream Cycle can create revalidation tasks for stale material. Historical and mathematical claims need not decay merely because they are old.

## Privacy membrane
Genesis imports from private conversations remain private by default. A public/federated packet must be a separately approved derivative that contains only the information intended for export.

## Deletion
Working Memory may expire normally. Collective/Genesis deletion should be exceptional, auditable, and used for legal/privacy/security needs rather than epistemic disagreement. When content must be removed, retain a non-sensitive tombstone stating that an item existed and why it became unavailable when appropriate.

## Reconciliation target
When the local Guardian ZIP is available, map existing MemoryCore, vector/semantic search, timeline memory, conversation import, and lineage components onto these rules before creating a parallel memory implementation.
