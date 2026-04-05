# Elysia Spec (Invariants + Module Contracts)

## Invariants (non-negotiable)

1. IdentityAnchor must be present for any external action (web, finance, file writes outside task scope).

2. TrustEngine is the gatekeeper for autonomy: it can block or require review.

3. MutationFlow cannot mutate core governance modules without explicit human override.

4. PromptRouter outputs must be deterministic and schema-valid.

## Core modules (authoritative)

- IdentityAnchor
- TrustEngine
- MutationFlow
- PromptRouter
- ElysiaLoop-Core

## Working rule

- Cursor implements tasks; it does not redesign modules.
