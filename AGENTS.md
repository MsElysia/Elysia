# Elysia / Project Guardian Agent Contract

This repository is being developed through multiple AI coding and research agents. This file is the shared operating contract for Codex, Cursor, ChatGPT Work, local agents, and future compatible workers.

## Source of truth

1. Git history, the current task ledger, verified tests, and immutable Genesis sources outrank agent memory.
2. The historical AI Constitution / Elysia Covenant is an authoritative governance source once its original text is recovered and verified. Reconstructed summaries must not replace it.
3. The active canonical implementation must be determined from actual boot paths and tests, not filenames, README claims, or file existence.
4. Old files are evidence. Never delete the only known copy of historical code or documentation during reconciliation.

## Required work cycle

For every nontrivial task:

1. Read the assigned task packet and its acceptance criteria.
2. Inspect relevant current code, tests, prior handoffs, and Genesis context.
3. State internally what is known, uncertain, and blocked.
4. Make the smallest coherent change that advances the task.
5. Run appropriate tests, static checks, or verification.
6. Request or perform independent agent review for consequential code changes.
7. Produce a structured completion/handoff record.
8. Update the task state rather than relying on chat history.

## Permissions and safety

- Do not merge to `main` while the current reconciliation gate is active.
- Do not enable autonomous deployment, unrestricted external posting, unrestricted self-replication, or credential harvesting.
- Do not expose secrets or personal chatlogs in commits, PRs, issue comments, or logs.
- Prefer isolated branches/worktrees for write tasks.
- Read-only archaeological and classification tasks must not modify source material.
- Any change that expands external write authority, private-data scope, deployment authority, financial authority, or machine-level access requires explicit human approval unless an existing verified constitutional/runtime rule already authorizes that exact class of action.

## Agent-to-agent handoff

Agents do not invent project state in prose. They hand off through a persistent task ledger and completion packet containing at least:

- task ID;
- worker identity/provider/model if available;
- files read;
- files changed;
- tests/checks run and results;
- claims/evidence;
- uncertainties;
- risks;
- next recommended task/role;
- branch/commit/PR references where applicable.

A successor agent must be able to continue without access to the predecessor's conversational context.

## Reconciliation rules

When analyzing historical Elysia/Guardian material, classify each item as one of:

- `CANONICAL_CURRENT`
- `EXACT_DUPLICATE`
- `SUPERSEDED`
- `NEWER_VARIANT`
- `UNIQUE_LEGACY`
- `PORT_CANDIDATE`
- `GENESIS_SOURCE`
- `ARCHIVE_CANDIDATE`
- `PRIVATE_OR_SENSITIVE`
- `NEEDS_HUMAN_REVIEW`

Never archive or supersede a unique historical component solely because a newer file has a similar name.

## Definition of done

A coding task is not done because code was written. It is done when:

- acceptance criteria are satisfied;
- tests/checks pass or failures are explicitly explained;
- no known unique historical behavior was silently lost;
- the change is reviewable and reversible;
- the next task state is recorded.

## Autopilot objective

Advance Elysia / Project Guardian toward a coherent, testable, provenance-preserving, constitution-governed multi-agent system while minimizing unnecessary human intervention. When progress stalls, treat the stall as a missing capability, missing evidence, unclear acceptance criterion, or safety boundary. Record the blocker and create the smallest follow-up task that can resolve it.
