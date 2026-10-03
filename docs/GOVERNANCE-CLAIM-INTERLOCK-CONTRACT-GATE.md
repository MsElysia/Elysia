# Governance claim interlock — Phase 0 contract gate

Result: **STOPPED before schema or code edits**. This is a compatibility finding, not an implementation of #29 and not a release decision.

## Exact refs inspected

- PR #32 product: `0843d9cad29a632a42946a5daf4abe4d0b93bdb0`; parent/base `e67deaa0d7a321d261a3ad7f64ee9991e19a469a`; open draft at observation time.
- PR #49 head: `87724730c816c7f6bbaf08e79d97647c9f872c26`.
- PR #54 head: `6fd5781b3c26a23a762150b587747749982fd429`.
- `AGENTS.md` exists at PR #32 exact product SHA and was read from that tree. It does not exist at current `main` SHA `722d8e4fe85d7e42ac34066c2d651849d15e734c`.

The newest explicit `CURRENT ENGINEERING CHECKPOINT` inspected was issue #11 comment `5962114284` (2026-10-02T21:57:01Z). It routes Issue #95 verification and does not release #29/#30/#31/#33. The current task expressly authorizes this governance audit lane; it does not transfer any older PASS or authorize #23 semantics.

## Required mapping and exact incompatibility

| PR #32 input | Trusted TaskLedger source found | Result |
|---|---|---|
| proposal `entity_id` | `task_id` exists in the task row/payload | A name can be mapped, but PR #32 requires the entity to belong to a complete admitted graph. TaskLedger has no such admission record. |
| proposal `action` | no immutable ledger-owned action-class field matching PR #32's enum | Caller task fields such as `risk_class`, `task_class`, and `human_approval_required` do not establish the governance action class. |
| entity objective refs | no normalized, immutable objective relation in the inspected ledger schema | Cannot derive without trusting mutable task payload or inventing a rule. |
| lineage refs | no admitted lineage graph or canonical repository/branch/SHA lineage store | Cannot derive trusted lineage, aliases, restacks, or multi-parent ancestry. |
| `parent_refs` graph | task `dependencies` are scheduler dependencies, not governance ancestry | Reinterpreting them would invent semantics and cannot prove a complete graph. |
| complete snapshot (`schema_version`, `revision`, `source_refs`, `gates`, `entities`) | no atomic snapshot/revision table or accessor | Cannot materialize the complete pinned snapshot required by `evaluate()`. |
| `trusted_current_digest` | no independently maintained trusted digest/pin | Computing `snapshot_digest()` from caller/task data would violate the contract's explicit trust boundary. |
| append-only generations -> unique `gate_id` records | no PR #32 selection/projection rule | Schema permits one record per `gate_id` in an evaluated snapshot; evaluator rejects duplicate IDs. It does not define newest-wins, status-wins, or another effective-generation projection. |

PR #32's evaluator states that classification, ancestry, and the current digest must come from independent trusted admission/storage (`checkpoint_reference.py`, lines 37-44). It rejects a digest mismatch (lines 48-51), builds dictionaries by `entity_id` and `gate_id`, and rejects duplicate identities (lines 56-59). It validates the entire ancestry graph (lines 63-86) and evaluates only the gate records supplied in that snapshot (lines 88-95). The schema requires the whole snapshot fields (schema lines 6-12) and defines `gate_id` plus `generation` on each gate (lines 42-64), but supplies no projection rule for multiple persisted generations.

The exact PR #32 `TaskLedger.claim()` reads only the task row and mutable JSON payload inside `BEGIN IMMEDIATE`, applies `execution_policy_error()`, worker eligibility, dependencies, and retry limits, then acquires the lease. It has no governance snapshot, trusted pin, objective/lineage ancestry, or gate-generation source. `submit_for_verification()`, `accept_verification()`, and `release()` do not supply those missing trust inputs.

## Dispatcher/executor boundary observed

At PR #54, `dryrun_orchestrator.dispatch_and_claim()` persists a task, calls `dispatch()`, then calls `TaskLedger.claim()`; a rejected claim returns `claim_blocked`. This path stops at a claimed dry-run result and does not invoke the executor adapter. The separate `dry_run_executor()` returns `would_execute` only after its trusted-state checks. Its task-level human approval check is at `executor_adapter.py` lines 216-218 and compares the envelope reference with `TrustedExecutionState`; it is not the governance source requested here. No production claim-to-executor call edge was found in the inspected PR #54 tree.

Consequently, the requested real claim-to-`would_execute` regression cannot honestly be added without first selecting or creating a production composition boundary, which is outside Phase 0 and would not cure the missing governance trust inputs.

## Fail-closed behavior and smallest human decision

Malformed, missing, stale, duplicate, contradictory, or unpinned state must remain blocked. With the current persisted model, **all governance evaluation at claim must be treated as unavailable**, not synthesized from caller-controlled payloads.

The smallest required human design decision is to designate a trusted admission/storage authority and a versioned projection contract that:

1. owns objective, action-class, lineage, and full ancestry admission;
2. atomically pins a complete snapshot revision and digest independently of claim callers; and
3. defines how immutable gate generations become the single unique-`gate_id` effective snapshot record without dropping inherited/effective gates.

Until that decision is made and independently reviewed, Step 1 persistence/accessor work and Step 2 claim/dispatch wiring are intentionally not performed.

## Post-audit authority note

PR #98 later received an owner-attributed comment proposing a Guardian-owned admission store and highest-valid-generation projection. Per this task's trust boundary, a username, owner association, or connector comment is not proof of human authority. That comment is therefore recorded as design input only and does not retroactively authorize this product SHA, transfer a PASS, or cross the Phase 0 gate. A direct human instruction in the active task is still required before any Part B implementation.
