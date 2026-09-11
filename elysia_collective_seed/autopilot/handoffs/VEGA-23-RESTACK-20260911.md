## VEGA VERIFICATION

### TARGET
Issue #23, branch autopilot-003-issue23-restack, exact product 9b21e002a8d65735469e7038a22853a444ee7e1c; parent 1b421cbfc50db7d03e7eaf5b222d91411fcfc9ea. Source PR27 is not this target. Read AGENTS.md, #23, latest #11/#23 handoffs, restack manifest, complete one-file product delta, singleton, caller, CI and existing tests. The implementer explicitly describes a partial port; this report does not attribute a full-completion claim to it.

### CLAIMS TESTED
Pure audit descriptor, background-disable normalization, environment-free audit configuration, compatibility of existing backend call, inherited lifecycle regressions. Three audit checks pass; call compatibility fails.

### TESTS EXECUTED
Python 3.12.14 / pytest9.1.1. Runner C:/Users/Owner/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe; PYTHONPATH=C:/Users/Owner/Project guardian/.worktrees/vega-test-15/.vega-deps; PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Worktree .worktrees/vega-23-restack-check. Elevated runner access is for dependency ACLs. No live core constructed.

- `python -m pytest -q tests/test_vega_restack_bootstrap.py --basetemp .vega-safe-check`: 3 passed, 1 failed, 0.17s. Runtime-import guard, repeated audit calls, opt-out, environment independence, and AST-extracted actual call bound against actual signature.
- `python -m pytest -q elysia_collective_seed tests/test_autopilot_verifier.py tests/test_autopilot_verifier_ledger_migration.py tests/test_autopilot_verifier_lifecycle.py tests/test_vega_verifier_boundaries.py tests/test_autopilot_lifecycle_repairs.py tests/test_vega_evidence_binding.py tests/test_autopilot_evidence_binding.py tests/test_autopilot_evidence_binding_regressions.py tests/test_vega_evidence_binding_adversarial.py --basetemp .vega-ci-check`: 147 passed,2.74s. Current branch CI-equivalent collection; includes original evidence and lifecycle falsification suites.
- `git diff 1b421cb HEAD`: only elysia_sub_guardian.py product change; no inherited tests weakened in this delta.

### NEW TESTS
tests/test_vega_restack_bootstrap.py: four minimal probes. Failure remains unmodified, no xfail. No product repairs.

### RUNTIME REACHABILITY
describe_guardian_bootstrap calls init_guardian_core(mode='audit'), returning descriptor before importing project_guardian. This isolated path works in tested cases. The existing elysia.py:388 calls init_guardian_core(config=self.config), whereas the new signature requires keyword-only mode. AST/signature binding proves incompatibility without importing/executing the full backend. Direct GuardianCore construction remains explicitly outside the safe descriptor and unverified; no live startup was attempted.

### FAILURES
HIGH integration regression on the partial branch: unchanged backend call raises TypeError: missing a required argument: 'mode'. Reproduce with `python -m pytest -q tests/test_vega_restack_bootstrap.py::test_existing_backend_call_matches_bootstrap_signature`. Expected the shipped caller explicitly selects its intended bootstrap mode; actual call supplies only config. Cause: callee API port landed before caller. This is acknowledged partial-port work, not a new architectural finding; use existing #23.

### FALSE CAPABILITIES
None attributed: descriptor labels runtime_constructed/runtime_wiring_verified false and handoff admits six files remain. Passing inherited CI does not prove the new bootstrap integration works.

### SAFETY CHECKS
No runtime import during repeated descriptor calls; background disable flags preserved; environment does not change audit default. Full socket/process/thread instrumentation and true construct-without-activate proof remain pending. No providers, deployment, permissions, merge or historical-material edits.

### VERDICT
FAIL for current branch backend-call compatibility; audit descriptor tests pass. Not a verdict on PR26's independently reviewed product boundary.

### CONFIDENCE
0.99 for signature incompatibility; no whole-runtime safety claim.

### ASTRA REPAIR TASK
Within existing #23 complete the paired caller port: explicitly select the intended mode at elysia.py's bootstrap call and test caller/callee compatibility together. Do not restore implicit operational defaults merely to pass. Complete remaining bounded port/tests only under the existing lineage/governance decision; this verification does not authorize restacking or merging divergent lineages. Retain the reproduction and rerun exact-head tests.

### EREBUS QUESTIONS
Can incomplete API ports be kept non-consumable until caller and callee land together? The conflicting lineage guidance tracked in #28 is not resolved by a green test or this report.

### NEXT TEST PRIORITY
On next #23 product head rerun this call compatibility test and full adversarial audit suite. Direct construction/activation separation remains an open requirement. PR24/25/26 already have independent reports at their pinned SHAs; no PASS transferred to this new partial port. PR15 remains at6649b89 with its existing #22 failure; repaired descendant candidates must be considered separately.
