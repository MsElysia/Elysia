# Verified capability integration v1

One manual, operator-authorized local labor calculation now runs through the existing calculator, independent mathematical verification, durable audit and the existing queue/objective/value algorithms. This is a computation result, not an external or durable capability effect. The audit itself is persisted separately and explicitly labelled.

## Exact source composition

Base PR173: `f8bbdbc159800b978f9a0ea9dd0b366cf357b1c7`. Generic self-task false-success protections are unchanged. No PR172 code, receipt framework, synthetic-note capability or authorization design is imported.

Calculator source PR168: `4eea564b0de97c124aea7475527e7ab542249ffc:elysia_offline.py`, only `calculate_local` extracted unchanged to `project_guardian/local_calculator.py`. An AST comparison against the exact original source executes in the focused suite; CI explicitly fetches this divergent source commit, never assumes ancestry. Local launcher/model/memory history from PR168 is not combined.

Memory source PR174: `4051ebaabdf1e1f838470912ee6de82d32014ee2`, only `project_guardian/memory.py` and `tests/test_memory_core_persistence.py` imported. Independent review found PR173 memory.py byte-identical to main (blob `a217683daf051b2cb73fb2be889f46ad83ea4c07`), so the port loses no branch-specific memory behavior. Source repaired blob is `b75aa2fc85b802ea306aa1213a9313193461e9ab`. Adaptation: additive `enable_persist_mirror=True` default preserves legacy behavior; this manual lane explicitly sets False to prevent optional USB/other mirror publication. Recording tests prove the lane never invokes the hook.

The exact plan, allowed files, sources, tests and closed gates are in `verified-capability-v1.json`. This is semantic file/function composition, not a divergent-history merge. Independent final-head review is required. No READY_FOR_MERGE_REVIEW or release claim is made by this document.

## Operator path

In an isolated checkout with the existing runner dependencies installed:

```text
python -B scripts/run_verified_calculation.py --workspace <disposable-synthetic-directory> --rate 35.50 --painters 3 --days 2 --hours-per-day 8
```

The trusted terminal displays the exact task, request, capability and inputs. Type the displayed `AUTHORIZE <request-id>` phrase to approve that one request. It returns a verified USD1704 computation. Anything else denies authorization. There is no approval flag, serialized grant, model-generated credential, recurring execution, network request or background service. To reload without executing:

```text
python -B scripts/run_verified_calculation.py --workspace <same-directory> --status
```

The committed test uses this real CLI in a child process, supplies its request-specific phrase via a simulated operator channel, then checks results from another fresh process. It also kills a dispatching child with os._exit(17): restart preserves attempted/partial and never executes again.

## Trusted adapter contract

`OperatorCalculationSession.prepare` creates a frozen, session-owned request. `authorize` uses a trusted host UI callback (the CLI uses terminal input) to mint an opaque, one-use,120-second process-local grant bound by object identity to that request. The UI callback is a host integration boundary, never a model/plugin payload. Only the fixed existing `calculator.labor` binding can be selected. Unsupported selections, copied requests, JSON receipts, forged/expired/other-request grants and grants from an earlier session cannot execute.

Before dispatch the adapter fixes task, request, capability, attempt, inputs/digest and expected result. Independent expected totals use integer-cent arithmetic, not the calculator's AST/Decimal implementation. Only the actual calculator's scalar result can match; success flags, receipt dictionaries, files and unrelated writes cannot supply proof. The host directly invokes the pinned calculator, catches errors/interruption and verifies the specific result. No task-provided expression or path is executed.

A durable attempted checkpoint precedes invocation. Verified completion is returned only after terminal MemoryCore persistence returns exactly True and a new MemoryCore reload matches the full event. Primary failures do not publish success. Request grants never persist or revive. A failed/interrupted attempt requires a new host-prepared request and new operator decision.

## Persistence and existing interfaces

The chosen workspace contains one dedicated `verified-calculations-v1/events.json` journal, written through repaired MemoryCore with timeline, vector and optional mirror publication disabled. An OS advisory lock prevents concurrent cooperative sessions and releases on process death. Linked paths/junctions, root replacement and between-operation changes to the journal are refused, preserving external bytes. This lane never opens operational Guardian memory.

Queue and objective stores gain an additive `in_memory=False` option. The default file-backed behavior remains. In this lane they are recoverable projections of the one primary journal, using their existing enqueue/claim/complete, objective progress and value algorithms. Rebuilding views cannot rerun execution or accumulate duplicate progress. In-memory queue completion suppresses global mission/autonomy callbacks. Task, objective and returned outcome retain the same task/capability/attempt evidence. Partial computation has a partial queue status. The value rule labels independently verified computation as operator_support with score0.5; it does not assert revenue, repaired state or external value.

Existing queue retention still keeps approximately40 completed tasks; the primary audit and outcome history retain their events. No cleanup, consolidation or forget path is invoked. Old MemoryAdapter/core wrappers that ignore persistence Boolean results are outside this positive contract; this adapter requires True and reloads.

## Validation and boundaries

Focused command:

```text
python -B -m pytest --noconftest -q -rs -p no:cacheprovider tests/test_self_task_execution_outcome.py tests/test_memory_core_persistence.py tests/test_verified_local_calculation.py project_guardian/tests/test_lazy_memory.py
```

Precommit native Windows Python3.13.15:74 passed,0failed,0skipped. The suite includes the21 unchanged containment regressions,16 imported persistence regressions,30 new capability cases and7 existing lazy-memory cases. Windows junction refusal provides nonprivileged path coverage; Linux runs the real symlink check. CI runs the same exact-head suite on Windows and Ubuntu Python3.12. Final exact-SHA results and independent replay belong in the delivery evidence, not inferred from this precommit result.

This is an interactive local lane, not authorization of the generic autonomous runner. Existing unsupported self-tasks remain unverified. The integer-cent verifier covers this bounded positive USD labor calculation, not arbitrary symbolic computation or financial advice. No personal source/memory retrieval, paid model, Ollama runtime, external effect, real USB backup, operational Windows pilot or release readiness is tested.

The operator terminal/callback and OS-owned application journal are trusted boundaries. The journal is not cryptographically authenticated against a hostile OS account editing all state. JSON/files do not grant execution authority, but a malicious actor with host-code or arbitrary same-account storage control is outside this in-process contract. No security permission or credential was changed to establish it.

## Rollback and next step

All predecessor/source refs are preserved. Abandon the additive draft to roll back; no source branch/main is modified. If explicitly imported later, revert only the candidate child commit. Keep synthetic journal files for evidence; do not copy them into real memory. Interrupted/failed computations require a new manual request; do not clear persistence fences by hand.

Next: bind one existing approved local-document read through this same host-owned authorization and checkpoint/verification boundary, with independently checked source identity/content and the same negative/restart tests. Do not expand generic autonomy or accept model receipts as authority.
