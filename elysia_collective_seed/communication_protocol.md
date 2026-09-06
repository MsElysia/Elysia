# Elysia Collective Communication Protocol

## Purpose
Agents communicate through structured cognitive packets rather than unrestricted all-to-all chat. The protocol is designed to preserve provenance, reduce duplicated reasoning, expose disagreement, and make every material conclusion auditable.

## Core rule
An agent may think privately in Working Memory, but any information intended to influence Collective Memory must be emitted as a valid cognitive packet.

## Packet flow
1. An agent receives a task plus only the packets relevant to its role.
2. It produces zero or more packets.
3. Archivist validates packet structure, lineage references, and provenance.
4. Packets are routed to agents whose capabilities match `needs`, subject, and risk.
5. Material hypotheses and proposals receive Erebus review before being marked supported.
6. Elysia may synthesize packets only after source packet IDs are preserved.
7. Human review is mandatory for protected actions.

## Communication modes
- DIRECTED: one agent requests work from a named role.
- BROADCAST: a packet is eligible for multiple relevant roles, not automatically every agent.
- CHALLENGE: Erebus or another reviewer contests a packet.
- REPLICATION: an agent independently attempts to reproduce a result.
- SYNTHESIS: Elysia combines source packets while preserving dissent.
- ESCALATION: the network asks for human judgment.

## Routing principles
- No default all-to-all messaging.
- Prefer the smallest competent set of agents.
- Independent reviewers should not receive another reviewer's conclusion before forming their initial assessment when blinded evaluation is useful.
- Agent reputation may affect routing priority, but never suppress a qualified dissenting packet solely because its author has lower reputation.
- High-confidence claims with weak provenance are treated as weakly supported.

## Consensus is not truth
Guardian's existing ConsensusEngine may be used to record collective decisions, but voting does not convert a claim into fact. Evidence state and decision state remain separate.

## Protected actions
The following require explicit human approval regardless of agent consensus:
- deployment or modification of a protected/default branch
- credential or secret access beyond an already approved capability
- irreversible external actions
- publishing private Genesis or Collective Memory
- changing safety or approval policy
- enabling autonomous replication or unrestricted external communication

## Failure handling
Malformed packets are rejected to Working Memory with a validation reason. Conflicting packets remain visible. Timeouts, unavailable agents, and minority dissent are recorded rather than silently discarded.
