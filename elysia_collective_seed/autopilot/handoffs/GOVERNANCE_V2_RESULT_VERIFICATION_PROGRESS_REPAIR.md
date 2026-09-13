# Governance v2 result / verification / progress repair handoff

Base: `334f6233339483fbae8b9f37ea9a2b78c7a77eac`
Scope: governance schema, executable reference model, and adversarial tests only.

The repair adds a generation-fenced v2 control state, canonical principal and
independence-group registry, exact-effect transaction/receipt lifecycle,
discriminated Git result identity, fresh single-use verifier claims, immutable
verification records, and task/destination-bound single-use progress tokens.
Every downstream artifact repeats and validates the complete ticket, admission,
classification, target, effect, observer, claim, test/evidence, and verification
chain. Control transitions also append prior generation/digest ancestry, and
issued claims, verification records, and progress tokens remain pinned in state.

The model returns new immutable state values; it does not perform repository or
external writes and is not wired into any runtime writer. TaskLedger semantics,
credentials, hooks/rulesets, production adapters, and Issue #23 were not changed.

Residual gates are explicit: production and cross-universe enforcement are
`NOT_IMPLEMENTED`, external writes are `NOT_ENFORCED`, the Issue #31 trust anchor
is `UNRESOLVED`, and Issue #23 remains human-governance gated.
