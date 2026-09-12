# Preliminary Guardian Implementation Gap Audit

This audit is based on the GitHub baseline only. It must be reconciled against the user's local Guardian ZIP before fixes are implemented.

## Priority 1: Historical chat ingestion is present but incomplete for Genesis use

Evidence found:
- `scripts/import_chatgpt_export.py` parses ChatGPT export JSON, extracts user/assistant messages, sorts by timestamp, and writes text chatlogs.
- The current Collective requires richer provenance, exact source linkage, original titles/metadata, content hashing, scope filtering, and contradiction-aware extraction.

Action after ZIP reconciliation:
- keep the existing importer as raw ingestion if still current;
- add a v2 provenance adapter rather than silently changing historical behavior;
- test on a small verified Elysia conversation set first.

## Priority 2: Capability discovery should be connected to existing CapabilityRegistry

Evidence found:
- Guardian already contains a structured `CapabilityRegistry` with runtime snapshots, usage/outcome logs, API budgets, relevance scoring, usefulness/cost/risk candidates, and capability summaries.

Action after ZIP reconciliation:
- add a disabled adapter from `capability_candidate_schema.json` into the existing registry;
- do not build a second capability database unless the local implementation requires it.

## Priority 3: Introspection/control-panel claims may exceed implementation

Repository documentation states that some introspection features were placeholders and returned dummy data.

Action after ZIP reconciliation:
- verify the current introspection endpoints against implementation and tests;
- mark UI surfaces as live, partial, simulated, or stale;
- Collective self-model must never consume dummy status as factual runtime state.

## Priority 4: WebScout has multiple generations and historical placeholder paths

Evidence found:
- a current/recent WebScout agent implementation exists;
- older files and feed-generation paths explicitly describe placeholder task-queue behavior, placeholder architecture generation, and formerly fake/placeholder research sources;
- later web-reading documentation describes replacing fake sources with real page fetching.

Action after ZIP reconciliation:
- identify the single live WebScout path;
- quarantine/deprecate old placeholder implementations from capability discovery;
- require source provenance for Researcher evidence packets.

## Priority 5: AI tool adapter creation has historical stubs

Evidence found in older comprehensive-core code:
- generated adapter code contains `# TODO: Implement adapter logic` followed by `pass`.

Action after ZIP reconciliation:
- determine whether this old registry is inactive or still reachable;
- never count generated stub adapters as usable capabilities;
- CapabilityRegistry should distinguish `declared`, `registered`, `tested`, and `operational`.

## Priority 6: Generic implementer may generate TODO-only files

Evidence found:
- `project_guardian/implementer/codegen_client.py` can create missing target files containing `# TODO: Implement ...` placeholders.

Action after ZIP reconciliation:
- ensure automated evaluation does not interpret file existence as implementation success;
- implementation scoring should require tests, executable behavior, or explicit `stub` status.

## Priority 7: External connectors were historically intended to be trust-supervised

Repository documentation contains an explicit historical TODO to add rate-limited external connectors under TrustEngine supervision.

Action after ZIP reconciliation:
- map current connectors/browser/tool surfaces to TrustEngine and the AI Constitution;
- any new external capability from Capability Watch should enter through minimum-permission, rate-limited adapters with provenance and human approval where consequential.

## Priority 8: Consensus and collective truth must remain separate

Guardian's ConsensusEngine is useful for organizational decisions, but the Collective design must prevent a weighted vote from automatically promoting unsupported claims to truth.

Action:
- keep evidence status in cognitive packets;
- use consensus for choices such as routing, experiment selection, or proposal approval;
- use provenance, evidence, replication, and Erebus review for epistemic status.

## Priority 9: Multiple historical trees may create false duplication

The repo includes `project_guardian/`, `elysia/`, `core_modules/`, backups, `old modules/`, proposals, and generated documentation.

Action after ZIP reconciliation:
- build a boot-path graph from actual imports and startup scripts;
- classify each module as `LIVE`, `OPTIONAL`, `LEGACY`, `BACKUP`, `PROPOSAL`, `GENERATED`, or `UNKNOWN`;
- only live/optional tested modules should enter the Collective capability map.

## Immediate no-ZIP-safe work

Safe to continue now:
- Genesis source schema and chronology;
- AI Constitution integration gate;
- Collective state/continuity model;
- cognitive packet protocol;
- agent contracts/prompts;
- federation protocol;
- capability candidate schema/intake protocol;
- deterministic dry-run tests;
- experiment metrics and benchmarks.

Blocked until ZIP/current runtime verification:
- modifying boot/orchestrator paths;
- changing MemoryCore persistence;
- replacing ConsensusEngine/DreamEngine;
- enabling model calls for founding agents;
- enabling external write actions;
- merging Collective branches to main.
