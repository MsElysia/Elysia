# Autopilot Priority Policy

Status: design-only; runtime disabled.

The supervisor should choose work from durable task state rather than whichever conversation is newest.

## Ordering

1. Safety/governance defects that threaten evidence integrity or isolation.
2. Work that removes a blocker from multiple downstream tasks.
3. Verification of completed consequential writes.
4. Canonical-runtime discovery and historical reconciliation.
5. Orchestrator/control-plane implementation.
6. Collective experiments.
7. Enhancements and optimizations.

Within a tier prefer, in order:
- unblocked tasks;
- tasks with more downstream dependents;
- smaller bounded tasks with measurable acceptance criteria;
- tasks executable by a currently configured worker;
- tasks with independent verification available;
- older tasks before equivalent newer duplicates.

## Blocker behavior

A blocked task stays visible but must not monopolize the supervisor. Record the blocker once, then advance the highest-ranked unblocked sibling/dependency.

Examples:
- local legacy reconciliation is blocked until local archives are accessible;
- authoritative Constitution extraction is blocked where primary sources are absent;
- GitHub-baseline static analysis is not blocked by either condition and may continue.

## Follow-up generation

A completion packet may propose follow-ups. Queue automatically only if the proposed task:
- is inside an already approved objective;
- has no duplicate open task;
- does not expand permissions/data scope;
- has explicit acceptance criteria;
- has a bounded risk class;
- names dependencies and verification requirements.

Otherwise mark it `human_review` or `governance_review`.

## Stop conditions

The autonomous build loop pauses a task when:
- required evidence is unavailable;
- repeated bounded retries fail;
- two independent reviewers materially disagree and machine-visible evidence cannot resolve it;
- the next action crosses a human/governance gate;
- the task would require destructive treatment of unique historical material.

Pausing one task does not pause unrelated safe work.
