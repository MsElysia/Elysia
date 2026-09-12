# Checkpoint governance admission contract

Status: executable normative specification for GitHub Issues #29/#30/#31/#33.
This package is not connected to TaskLedger, the scheduler, Guardian, Codex,
Cursor, Git, or a repository policy service. Passing its tests does not close
any of those issues or release the Issue #23 gate.

`governance_bridge.schema.json` and `blueprint.py` repair the future integration
blueprint after independent operational red-team review. They model trusted
per-attempt admission issuance, content/effect-based authoritative classification,
canonical exact write-set and staged-patch binding, single-use generation-fenced
mutation tickets, task/admission ownership, immutable cycle context, mutation
result and verification identities, fail-closed dual-failure handling,
composed-boundary completeness and the separation between artifact existence,
technical verification and authorized progress. The authority chain is Admission
→ Classification → Ticket → Effect → Result → Verification → Authorized Progress,
with every link referencing the prior immutable digest. They are pure executable
specifications and do not reserve state, consume a production nonce, write a
file, claim a task, intercept Git, or authorize an operation.

`mutation_engine._direct_apply_mutation` is classified as `PARTIAL_BOUNDARY`, not
the first sufficient choke point. The smallest credible future bridge is a
`COMPOSED_MULTI_BOUNDARY_DESIGN`: admission issuance and objective attachment;
task/claim and queue attachment; authoritative classification; fenced ticket;
both live mutation and repository-adapter mediated write checks; evidence capture;
and a distinct authorized-progress transition. Repository-side enforcement is a
second required boundary for raw Git/GitHub and credentialed external agents.
All of those paths remain unimplemented and unprotected here.

The known Phase B inventory includes `mutation.py.apply`,
`mutation_engine._direct_apply_mutation`,
`implementer/repo_adapter.apply_patch`, `MutationPublisher.publish_mutation`
(including its direct `Path.write_text` effects) and
`MetaCoder.apply_mutation`. It is explicitly non-exhaustive. Every unknown or
unintegrated mediated writer remains `NOT_ENFORCED`.

## Problem and authority boundary

A newer checkpoint can omit an active gate and recommend a semantic port. An
owner-attributed GitHub App comment can then masquerade as human approval.
Checkpoint prose, completion packets, gate-reference lists supplied by workers,
and actor strings cannot establish either absence of a gate or release.

The eventual authoritative boundary is independently admitted objective/lineage
metadata plus durable gate storage, enforced atomically before claim or write.
The current unpublished local governance ledger already attempts local mutation
enforcement. This package specifies its missing portable checkpoint-consumption
contract without replacing, importing, modifying, or certifying that work.

## Inputs and decisions

`checkpoint_snapshot.schema.json` defines a **complete** snapshot of gates and
trusted admission records under `schema_version: 2`. See
`GOVERNANCE_V2_ADMISSION.md` for versioning, migration, root authority, objective
and action classification, and the Git-ancestry/governance-lineage distinction.
Gate scope identifies both objectives and branch/PR/SHA
lineages. Entity parent links represent task subdivision and restacking; all
ancestor objective references, lineage references, and explicit gate references
are unioned. Matching either objective or lineage, or an explicit inherited gate
reference, is sufficient. Workers cannot erase inherited scope by renaming a
child. Missing ancestors, missing referenced gates, cycles, duplicate identities,
unknown states/actions, and incomplete records invalidate the snapshot.

Each entity is independently admitted as `root` or `derived`. Roots cannot name
parents, and derived entities must name at least one existing parent. This makes
deleting ancestry from a known child structurally invalid instead of allowing it
to masquerade as a new root. The trusted admission boundary must assign this
classification from repository/control-plane evidence; worker declarations are
not authoritative.

Gate IDs are stable across generations. A snapshot contains exactly one current
record per gate ID, not an event log. Future durable storage must preserve prior
generations separately, prohibit generation rollback, and return a complete
snapshot atomically. The revision and digest are not release credentials.

`evaluate(snapshot, proposal, trusted_current_digest=..., checkpoint=...)` is a
pure reference oracle. Its proposal contains only an admitted entity ID and a
known action class; it cannot override gate metadata. `checkpoint` is ignored as
authority, regardless of prose recency, owner attribution, or release claims.

The digest must come from an independently trusted, current snapshot source.
Tests supply that pin explicitly to falsify stale/altered snapshot consumption.
The oracle does **not** fetch or authenticate that source, prove completeness,
or make a caller-chosen hash authoritative. Atomic freshness through actual
mutation, trusted admission/classification, repository-side enforcement, and
unforgeable human presence remain outside this specification's implementation.
If a worker controls both the state and pin, or lies about objective/ancestry or
action classification at admission, this package cannot protect that boundary.

All results are diagnostic; none grants execution authority:

| Disposition | Meaning |
| --- | --- |
| `BLOCKED_INVALID_STATE` | Required state, identity, graph, pin, or proposal is invalid. |
| `BLOCKED_PENDING_HUMAN_RELEASE` | At least one applicable effective gate blocks this action. |
| `NO_MATCHING_BLOCK_NOT_AUTHORIZATION` | This comparison found no blocking action; other checks remain required. |

Every valid comparison reports its applicable `effective_active_gates` as exact
gate ID/generation pairs, including for static/read actions. Each gate must block
claim, repo_write, semantic_write, integration, merge, deploy, and external_write.
Additional actions can be blocked. Static work outside those blocks is only a
no-match result, not an authorization to write a gated implementation.

## Release authenticity is intentionally unavailable

Both `active` and `released` records remain effective in this version. Even a
structurally valid release claim with matching gate ID/generation/scope/actions,
asserted human identity, transport/application provenance, and evidence is not
authorization. Every result says `release_validation=UNAVAILABLE`.

The schema preserves release assertions for audit comparison; it does not approve
them. GitHub login, OWNER association, app attribution, direct-human strings,
worker/verifier identity, and automation-writable proof references are never
accepted as human proof. Persisting `state=released` cannot bypass revalidation.
No resolver hook, credentials, release API, or permissive adapter is introduced.

Before any release can become valid, a human must select a trust anchor that
gated automation cannot invoke, forge, replay, or widen. Its independently
reviewed proof must bind the exact gate/generation/objective/lineage/action set,
including freshness/replay constraints, preserve principal and transport
provenance, and be revalidated after restart. A release cannot implicitly resume
work. That future mechanism is deliberately not implemented here.

## Executable acceptance and non-closure

Run `python -m pytest -q elysia_collective_seed/autopilot/contracts` with pytest
and jsonschema 4.x installed. Existing seed CI includes this directory recursively
and now installs the schema validator. No runtime/provider imports are needed.

Tests reconstruct #28/#29 at source `9b21e002a8d65735469e7038a22853a444ee7e1c`,
then present newer conflicting/omitting checkpoint prose. Fixture generation 1
and fixture gate identity are explicitly synthetic, not live governance state.
They attack ancestry, salami slicing, independent scope matches, multiple gates,
owner/actor spoofing, stale generations, broadened release scope, missing data,
snapshot substitution, and fresh-worker equivalence.

`fixtures/issue_33_scope_inheritance.json` also preserves the exact governance
shape of Issue #33: admitted Issue #23 ancestry reaches detached base `4ff2dc92`,
renamed side branch `cursor/autopilot-003-issue23-restack-cwa`, and product
`7374820`. Executable regressions prove that a branch alias, sibling, renamed
task, detached-SHA rebind, or sequence of smaller child changes cannot discard
the ancestor objective, lineage, or explicit gate reference. Checkpoint claims
that the official staging branch was unchanged, the implementation completed,
tests/review passed, or a PR exists remain non-authoritative inputs. The exact
historical commits are preserved as evidence and are not modified or promoted.

This Issue #33 result is **NO SPEC GAP — ENFORCEMENT GAP ONLY** when repository
ancestry, objective and action class have already been independently admitted.
Cursor, Codex and direct Git attempts receive the normative blocked disposition,
while `external_write_enforcement=NOT_ENFORCED` truthfully records that this
package cannot stop the mutation. A technically passing unauthorized artifact
does not become authorized progress. Missing or severed admission state fails
closed instead of accepting a friendly worker-supplied replacement label.

JSON file roundtrips verify only the portable contract, **not** SQLite migrations,
two-connection serialization, lease revocation, or production restart enforcement.
Every result declares `external_write_enforcement=NOT_ENFORCED`. There is no Git
write interception or deployment protection in this package. External writers
must remain a separate blocked acceptance criterion; a required check alone
would need careful distinction between blocking integration and blocking writes.

Blueprint repair tests similarly validate only reference invariants. A reference
ticket disposition explicitly says it is not production authority. Actual CAS,
atomic check-plus-write, durable nonce consumption, restart-safe high-water marks,
trusted classifier/issuer authentication, repository rules and the Issue #31
human trust anchor remain `NOT_IMPLEMENTED` or `UNRESOLVED` as applicable.
Effect-binding tests additionally validate path/operation/patch substitution,
task/admission and result/verification swaps, partial/crashed evidence states,
cycle identity continuity and mediated-writer inventory classification. They do
not make ordinary filesystem or Git operations transactional.

## Source and lineage

- [Current checkpoint](https://github.com/MsElysia/Elysia/issues/11#issuecomment-5636666687)
- [Gate packet](https://github.com/MsElysia/Elysia/issues/29#issuecomment-5638137343)
- [Human-authenticity refinement](https://github.com/MsElysia/Elysia/issues/29#issuecomment-5638881866)
- [Checkpoint consumption contract](https://github.com/MsElysia/Elysia/issues/30#issuecomment-5639605013)
- [Trust-anchor finding](https://github.com/MsElysia/Elysia/issues/31)

Base: PR #25 at `e67deaa0d7a321d261a3ad7f64ee9991e19a469a`, matching the
existing local governance work's base. No PR #26 reconciliation, Issue #23 port,
or verification verdict transfer is performed. Do not confuse GitHub Issues
#29/#30/#31 with unrelated historical `TASKS/TASK-0029/0030/0031.md` files.
