# Elysia Collective 0.1 Dry Run

This dry run validates the collective protocol without invoking any model, browser, credential, Guardian runtime capability, mutation system, or external action.

## Purpose

Before real agents are connected, prove that the proposed social/cognitive machinery has basic internal coherence:

- packet IDs are unique
- parent lineage only points backward to existing packets
- confidence remains bounded from 0 to 1
- routing is driven by explicit `needs`
- Erebus critique becomes a new packet rather than mutating source history
- Engineer proposals preserve their ancestry
- Elysia synthesis cites the chain it integrates

## Simulated EC-001 lineage

1. Explorer proposes a three-tier/provenance memory principle.
2. Researcher contributes supporting evidence.
3. Erebus identifies recursive-summary drift as a failure mode.
4. Engineer converts the surviving idea into an implementation proposal.
5. Erebus reviews the implementation conditions.
6. Elysia creates a parent-linked synthesis representing the current collective position.

The content is deliberately deterministic. The goal is protocol verification, not intelligence evaluation.

## Run

From the repository root:

```bash
python -m elysia_collective_seed.dry_run_harness
```

Tests:

```bash
pytest -q elysia_collective_seed/test_dry_run.py
```

## Expected properties

A successful run must not require network access or API keys. It should print the packet lineage and each packet's next routing destination. Tests should fail if lineage references a future/nonexistent packet or if confidence falls outside its valid range.

## Integration status

**NOT RUNTIME ENABLED.**

This branch must not be merged into `main` before the local Guardian ZIP is compared with GitHub. After reconciliation, the harness can be adapted to instantiate real bounded agents one role at a time while preserving the same packet contracts and tests.
