# One-entry operator interface plan

**Status:** Planning only. Do not implement from this document without a separate UI task and tests.  
**Scope:** Simplify the Elysia / Project Guardian control panel into one primary operator entry point while preserving safe-stack boundaries.

## Product goal: one entry, any question

The control panel should open on one obvious operator entry: a single conversational input where the operator can ask any question, request a status summary, search memory, inspect recent reasoning, or ask what to review next.

The intended feel is: "Ask Elysia anything from here." The operator should not need to know whether the answer comes from conversation history, brain trace visibility, memory ranking, self-improvement proposal summaries, prompt-contract status, governance diagnostics, or runtime status.

The first screen should answer three operator needs:

1. Ask a question or state an intent.
2. See the current safe operating state.
3. Open supporting detail only when needed.

## Current UI problem

The current `CONTROL_PANEL_TEMPLATE` exposes many primary tabs:

- Dashboard
- Learning
- Tasks
- Workbench
- Security
- Memory
- Introspection
- Control
- Insights
- API meter
- Logs

The actual "Conversation Chat" entry point exists inside the Control tab, while safe-stack diagnostics live across dashboard cards and secondary tabs. This makes the operator choose a subsystem before asking a question, even when the desired workflow is exploratory: "What is going on?", "What should I review?", "Why is this blocked?", or "What did you consider?"

The result is cognitive overhead:

- The user has to understand internal module names.
- Read-only diagnostics compete with primary interaction.
- Safe-state information is present but visually scattered.
- Advanced detail panels are useful, but they look like first-class workflows.
- Future memory import or confirmation features could accidentally look like action controls unless clearly staged behind planning and review boundaries.

## Proposed simplified interface

Use one primary operator home view, tentatively named **Ask Elysia**.

Primary layout:

- One prominent text input at the top: "Ask anything..."
- Conversation transcript immediately below, backed by `ConversationStore`.
- Small persistent safety strip near the input:
  - Autonomy: off
  - Live execution: off
  - Brain trace: dry-run/config-gated
  - Memory ranking: read-only
- A compact "Sources considered" area attached to each answer, showing whether the answer used chat history, latest brain trace metadata, proposal summaries, memory ranking status, prompt-contract status, or governance diagnostics.
- A right-side or below-the-fold detail drawer for secondary panels.

The operator should be able to ask:

- "What happened recently?"
- "What should I review next?"
- "Show me the latest brain trace."
- "Are there self-improvement proposals?"
- "Is memory ranking healthy?"
- "What are the prompt contract warnings?"
- "Are any operator confirmations pending?"

The UI should route those requests to read-only summaries first. It should not display apply, run, execute, live, or autonomy controls as part of this simplification.

## Request routing model

The first implementation should be a UI and request-shaping simplification over existing safe-stack surfaces, not a new autonomous router.

Recommended routing tiers:

| Request type | Detection approach | Safe source |
|--------------|-------------------|-------------|
| General chat | Default path | Existing `/api/chat` and `run_operator_chat_turn` host integration |
| Conversation history | "history", "conversation", "what did we say" | `ConversationStore` and `/api/chat/history` |
| Brain trace | "brain trace", "reasoning trace", "what did you consider" | `/api/brain/trace/latest` |
| Self-improvement proposals | "proposal", "improvement", "review ideas" | `/api/self-improvement/proposals` |
| Proposal export | Explicit request to export selected proposal prompt | Existing export endpoint; copy-only |
| Memory ranking | "memory", "ranking", "important memories" | `/api/memory/ranking/summary` |
| Prompt contracts | "contract", "JSON format", "validation" | `/api/prompt-contracts/status` |
| Governance confirmations | "confirmation", "live execution guard", "pending approvals" | `/api/governance/operator-confirmations` |
| System status | "status", "safe state", "is anything on" | Existing status/safety fields plus safe-stack metadata |

Routing should be deterministic and transparent in early phases:

- Start with keyword/intention mapping.
- Show which read-only source was opened or summarized.
- Fall back to normal operator chat when no specific diagnostic intent is detected.
- Keep all routed diagnostic fetches read-only.
- Keep `run_operator_chat_turn` as the shared chat orchestration layer; it does not call tools, shell, autonomy, or models by itself.

## Advanced panels as secondary details

The following should become secondary/collapsible details behind the one-entry view:

- Brain Trace
- Self-Improvement Proposals
- Proposal Export
- Memory Ranking
- Prompt Contracts
- Operator Confirmation Diagnostics
- API meter
- Logs
- Introspection
- Security events
- Task queue
- Workbench artifacts
- Learning status/settings

Recommended grouping:

| Collapsible group | Contains |
|-------------------|----------|
| Reasoning | Brain Trace, Think-Decide-Act metadata, trace warnings |
| Review Queue | Self-Improvement Proposals, Proposal Export |
| Memory | Conversation history, Memory Ranking, future import review |
| Governance | Operator confirmations, live-execution guard status, audit summaries |
| System | API meter, prompt contracts, logs, security status |
| Work | Task queue, workbench artifacts, learning status |

The collapsed state should show compact counts or badges, not full tables. Detail panels should open only when the operator asks for them or clicks a "details" affordance.

## Safety behavior

The simplified interface must preserve the current safe-stack posture:

- Live execution remains disabled by default.
- Autonomy remains unwired.
- The one-entry interface must not add apply, run, execute, live, or autonomy controls.
- Self-improvement remains review/export only.
- Proposal export remains copyable text only.
- Memory ranking remains advisory and read-only.
- Prompt-contract status remains read-only and must not call models.
- Operator confirmation diagnostics remain read-only and must not create, revoke, or mark confirmations used.
- Brain trace display remains sanitized and dry-run/config-gated.
- Raw prompts, full traces, secrets, and hidden reasoning must not be exposed in UI payloads.
- If routing is uncertain, prefer a normal chat response plus safe suggestions, not action.

The safety strip should remain visible near the primary input so the operator does not confuse conversational assistance with live execution.

## Future drag/drop memory import scope

Drag/drop memory import should be **later**, not part of the first simplification.

Future scope, after the one-entry interface is stable:

- Allow dropping local text, JSON, Markdown, or exported conversation files into a review queue.
- Parse and summarize locally before anything is saved.
- Show a preview with redaction warnings and duplicate detection.
- Require explicit operator confirmation before importing into memory.
- Store import provenance and source metadata.
- Provide undo/delete for newly imported batches.
- Keep imports separate from live execution and autonomy.

Non-scope for initial one-entry UI:

- No automatic memory writes from dropped files.
- No background ingestion without review.
- No external fetches from dropped URLs.
- No embeddings or model calls unless separately planned and gated.
- No bulk import into production memory without tests.

## Phased implementation

### Phase 0: planning and static tests

- Keep this document as the design reference.
- Add static tests before implementation to assert the new one-entry markers and safety copy.
- Confirm current safe-stack smoke remains green.

### Phase 1: visual consolidation only

- Make the first screen the conversational operator entry.
- Move existing safe-stack panels into secondary/collapsible sections.
- Reuse existing endpoints and JavaScript functions.
- Do not change server routes or runtime behavior.
- Do not add new controls.

### Phase 2: read-only routing helpers

- Add deterministic client-side or server-side request classification for read-only diagnostics.
- Show source badges for answers and opened detail panels.
- Keep fallback as normal operator chat.
- Add tests for routing labels and no unsafe controls.

### Phase 3: operator diagnostics drawer

- Add a unified details drawer for Brain Trace, Proposals, Memory Ranking, Prompt Contracts, and Governance.
- Keep detail fetches explicit and read-only.
- Add empty states and stale-data warnings.

### Phase 4: future memory import planning

- Write a separate drag/drop import plan.
- Add tests for preview-only behavior, redaction, duplicate detection, and no automatic memory mutation.
- Implement only after review and explicit approval.

## Non-goals

- Do not enable live execution.
- Do not wire autonomy.
- Do not redesign backend architecture.
- Do not replace `run_operator_chat_turn`.
- Do not add apply/run/execute controls.
- Do not add confirmation creation or consumption flows.
- Do not implement drag/drop import in the first UI simplification.
- Do not call real LLMs or external APIs from tests.
- Do not expose raw traces, raw prompts, secrets, or hidden reasoning.
- Do not remove advanced diagnostics; make them secondary and discoverable.

## Tests needed before implementation

Before any UI implementation, add tests for:

- One-entry panel exists and is the first operator-facing surface.
- Primary input copy supports "one entry, any question".
- Safety strip includes autonomy off, live execution off, and dry-run/read-only language.
- Advanced panels are present as secondary/collapsible details.
- Brain Trace, Self-Improvement Proposals, Proposal Export, Memory Ranking, Prompt Contracts, and Governance diagnostics remain available.
- No apply/run/execute/live/autonomy controls appear in the one-entry or safe-stack detail sections.
- Existing safe-stack endpoints remain referenced.
- `run_operator_chat_turn` remains the shared chat orchestration helper.
- Request routing tests cover diagnostic intents and normal-chat fallback.
- Drag/drop import is absent in Phase 1, or clearly disabled/planning-only if copy is present.
- Smoke includes the new UI marker tests.
- Existing `python scripts/run_safe_stack_smoke_tests.py` remains green.
