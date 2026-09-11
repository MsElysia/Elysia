# Draft pull request prepared for user approval

Title: Specify fail-closed governance checkpoint consumption

Base branch: `codex/remote-fix-8-claim-policy`
Head branch: `codex/governance-checkpoint-contract`
Exact product: `0843d9cad29a632a42946a5daf4abe4d0b93bdb0`
Keep draft and unmerged.

## Proposed PR body

Newer checkpoint prose can omit an active governance gate, and owner-attributed
automation comments can appear to authorize release. This adds a strict snapshot
schema and pure executable checkpoint contract: inherit objective/lineage scope,
retain effective gates despite checkpoint omission, block stale/malformed state,
and keep all release claims unverified until a human trust anchor is selected.

This is normative schema/spec/test work for #29/#30/#31, complementary to the
unpublished local ledger interlock. It is not wired into the scheduler, ledger,
Guardian, or Git, and it grants no execution authority. Production persistence,
external write enforcement, and human release authentication remain unresolved.
No #23 semantic work or gate release is included.

Local required suite: 328 passed, including 115 new contract tests. Independent
verifier and architecture-review results are recorded separately for the exact
product SHA above. CI configuration includes these tests and jsonschema 4.x;
GitHub CI has not run on this unpublished candidate.

The candidate is based on PR #25 at `e67deaa...`; it does not reconcile PR #26 or
transfer an existing PASS. Existing branches and uncommitted work are preserved.

Refs #11, #29, #30, #31. Keep all issues open; no merge/deploy/release authority.

## Publication boundary

No push, PR, or issue comment has been made. The user's attached PROTECTED
ACTIONS / HUMAN GOVERNANCE instructions reserve external posting for approval.
If approved, publish the exact product branch and evidence branch, create this
draft PR against PR25, and attach exact-SHA verification evidence. Publication
does not authorize integration, #23 semantic work, a trust anchor, or gate release.
