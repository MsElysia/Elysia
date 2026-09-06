# Routing and Attention System

## Objective
Allocate collective attention to the smallest useful set of agents while preserving independent challenge and avoiding reputation-driven groupthink.

## Capability routing
Each agent advertises capabilities, limits, cost class, tool permissions, and current load. Packets declare `needs` and optional topic/risk metadata. A router selects agents using capability match first, then expected utility, diversity, cost, and load.

## Prototype attention score
Use a transparent starting model rather than a learned black box:

`attention = priority * usefulness * novelty * confidence * urgency_adjustment`

Each term is bounded. This is a routing heuristic, not a truth score. Low-confidence but high-risk contradictions can receive high attention through priority/urgency.

## Diversity requirement
For consequential claims, routing should prefer at least one reviewer whose evidence path or model/provider differs from the originating agent when available. Multiple instances of the same model using the same context are not counted as fully independent confirmation.

## Collaboration graph
Record outcomes for role-to-role and agent-to-agent collaborations. Connections may gain or lose routing preference based on measured results, but:
- no permanent exclusion is based solely on historical score;
- exploration traffic is reserved for less-used combinations;
- Erebus review cannot be routed away because it is inconvenient;
- protected decisions remain subject to human approval.

## Reputation
Maintain multidimensional reputation rather than one global number. Candidate dimensions:
- factual calibration
- useful novelty
- critique precision
- replication success
- implementation quality
- provenance quality
- cost efficiency

Reputation affects routing probability and review depth, not epistemic status by itself.

## Loop protection
Detect and limit:
- agents repeatedly citing packets descended from their own output as independent support;
- popularity cascades;
- endless critique/rebuttal loops;
- one agent family monopolizing assignments;
- packet storms caused by broad broadcasts.

Use hop limits, per-task budgets, lineage checks, duplicate detection, and human escalation for unresolved loops.

## Guardian integration target
Guardian already contains agent registration/weighted consensus concepts and bounded relevance scoring. During reconciliation, reuse compatible registries and metrics while keeping decision voting distinct from evidence routing.
