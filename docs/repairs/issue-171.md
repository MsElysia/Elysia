# Issue 171 bounded repair

Base: f7cd69d573bc28dc178e8e25e3c87fd8a6abdd83 (PR170), parent 71a9208c5a3bb8ce5df332e48f9435441e9660e6.

A deterministic unrelated thread changes the shared host directory while a different task reports success. The new regression fails on unchanged base production: succeeded instead of partial.

Neither directory snapshot inequality nor payload-selected artifact/digest is accepted as task proof. Independent review rejected an interim expected-file helper because an unrelated writer could still satisfy the same target/content. That helper was removed before publication. No new receipt framework is introduced.

No production capability adapter currently supplies task-bound evidence. The real runner deliberately supplies none: all otherwise successful execution attempts remain partial until a capability-specific trusted adapter is implemented and independently verified. There is no positive integrated execution claim. Planning remains readiness_only/proposed. Queue/objective/value behavior is tested across persistence/reload.

Reuse: quote optional np.ndarray annotation exactly as the historical minimal repair in 5fb6f34da9857adf8d779ee0830304518c87706e (PR86). No divergent branch merge. Runner test import no longer skips; CI declares import dependencies. Installing the SDK does not activate a provider; tests construct the runner via __new__ and use synthetic capability doubles.

Validation: python -B -m pytest --noconftest -q -rs -p no:cacheprovider tests/test_self_task_execution_outcome.py
Native Windows Python3.13.15: 21 passed, 0 failed, 0 skipped before commit. Exact-head rerun and independent review recorded in delivery evidence. CI is separate evidence, never inferred from local PASS.

Verdict: scoped false-positive containment PASS; positive production effect integration PARTIAL. Draft only; not READY_FOR_MERGE_REVIEW or release ready.

Rollback: close/abandon this additive child branch; PR170 and main are untouched. If explicitly applied elsewhere, revert only this child repair commit. Preserve predecessor history. No deployment, service startup, provider/autonomy activation, credential or personal data operation.
