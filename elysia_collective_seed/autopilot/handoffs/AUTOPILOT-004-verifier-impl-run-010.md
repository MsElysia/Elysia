# AUTOPILOT-004 verifier implementation handoff

## Scope
Implemented the first executable, runtime-disabled slice of the independent-verifier lifecycle on isolated branch `autopilot-004-verifier-lifecycle-impl`, based on the reviewed verifier contract branch.

## Durable changes
- Added `verifier.py` with deterministic verifier selection.
- Producer worker is always excluded from verification.
- Same-independence-group workers are excluded.
- Missing independence metadata fails closed.
- Verifier must possess the requested verification capability and risk allowance.
- No provider invocation, external write, merge, deployment, or authority expansion is present.
- Added four regression tests covering producer self-verification, same-group rejection, distinct-group acceptance, and missing-metadata fail-closed behavior.

## Evidence
Implementation commit: `58332f55eb1ec5d457ad924f6ee1df7bef739103`
Test commit: `8e8e299cc16e0374f93517139b7ae8eed8107e29`

## Verification gate
This branch is not integrated. Next step is CI/test verification on the exact branch head, followed by independent review. If green, integrate only into the AUTOPILOT-004 dispatcher development lane, not `main` or the protected seed integration target.

## Follow-up
After this primitive is verified, wire verifier claims into the local SQLite ledger/state-transition implementation and add an end-to-end synthetic write -> review -> independent verification -> completed test. Keep all adapters runtime-disabled.
