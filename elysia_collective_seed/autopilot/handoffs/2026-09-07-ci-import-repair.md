# AUTOPILOT-004 handoff: CI import repair

## Task
Investigate the failed Elysia Autopilot CI run for the dry-run dispatcher/ledger integration branch and repair only the bounded collection failure.

## Evidence
GitHub Actions run `34122102402` reached Python compilation and JSON validation successfully, then failed during pytest collection. The failure was isolated to `autopilot/test_completion_validator.py`, where a relative import (`from .completion_validator ...`) was collected without a known parent package.

## Change
Replaced the relative import with the repository-root absolute package import:
`from elysia_collective_seed.autopilot.completion_validator import validate_completion`.

No runtime code, provider invocation, network behavior, authority gates, ledger semantics, dispatcher behavior, or Guardian integration was changed.

## Verification state
Static diagnosis is complete. The new commit must pass Elysia Autopilot CI before the dry-run dispatcher/ledger integration is considered executable-verification complete.

## Next role
Independent verifier / CI observer.

## Next task
Confirm CI on the repaired head. If green, review completion-validation integration and then proceed to the next bounded AUTOPILOT-004 slice. If red, inspect the first failing test and repair only within the existing approved scope.
