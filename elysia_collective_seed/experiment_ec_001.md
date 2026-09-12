# Experiment EC-001: Collective Memory Architecture

## Research question
Does a six-role Elysia collective produce a better long-term memory architecture than an isolated agent using an equivalent overall compute/token budget?

## Control
One strong agent receives the problem, available Guardian architecture documentation, and a fixed resource budget.

## Collective condition
- Explorer generates candidate architectures.
- Researcher gathers evidence and prior-art considerations.
- Erebus attacks assumptions and proposes falsification tests.
- Archivist retrieves relevant historical material and enforces provenance.
- Engineer produces an implementation design and test plan.
- Elysia synthesizes the collective state, preserving disputes and uncertainty.

## Required outputs
1. Proposed architecture
2. Threat/failure analysis
3. Migration plan from existing Guardian memory systems
4. Test suite proposal
5. Explicit unresolved questions
6. Cognitive packet lineage for all material conclusions

## Evaluation metrics
- factual and architectural correctness
- number and severity of overlooked risks
- implementation feasibility
- useful novelty
- self-correction rate
- cross-role contribution rate
- provenance completeness
- resource cost
- evaluator preference under blinded comparison

## Guardrails
- No autonomous deployment.
- No changes to main/default branch.
- No credential access.
- No irreversible external actions.
- Code changes remain sandboxed until human approval.
- Original Genesis material remains immutable.

## Success criterion
Collective condition should demonstrate repeatable quality lift over the control that is large enough to justify its additional orchestration complexity and cost.
