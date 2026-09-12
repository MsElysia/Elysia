# Genesis Tranche — Governance from Trust Scores to Review, Replay, and Preflight

## Scope

This bounded tranche reconstructs a specific Project Guardian design transition: moving from simple trust-gated actions toward a durable control plane built around explicit decision semantics, human review, context-bound approval replay, atomic state updates, and all-or-nothing mutation preflight.

It is intentionally narrower than the earlier DreamEngine/MutationEngine tranche. That earlier tranche covers the emergence of self-improvement and code mutation. This tranche focuses on how Guardian later constrained consequential actions so that approval became explicit, auditable, and difficult to reuse outside its original context.

## Provenance status

### REPOSITORY_EVIDENCE

The task specifications and changelog for TASK-0012 through TASK-0024 exist in the repository and were already present in the repository's initial Git commit:

- commit `cf3462f69edc555bd023137cddd9df8db1482759`
- commit date: 2026-04-05
- commit message: `Initial commit: Project Guardian / Elysia`

This establishes that the design sequence documented below existed in repository form by April 5, 2026. It does **not** establish the exact dates on which each numbered task was first conceived or executed. The internal task numbering provides design/order evidence, not a guaranteed wall-clock chronology.

The later Evolvable AI safety framework was added in:

- commit `649951c692d54d3befaccff546e0a95dcc9d4676`
- commit date: 2026-05-10
- commit message: `Add evolvable AI safety framework`

### UNVERIFIED

The raw conversations that originally motivated TASK-0012 through TASK-0024 have not been recovered for this tranche. Any claim about the user's exact wording, philosophical intent, or the precise date of the underlying conversations remains unverified.

## Repository evidence

### 1. Review became a third state, not a disguised deny

`TASKS/TASK-0012.md` defines a control-plane change for actions whose trust decision is `review`.

Instead of hard failing, Guardian should:

1. create a durable `ReviewRequest`;
2. append it to a file-backed `ReviewQueue`;
3. stop the action by raising `TrustReviewRequiredError`;
4. allow later replay only after an approval record exists;
5. verify that the approval still matches the exact action context.

The task explicitly states that approving one thing must not authorize a modified action.

This is materially different from a simple trust threshold. The design separates:

- `allow` — proceed;
- `deny` — refuse;
- `review` — halt, preserve context, and wait for an external governance decision.

### 2. Approval was designed as contextual authority, not a bearer token

`TASKS/TASK-0012.md` and later `SPEC_MODULES/mutation.md` require replay approvals to match the action context.

For mutation approval, relevant context includes items such as:

- sorted `touched_paths`;
- override flag;
- caller identity;
- task ID.

`SPEC_MODULES/mutation.md` requires exact context matching before an approved request can bypass review. A different path, caller, or task ID does not match.

This means an approval ID is not intended to be authority by itself. Authority is the combination of:

- a known review request;
- a recorded approval;
- and unchanged reviewed context.

That principle later reappears in the Evolvable AI safety framework, which states that `request_id`, `review_id`, and `approval_id` are not trusted by themselves. Approval must belong to the correct review type and still match the current target, action, metadata, and artifact fingerprint.

### 3. Durable governance state introduced crash and race risks

`TASKS/TASK-0015.md` identifies a second-order safety problem: once review and approval are persisted, corrupted control-plane state becomes a governance risk.

The task therefore requires:

- atomic writes using temporary files plus `os.replace()`;
- latest-state semantics for append-only review records;
- atomic ApprovalStore writes;
- explicit documentation of the single-writer assumption when stronger locking is unavailable;
- UI redaction on copied context rather than mutation of the authoritative context;
- normalized action constants so policy decisions are not split by string mismatches.

This is significant because the safety problem shifted from only "should this action run?" to also "can the evidence and state used to decide that question survive crashes, concurrency, UI handling, and naming inconsistencies?"

### 4. Mutation became a governed transaction rather than a free-form helper

`TASKS/TASK-0019.md` and `SPEC_MODULES/mutation.md` formalize MutationEngine as the sole code-mutation surface.

The design requires:

- explicit `MutationDeniedError`, `MutationReviewRequiredError`, and `MutationApplyError` exceptions;
- structured `MutationResult` success data instead of parsing strings;
- removal or disabling of direct GPT/network review paths that bypass governance;
- decision-aware handling of `TrustDecision` rather than treating it as a truthy object;
- ReviewQueue and ApprovalStore integration for governance mutation overrides;
- protected governance paths;
- deterministic approval context;
- backups before writes.

The spec later states that MutationEngine must never perform direct network calls and must not bypass the approved gateway/control surfaces.

### 5. Preflight introduced an all-or-nothing mutation guarantee

The changelog and `SPEC_MODULES/mutation.md` document the later `APPLY_MUTATION` preflight rule.

Before any mutation batch writes occur, Guardian should:

1. validate every target path;
2. determine whether protected governance files are involved;
3. perform the TrustMatrix/replay decision for the batch;
4. reject the entire batch before writing if any target fails.

The documented invariant is that no partial mutation should occur because one file was written before a later file was denied.

This is a transaction-like safety idea: authorization is evaluated over the intended change set before side effects begin.

### 6. The same governance pattern expanded beyond mutation

The repository changelog shows the same review/replay pattern being applied across:

- WebReader/network access;
- FileWriter;
- SubprocessRunner;
- governance mutations;
- task execution.

The design converges on a single control grammar:

`ALLOW / DENY / REVIEW -> durable request -> human approval -> context-bound replay`

rather than giving every tool its own unrelated approval semantics.

## May 2026 extension: Evolvable AI safety

`docs/EAI_SAFETY_FRAMEWORK.md`, added May 10, 2026, extends the same governance pattern to a broader evolvable-AI risk model.

The framework explicitly treats risk as control over three levers:

- reproduction;
- variation;
- deployment.

It states that the implementation should **not create an evolution loop**. Instead, it should gate existing mutation, module creation, and slave/deployment surfaces.

Important extensions include:

- human approval or controlled-evolution markers for replication/deployment;
- lineage tracking for generated artifacts and variants;
- audit events for real runtime assessments;
- dry-run assessments that do not register lineage or deploy anything;
- review requests created from REVIEW/DENY assessments;
- alerts that are informational rather than authoritative;
- separation between alert acknowledgement and immutable audit history;
- context and artifact-fingerprint verification before an approval is accepted.

## INTERPRETATION

The repository evidence supports a broader architectural interpretation:

Guardian's governance model evolved from **scalar trust** toward **capability-specific, evidence-preserving authority**.

The important transition was not simply adding a human "approve" button. It was making approval narrow and testable:

- the request is durable;
- the context is preserved;
- the approval is attached to that context;
- replay is checked rather than assumed;
- mutations are preflighted before writes;
- consequential surfaces use a shared decision grammar;
- runtime safety evidence is append-only rather than silently overwritten.

This architecture treats authority as something that should be **bound to the exact proposed action**, not something an agent possesses globally once it has been trusted once.

That principle is strongly consistent with later Elysia Collective work on exact-SHA verification, claim-pinned evidence, human-governance gates, and preventing a PASS or approval from silently transferring to a changed product or lineage. The later systems should be viewed as an extension of the same architectural instinct, but that continuity is an interpretation unless a primary historical source explicitly states it.

## Contradictions and tensions preserved

### Trust autonomy vs human authority

Guardian contains machinery for trust-based autonomous decisions, while the review/replay design deliberately interrupts autonomy at consequential boundaries.

This is not necessarily a contradiction. It may reflect a layered goal:

- autonomous operation for bounded low-risk actions;
- explicit human authority for uncertain or high-impact actions.

The exact intended threshold between those layers remains unresolved without the original design conversations.

### Approval replay vs changing world state

Context hashing protects against obvious approval reuse, but matching request context does not prove that external conditions are unchanged.

An approval can remain context-identical while the environment has changed. This suggests a future distinction between:

- identity/context validity;
- freshness/expiry validity;
- external-state validity.

The repository evidence inspected here does not establish whether all later approval paths implemented expiry or external-state revalidation.

### Append-only history vs operational corrections

ReviewQueue uses append-only/latest-state semantics, preserving earlier states while using the newest state operationally. This is compatible with Genesis-style history preservation, but it creates a general design question:

Should corrections supersede prior state operationally while leaving the prior record immutable historically?

Later Collective memory design appears to answer yes, but the direct historical bridge is still interpretive.

### File-backed governance vs multi-agent concurrency

TASK-0015 explicitly retains a single-writer assumption when stronger locking is unavailable. That is sufficient for a bounded local control plane but may become inadequate under concurrent multi-agent execution.

This is a concrete historical limit that should not be erased when documenting later distributed/autopilot designs.

## Unresolved questions

1. What original conversation or user decision first introduced the three-way `allow / deny / review` model?
2. Was context-bound replay explicitly motivated by a prior approval-reuse failure, or was it designed preventively?
3. Which TASK-0012–TASK-0024 behaviors were actually exercised in the historical runtime versus only specified/tested in repository form?
4. When did human approval become a philosophical governance principle rather than only an engineering safety mechanism?
5. Did the later Evolvable AI framework derive directly from the earlier ReviewQueue/ApprovalStore architecture, or were they independently convergent designs?
6. Which approval surfaces currently enforce freshness/expiry in addition to context identity?
7. How should the historical single-writer assumption be superseded in a multi-agent runtime without losing append-only provenance?
8. Where should the line be drawn between autonomous low-risk approval and constitutionally reserved human authority?

## Primary sources to recover next

Highest-value missing sources for this thread:

1. original conversations corresponding to TASK-0009 through TASK-0024;
2. discussions that introduced TrustDecision's `allow / deny / review` semantics;
3. discussions around ReviewQueue and ApprovalStore replay protection;
4. conversations around the May 2026 Evolvable AI safety framework;
5. any original Constitution/Covenant clauses governing self-modification, replication, human approval, or irreversible actions.

Until those sources are recovered, repository evidence proves the architecture existed, but not the exact philosophical language or complete historical causality behind it.

## Source index

Repository sources inspected for this tranche:

- `TASKS/TASK-0012.md`
- `TASKS/TASK-0015.md`
- `TASKS/TASK-0019.md`
- `SPEC_MODULES/mutation.md`
- `CHANGELOG.md`
- `docs/EAI_SAFETY_FRAMEWORK.md`
- Git history for `TASKS/TASK-0012.md`: initial commit `cf3462f69edc555bd023137cddd9df8db1482759`, 2026-04-05
- Git history for `docs/EAI_SAFETY_FRAMEWORK.md`: commit `649951c692d54d3befaccff546e0a95dcc9d4676`, 2026-05-10
