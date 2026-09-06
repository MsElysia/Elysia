# Elysia Capability Discovery Intake Protocol

## Purpose

Turn discoveries from Elysia Capability Watch into structured, testable candidates that can later enter Guardian's existing CapabilityRegistry and Collective roadmap.

A new product feature, plugin, connector, model tool, website integration, agent framework, protocol, or data source is not automatically a capability of Elysia. It becomes a candidate first.

## Intake stages

```text
External capability discovery
          |
          v
      CANDIDATE
          |
   evidence + access check
          |
          v
      VERIFIED
          |
   architecture mapping
          |
          v
      PROPOSED
          |
   Erebus/security review
          |
          v
      SANDBOXED
          |
   measured experiment
          |
     +----+----+
     |         |
     v         v
   ADOPTED   REJECTED
```

## Candidate record

Every discovered capability should record:

- unique candidate ID;
- capability name;
- provider/source;
- discovery date;
- availability status;
- official evidence/source references;
- capability class: model, tool, connector, plugin, protocol, memory, browser, automation, data source, coding, multimodal, compute, or other;
- authentication/access requirements;
- read/write/external-action permissions;
- data exposed to the provider;
- estimated cost/resource requirements;
- expected usefulness;
- estimated risk;
- existing Guardian component it maps to;
- proposed Elysia role or "organ";
- concrete experiment;
- rollback/disable path;
- status.

## Architecture mapping

Before adding new code, ask:

1. Does Guardian already have this function under a different name?
2. Can the capability be exposed through the existing ToolRegistry, CapabilityRegistry, WebScout, bounded browser, agent manager, memory system, or orchestrator?
3. Does it replace an older implementation or complement it?
4. Does adopting it create provider lock-in?
5. Can it be disabled without corrupting Collective state?

Prefer adapters over duplicate subsystems.

## Capability scoring

Guardian already has a CapabilityRegistry that evaluates available capabilities and tracks outcomes/usage. The Collective should reuse that infrastructure where practical.

A candidate's provisional score should consider:

`Value = usefulness * reliability * novelty * interoperability`

and

`Burden = cost + security_risk + privacy_risk + maintenance + lock_in`

These formulas are conceptual until reconciled with Guardian's existing scoring implementation.

High novelty alone is not enough to justify adoption.

## Erebus review

Before any candidate gains write access, external action capability, private-data access, code execution, or credential use, Erebus review must produce:

- abuse/failure cases;
- privacy consequences;
- dependency risks;
- hidden authority escalation;
- prompt-injection/data-poisoning exposure where applicable;
- minimum-permission alternative;
- falsifiable success criteria.

## Experiment discipline

Each candidate should have a bounded experiment. Example:

- hypothesis: capability X improves historical retrieval by 20% over existing retrieval;
- control: current Guardian implementation;
- treatment: Guardian plus X adapter;
- budget: fixed calls/tokens/time;
- measurements: accuracy, coverage, latency, cost, privacy surface, failures;
- rollback: disable adapter and retain prior state.

## Adoption rule

A capability becomes `ADOPTED` only when it creates repeatable value greater than its operational and governance burden.

The Capability Watch may recommend adoption. It may not grant itself permissions or enable the capability autonomously.

## Relationship to Elysia evolution

Capability discovery is treated as environmental adaptation rather than uncontrolled self-modification:

1. environment exposes a new affordance;
2. Elysia detects it;
3. Collective evaluates it;
4. sandbox experiment measures usefulness;
5. human governance approves consequential integration;
6. the capability enters the active phenotype while the historical architecture remains traceable.
