# Elysia Autopilot Orchestrator

## Goal

Build Project Guardian / Elysia with minimal human intervention by using GitHub and Guardian state as the persistent control plane while multiple replaceable AI workers perform bounded tasks.

The system is intentionally provider-neutral. Codex, Cursor, ChatGPT Work, local models, or future agents may all act as workers if they accept the same task packet and return the same completion packet.

## Core principle

**Persistent project state lives outside any single agent conversation.**

The orchestrator owns:
- task state;
- dependencies;
- retries;
- acceptance criteria;
- branch/PR references;
- review requirements;
- capability routing;
- completion evidence;
- human-approval gates.

Workers are disposable.

## Control-plane layers

```text
Historical chats / local archives / GitHub history
                    |
                    v
             Genesis + Corpus
                    |
                    v
             Project Guardian
                    |
             Task/State Ledger
                    |
        +-----------+------------+
        |           |            |
        v           v            v
      Codex       Cursor      ChatGPT Work
        |           |            |
        +-----------+------------+
                    |
                    v
             Review / Verification
                    |
             accepted project state
                    |
                    v
            next generated tasks
```

## Recommended worker roles

### ChatGPT / Work
Best suited for:
- recovering requirements from conversations/projects/files;
- architecture synthesis;
- research;
- external capability discovery;
- governance/Constitution mapping;
- high-level task generation and prioritization;
- cross-source reconciliation.

### Codex
Best suited for:
- substantial repository changes;
- isolated worktree implementation;
- tests and refactors;
- long-running coding tasks;
- PR review loops;
- recurring/scheduled engineering work;
- independent code/security review.

### Cursor
Best suited for:
- local-machine archaeology against historical folders;
- local builds/debugging where machine state matters;
- parallel specialized subagents;
- Cloud Agent implementation;
- IDE-visible development and verification;
- local/Cloud Agent execution via SDK/CLI/My Machines.

### Local models
Optional, later phase. Best suited for cheap/high-volume tasks that do not need frontier reasoning:
- file classification;
- embedding/tagging;
- duplicate detection;
- log triage;
- routing suggestions;
- watchdog/health summaries;
- offline fallback.

Do not make a local model the sole authority over architecture, Constitution, merges, or deployment.

## Task lifecycle

1. `DISCOVER`
   - Genesis miner, capability scout, tests, issue intake, or agent discovers a need.
2. `SPECIFY`
   - create task packet with bounded objective and acceptance criteria.
3. `ROUTE`
   - choose worker based on task class, risk, tool needs, locality, model quality, and cost.
4. `ISOLATE`
   - write work occurs in a branch/worktree/VM.
5. `EXECUTE`
   - worker performs bounded task and records evidence.
6. `VERIFY`
   - independent worker/test suite checks result.
7. `REPAIR`
   - failures create follow-up tasks and retry with bounded attempts.
8. `INTEGRATE`
   - successful low-risk changes may advance to the integration queue; protected actions remain gated.
9. `ARCHIVE`
   - preserve superseded code/history where required.
10. `GENERATE NEXT WORK`
   - completion packet may propose follow-up tasks, but the orchestrator validates dependencies, duplication, risk, and priority before queueing them.

## Autonomous task generation

Workers may propose new tasks, but no worker directly grants itself new authority.

A follow-up task should be automatically accepted only when all are true:
- it advances an existing approved project objective;
- it stays within current repository/data boundaries;
- it does not expand external write/deployment/private-data authority;
- it has measurable acceptance criteria;
- it is not a duplicate of an open task;
- its dependencies are known;
- its risk class is within current autopilot policy.

Otherwise it enters `human_review` or governance review.

## Risk policy

### Fully automatic
- read-only archaeology/research on approved sources;
- documentation;
- tests;
- static analysis;
- code changes in isolated branches/worktrees;
- refactoring with passing tests;
- independent review;
- issue/task creation;
- archival proposals;
- capability experiments in sandboxes.

### Automatic with independent verification
- implementation changes affecting runtime behavior;
- memory schema migrations in test copies;
- agent prompt/contract changes;
- capability adapters;
- dependency upgrades.

### Human/governance gate
- merge to protected production branch while reconciliation gate remains active;
- deployment;
- destructive archival/deletion of unique historical material;
- new external posting/write authority;
- new private-data scope;
- credential/financial authority changes;
- Constitution amendments;
- disabling safety/audit/rollback controls.

## Routing policy

The orchestrator should score workers on:
- required tool access;
- local-files requirement;
- task type;
- model/reasoning need;
- historical success for similar tasks;
- cost;
- latency;
- current availability;
- independence from the worker that produced the code being reviewed.

Example:
- local old-folder comparison -> Cursor local/My Machines Archaeologist;
- broad architectural synthesis -> ChatGPT/Work;
- implement migration + tests -> Codex or Cursor Cloud Agent;
- independent verification -> different model/provider when practical;
- cheap duplicate classification -> local model later.

## Failure handling

A worker failure is not a dead end.

The orchestrator records:
- failure mode;
- tool/model/provider;
- attempted strategy;
- logs/checks;
- whether the task itself is underspecified.

Then it may:
- retry with same worker and extra context;
- route to another worker;
- split the task;
- create a missing-tool/documentation task;
- mark blocked;
- request human review only when machine-visible evidence cannot resolve the ambiguity.

## Completion criterion for the overall project

Autopilot must not declare Elysia "complete" from a README claim. Completion requires a versioned release gate with:
- canonical architecture map;
- reconciled historical archive;
- recovered/verified governance sources;
- reproducible setup;
- passing required test suites;
- security/safety checks;
- successful collective experiments where required;
- operational observability;
- backup/rollback validation;
- documented known limitations;
- explicit release criteria satisfied.

After a release, maintenance tasks may continue, but feature-construction autopilot can enter a lower-intensity maintenance mode.
