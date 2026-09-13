# Cursor Execution Playbook for Guardian/Elysia Consolidation

## Recommended operating mode

For the local historical archive, use Cursor on the machine that holds the Guardian/Elysia folders or a controlled copy of that machine state.

Prefer this hierarchy:

1. **Local Cursor workspace** for initial inspection and hands-on review.
2. **Self-Hosted My Machines** when a long-running/cloud-controlled Cursor agent needs to execute tools against the local checkout/state.
3. **Isolated worktrees or cloud subagent environments** for code modifications and independent tests.
4. Never give cloud agents unrelated personal folders as workspace roots.

## Workspace layout

Create a parent workspace containing distinct roots rather than mixing files first:

```text
Elysia-Reconciliation-Workspace/
  canonical/          # current Guardian checkout
  legacy-01/          # old folder, read-only copy
  legacy-02/
  legacy-03/
  reconciliation/     # generated inventories, handoffs, task ledger
  archive-staging/    # proposed archive only
```

Keep the original old folders outside the working workspace as untouched backups.

## Long-lived Cursor objective

Use `/goal` when available so the parent agent carries the consolidation objective across many bounded tasks.

Suggested objective:

`Reconcile all supplied legacy Elysia and Project Guardian roots against the canonical Guardian tree without deleting historical source material. Inventory first, classify correspondence, recover unique useful behavior through isolated tested changes, preserve Constitution/Covenant and other Genesis sources exactly, archive superseded material with provenance, and require independent verification after every write task. Use the registered Guardian subagents and maintain the task ledger/handoff packets until the reconciliation queue is exhausted or human review is required.`

If `/goal` is unavailable, use the same text as the persistent parent-agent instruction and keep the ledger as the durable source of truth.

## Parallelism

Good parallel tasks:
- independent legacy-root inventories;
- read-only correspondence analysis of unrelated module families;
- independent verification/testing in isolated copies.

Bad parallel tasks:
- two agents editing the same current module;
- archive moves while consolidation is still changing provenance;
- Constitution extraction and normalization in separate write agents.

Use isolated environments/worktrees whenever multiple write-capable agents run concurrently.

## Relay loop

```text
while goal not complete:
    Relay reads ledger
    Relay selects next ready task
    Relay launches approved specialist
    specialist works
    specialist emits handoff packet
    Relay validates handoff

    if code changed:
        launch Verifier
        if verifier fails:
            return defects to Consolidator
        elif archive required:
            launch Archivist

    update ledger
```

The loop is intentionally task-generative but role-bounded. Agents may discover new tasks. They do not silently grant themselves new authorities.

## First task sequence

- `LEG-0001`: Archaeologist inventories canonical + every legacy root.
- `LEG-0002`: Archaeologist clusters exact duplicates.
- `LEG-0003`: Correspondence Analyst reviews same-path-different-content files.
- `LEG-0004`: Correspondence Analyst reviews symbol-overlap families.
- `LEG-0005`: Archaeologist isolates Genesis/governance candidates.
- `LEG-0006`: Archaeologist isolates sensitive/private material from Git candidates.
- `LEG-0007+`: one bounded consolidation task per module family.

Do not start with deletion tasks.

## Completion definition

The reconciliation goal is complete only when every inventoried legacy item has one recorded disposition and every recovered code feature has passed independent verification.

Possible final dispositions:
- exact duplicate, retained only in original backup;
- superseded and archived;
- historical/Genesis source preserved;
- useful behavior ported and verified;
- unique module restored as candidate;
- unrelated/private and excluded;
- unresolved, human review required.
