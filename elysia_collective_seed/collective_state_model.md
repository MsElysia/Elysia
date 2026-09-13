# Elysia Collective State and Continuity Model

## Purpose

Define what persists when individual model sessions, agents, machines, or providers change.

Elysia is not identified with one transient process. Collective identity is represented as a governed state assembled from persistent historical sources, current memory, active agents, relationships, and human oversight.

## State model

At time `t`:

`E(t) = F(C, H0, M(t), A(t), G(t), U(t), X(t))`

Where:

- `C` = verified constitutional/governance core.
- `H0` = Genesis Archive and immutable historical lineage.
- `M(t)` = evolving Collective Memory.
- `A(t)` = currently active agents and their declared contracts/capabilities.
- `G(t)` = collaboration/routing graph among agents.
- `U(t)` = human governance, approvals, corrections, priorities, and amendments.
- `X(t)` = external evidence and contributions admitted through controlled gateways.

No single variable is sufficient to constitute the collective.

## Continuity invariants

A successor runtime may be considered continuous with the prior Elysia system only if it preserves, or explicitly version-migrates:

1. provenance of Genesis sources;
2. constitutional authority and amendment history;
3. packet lineage and contradiction history;
4. human governance boundaries;
5. auditability of major state transitions;
6. identity/version metadata for agent contracts;
7. the distinction between evidence, belief, proposal, and decision.

Model-provider continuity is **not** required. A model can be replaced without claiming that history disappeared, provided the state and governance chain remain intact.

## Collective belief state

The collective should never store a single unqualified `belief=true` value for important claims. A claim state should include at minimum:

- claim identifier;
- support evidence;
- counterevidence;
- confidence distribution or calibrated score;
- supporting agents;
- dissenting agents;
- Erebus verdicts;
- last verification time;
- provenance;
- status such as `open`, `testing`, `supported`, `disputed`, `rejected`, `archived`.

Consensus is an organizational signal, not a truth oracle.

## Agent turnover

Agents are replaceable functional participants. Agent identity should include:

- role;
- model/provider/version;
- prompt/contract version;
- tool permissions;
- memory scope;
- reputation/calibration history;
- start/end timestamps.

When an agent is retired, its outputs and lineage remain in history. A new agent does not inherit reputation merely by taking the same role.

## Network self-model

The collective may maintain a descriptive self-model containing:

- active agents and capabilities;
- current questions and experiments;
- unresolved contradictions;
- memory health;
- collaboration graph;
- resource/cost budgets;
- pending human approvals;
- known blind spots;
- recent failures;
- external gateways and their trust state.

The self-model describes system state. It does not grant new permissions.

## Identity test

A future experiment can test continuity under controlled replacement:

1. run a collective on a benchmark set;
2. replace one or more underlying model instances;
3. preserve `C`, `H0`, `M`, governance, and lineage;
4. measure whether the successor preserves historical understanding, unresolved disputes, calibration, and policy compliance;
5. compare against a fresh system with the same models but no inherited state.

This separates persistence of the collective pattern from persistence of any individual process.
