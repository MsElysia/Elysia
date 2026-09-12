# Vega independent v2 admission verification

Verdict: **FAIL**. Confidence: high for the reproduced decision-boundary defect.

Target: `codex/governance-v2-trusted-admission` at exact
`caf735ba44c0d992d7562f3f99cbbb39404c11bc`, based on PR #35
`9ad2d941269650b231d3f3e4f5327266a66f9cb1`. Remote candidate head was
rechecked unchanged before publication. This is a separate child candidate, not
the unchanged PR #35 head. No implementation authorship in this verification.

## Claims and inspection

Read AGENTS.md, #11 checkpoint/handoffs, PR #35 acceptance comments, v2 handoff
and admission specification, admission.py, checkpoint_reference.py, relevant
fixture/test changes and CI command. Tested the public promise that malformed
snapshots and rollback produce a blocked result. Existing v1 tests were adapted
to v2 fields/action names; no weakening identified in the inspected assertions.
This failure report is not exhaustive certification of migration or admission.

## Executable evidence

Isolated detached worktree: `.worktrees/vega-v2-check` at target SHA.
Python: `C:/Users/Owner/guardian-governance-checkpoint-contract/.venv/Scripts/python.exe`
(3.13.15), pytest 9.1.1. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

Required CI-equivalent suite:

```text
python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_autopilot_claim_policy.py --basetemp .vega-baseline2
```

Result: **414 passed**, 4.93 seconds. Includes original lifecycle/falsification,
ledger migration and claim-policy tests. This is local evidence, not GitHub CI.
Initial bundled Python 3.12 attempt had four collection errors because jsonschema
was absent; switching to the existing declared-dependency environment resolved
that environment problem without changing product code or installing packages.

Independent regression:

```text
python -m pytest -q breaker_tests/test_vega_v2_generation.py --basetemp .vega-breaker
```

Result: **4 failed, 2 passed**, 0.19 seconds. `git diff --check` passed.
Tests reuse only the candidate's valid migration fixture, then independently
mutate and JSON-roundtrip the generation. Roundtrip is serialization evidence,
not production persistence/restart proof.

## Reproduction and impact

Take a valid v2 snapshot, set `snapshot_generation` to null, string `"8"`, `[]`,
or `{}`, and invoke `evaluate_admitted` with `minimum_generation=8` and its
matching digest. Expected: `BLOCKED_INVALID_STATE`. Actual: uncaught `TypeError`
from `admission.py:40` comparing malformed generation to integer minimum.
The type/schema check occurs after comparison; the public evaluator catches
AdmissionError only. The four JSON-representable cases all reproduce.

Valid generation retains the active gate, and an older valid generation returns
blocked, even with misleading worker metadata. No authorization bypass was
demonstrated: this is a bounded error-handling/availability defect in the promised
fail-closed diagnostic API, not evidence that a write was authorized.

## Runtime, safety and false-capability assessment

The public normative evaluator is reachable by ordinary function calls and was
executed. It is not connected to scheduler/ledger/Git mutation. No Guardian,
provider, network probe, service or activation path ran. No product changes,
permissions, human release, merge or deployment performed. No broader
FALSE_CAPABILITY finding is asserted: production enforcement and authentication
are explicitly unimplemented. #23/#36 governance gates remain unchanged.

## Bounded Astra repair and handoff

Validate snapshot generation type/schema before arithmetic comparison, and ensure
malformed JSON state returns the documented blocked decision through the public
boundary. Preserve the regression and existing gate/rollback behavior. Do not
add production enforcement, infer human authorization, or expand this repair.
Rerun all 414 existing tests and these six cases on the repaired exact SHA;
obtain exact-head CI and **independent Vega re-verification**.

Erebus question: none needed to reproduce this defect; external write admission
and human trust-anchor decisions remain separate unresolved governance work.
Next test priority after repair: malformed state combined with optional rollback
policy across every public validation/evaluation entry point.

Durable reviewed mapping: `caf735ba44c0d992d7562f3f99cbbb39404c11bc` -> FAIL.
Do not repeat this unchanged finding; rerun on a changed candidate.
