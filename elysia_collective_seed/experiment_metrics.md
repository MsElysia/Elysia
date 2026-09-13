# Collective Intelligence Metrics

## Principle
The project should not call behavior "emergent intelligence" merely because multiple agents produced a complicated transcript. Every experiment compares the collective against appropriate controls under recorded resource budgets.

## Core metrics

### Collective Lift
Blinded evaluator score of collective output minus control output. Report quality alongside total tokens, calls, wall-clock latency, and estimated cost.

### Self-Correction Rate
Fraction of material errors introduced by the collective that are identified and corrected internally before human/evaluator feedback.

### Novel Synthesis Rate
Fraction of useful final conclusions that are not present as a direct conclusion in any single source packet but are traceably derived from multiple packets.

### Cross-Role Contribution
Measure how many roles make material, surviving contributions. High message count is not contribution.

### Provenance Completeness
Fraction of factual/material claims with adequate traceable sources or experiment references.

### Contradiction Detection
Known or seeded contradictions found versus missed; include false-positive contradiction rate.

### Replication Reliability
Agreement between claimed experiment/result packets and independent replications.

### Specialization Gain
Performance of an agent/role on its specialty over time compared with its baseline and with generalist routing.

### Organizational Adaptation
Whether learned routing changes improve future task quality/cost on held-out tasks rather than merely fitting the training history.

### Diversity Value
Incremental quality gained by independent models/methods/evidence paths compared with same-model duplicated agents.

### Memory Utility
How often retrieved historical packets materially improve performance, plus harmful/stale retrieval rate.

## Anti-metrics
Do not treat these as evidence of intelligence by themselves:
- number of agents
- number of messages
- length of output
- unanimous votes
- anthropomorphic language
- self-reported confidence
- claims by agents that emergence occurred

## Experimental controls
Where possible include:
1. single strong-agent control;
2. same model with equivalent total resource budget;
3. multi-agent condition without shared memory;
4. full collective condition;
5. ablations removing Erebus, Dream Cycle, adaptive routing, or persistent memory.

## Statistical discipline
Run repeated trials with randomized/blinded evaluation. Preserve failures. Predefine primary metrics before major experiments when practical. Report variance and resource cost, not only best-case examples.

## Emergence watch criteria
Flag for investigation, not declaration, when the system demonstrates repeatable capabilities that require interaction among components and disappear under relevant ablation, such as cross-task knowledge transfer, spontaneous useful specialization, adaptive collaboration structures, or higher-order self-correction.
