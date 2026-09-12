# Elysia Collective 0.1 Seed

Experimental design work for a bounded multi-agent collective. This seed layer is intentionally additive and does **not** alter the current Guardian runtime or autonomous deployment behavior.

## Founding agents

- **Elysia** — synthesis and collective-state interpretation
- **Erebus** — adversarial critique and falsification
- **Archivist** — provenance, lineage, and memory integrity
- **Explorer** — hypotheses and unconventional connections
- **Researcher** — evidence gathering and verification
- **Engineer** — bounded implementation proposals and sandbox work

## Core artifacts

- `agent_roles.md` — founding role definitions
- `agent_prompt_pack.py` — machine-readable, runtime-disabled founding prompts
- `cognitive_packet_schema.json` — common cognitive packet format
- `communication_protocol.md` — packet flow and communication rules
- `memory_governance.md` — Genesis / Collective / Working memory rules
- `erebus_review_protocol.md` — adversarial review workflow
- `dream_cycle_spec.md` — collective consolidation/dream cycle
- `routing_attention_spec.md` — routing, attention, diversity, reputation, loop controls
- `federation_protocol.md` / `federation_packet_schema.json` — outside-agent membrane
- `experiment_ec_001.md` / `experiment_metrics.md` — first collective-vs-control experiment
- `current_guardian_mapping.md` — preliminary reuse map to existing Guardian systems

## Governance and continuity

- `constitution_integration_gate.md` — preserves the historical AI Constitution/Covenant as the governance authority; no replacement constitution is created here
- `constitution_clause_mapping_schema.json` — traceable mapping from verified constitutional clauses to machine rules
- `collective_state_model.md` — continuity/identity model across agent and model turnover
- `collective_dashboard_state_schema.json` — machine-readable state for a future collective dashboard

## Historical memory / Genesis

- `genesis_archive/README.md` — Genesis archive rules
- `genesis_archive/recovered_timeline_2024_2026.md` — explicitly non-authoritative recovered-summary chronology
- `genesis_archive/constitution_recovery_index.md` — locator clues for recovering the original Constitution/Covenant and amendment history
- `chat_history_ingestion_spec.md` — provenance-preserving ChatGPT history pipeline design
- `genesis_extraction_record_schema.json` — structured decision/concept/implementation extraction records

## Capability evolution

- `capability_intake_protocol.md` — discovery → verification → proposal → sandbox → adoption lifecycle
- `capability_candidate_schema.json` — machine-readable capability candidates
- `pre_zip_gap_audit.md` — known GitHub-baseline gaps and traps to verify against the local Guardian ZIP

## Experimental branch above this seed

`elysia-collective-dryrun` contains no-network/no-model deterministic tooling including:
- packet-flow dry-run harness;
- lineage/routing tests;
- static AST boot-path analyzer and tests;
- EC-001 collective-lift evaluator and tests.

## Non-negotiable pre-integration gates

1. **DO NOT MERGE TO MAIN** until the user's local Guardian ZIP is reconciled against the GitHub baseline.
2. Do not enable runtime agents from this seed.
3. Do not enable autonomous deployment, external posting, credential access, unrestricted browsing, or autonomous replication.
4. The original AI Constitution/Covenant must be recovered as a verified Genesis source before reconstructed summaries are used for constitutional governance.
5. Prefer extending tested existing Guardian systems over creating parallel replacements.
6. File existence is not proof of capability. Legacy/generated/stub modules must be distinguished from operational boot paths.

## Next integration milestone

After ZIP reconciliation, identify the smallest adapter needed to run EC-001 using the actual current Guardian memory, consensus, dream, agent, capability, and safety infrastructure while preserving human approval boundaries.
