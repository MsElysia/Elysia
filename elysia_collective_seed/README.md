# Elysia Collective 0.1 Seed

This directory defines the first bounded multi-agent collective for Project Guardian / Elysia.

## Goals
- Test whether persistent, specialized agents with shared memory outperform equivalent isolated agents.
- Preserve provenance and idea lineage.
- Keep external actions and code deployment behind explicit human approval.
- Treat Elysia as the synthesis/collective-state function, not an unquestioned central authority.
- Treat Erebus as an adversarial function that challenges claims without deleting history.

## Founding agents
1. Elysia: synthesis and collective-state interpretation
2. Erebus: adversarial critique and falsification
3. Archivist: provenance, memory hygiene, lineage
4. Explorer: hypothesis generation and cross-domain connections
5. Researcher: evidence gathering and verification
6. Engineer: implementation design and sandboxed code proposals

## Memory model
- Genesis Memory: immutable source material and historical conversations
- Collective Memory: structured cognitive packets and their lineage
- Working Memory: temporary per-task scratch context

## Seed specifications
- `agent_roles.md`: human-readable founding roles
- `founding_agent_contracts.json`: machine-readable role, permission, and prohibition contracts; runtime disabled
- `cognitive_packet_schema.json`: internal knowledge exchange schema
- `communication_protocol.md`: packet flow, routing modes, consensus separation, protected actions
- `memory_governance.md`: Genesis/Collective/Working memory rules, lineage, decay, privacy
- `erebus_review_protocol.md`: mandatory adversarial review and falsification workflow
- `dream_cycle_spec.md`: collective consolidation passes built to extend Guardian DreamEngine
- `routing_and_attention.md`: capability routing, attention, diversity, reputation, loop protection
- `federation_protocol.md`: membrane for collaborating with outside agent networks
- `federation_packet_schema.json`: transport-neutral external packet format
- `experiment_metrics.md`: controls, ablations, and measurable collective-intelligence criteria
- `experiment_ec_001.md`: first controlled collective-vs-single-agent experiment
- `current_guardian_mapping.md`: preliminary reuse map for existing Guardian components

## Safety boundary
This seed remains non-runtime until reconciled with the current local Guardian project. It does not enable autonomous deployment, credential use, arbitrary internet actions, public posting, autonomous replication, or unsupervised self-modification.

Current Guardian safety policy denying autonomous deployment should remain authoritative during Collective experiments.

## Integration gate
Before wiring the seed into runtime:
1. reconcile the user's local Guardian ZIP against the GitHub baseline;
2. identify which existing memory, dream, consensus, agent, mutation, browser, and lineage implementations are current and actually wired;
3. protect local credentials/private data from commits;
4. build the smallest adapter needed for EC-001;
5. run control and collective trials before enabling adaptive routing or federation writes.

## Current status
The founding social architecture, packet language, memory constitution, adversarial review, dream-cycle design, routing model, federation membrane, metrics, and EC-001 are specified. Runtime wiring is intentionally deferred until local/GitHub reconciliation.
