# Current Guardian to Collective Mapping

This is a preliminary map of the GitHub baseline. It must be reconciled against the local Guardian ZIP before runtime integration.

| Collective concept | Existing Guardian candidate | Preliminary use |
|---|---|---|
| Elysia synthesis | orchestrator prompt + existing synthesis/introspection paths | Reuse selected context/orchestration plumbing, but do not equate orchestrator authority with Elysia's synthesis role. |
| Erebus | `project_guardian/prompts/agents/critic.py` + adversarial self-learning modules | Extend critic into structured falsification packets and blinded adversarial review. |
| Engineer | `project_guardian/prompts/agents/executor.py`, mutation sandbox/validator | Reuse bounded execution and sandbox concepts; protected deployment remains human-gated. |
| Archivist | MemoryCore/timeline/vector/lineage components | Add packet validation, lineage, three memory classes, and append-first state changes. |
| Researcher | WebScout + bounded browser | Reuse bounded research interfaces; require evidence packets and provenance. |
| Explorer | creativity/dream/reflection components | Use for hypothesis generation without allowing generated ideas to self-promote to fact. |
| Collective decisions | `project_guardian/consensus.py` | Reuse agent registration, weighted voting, confidence, and history for decisions. Keep consensus separate from factual truth. |
| Dream Cycle | `project_guardian/dream_engine.py` | Extend existing reflective process with contradiction, convergence, orphan, staleness, and organizational passes. |
| Moltbook observation | `project_guardian/bounded_browser/moltbook.py` | Preserve current read-only, domain-locked, budget-limited observation boundary. |
| Safety boundary | `config/eai_safety.json` + mutation/recovery systems | Preserve autonomous deployment deny policy and lineage/audit concepts. |

## Important findings from current GitHub baseline

### ConsensusEngine
Already supports agent registration, weighted voting, confidence-weighted consensus, decision history, and configurable thresholds. Collective 0.1 should adapt this for governance decisions but must not use majority vote as an evidence validator.

### DreamEngine
Already models persistent Dream records and reflective types including memory reflection, behavior analysis, optimization, planning, and other reflective modes. Collective Dream Cycle should be an extension/output adapter around this machinery if the local ZIP does not contain a better version.

### Existing critic and executor
The current critic already prioritizes safety/correctness and weak-assumption detection. The current executor already emphasizes bounded outputs and minimal scope. These are strong ancestors for Erebus and Engineer rather than reasons to build duplicates.

### Moltbook
The existing preset is read-only and host-allowlisted with conservative page/scroll/depth budgets. Do not quietly turn it into a posting agent. External write behavior, if ever added, belongs behind a new explicit permission and human approval path.

### Deployment safety
Current EAI safety config denies autonomous deployment. Collective work must preserve that default during experimentation.

## ZIP reconciliation questions
When the local project arrives, determine:
1. Which modules are newer locally than GitHub?
2. Which advertised/activation-matrix modules actually exist locally but not on GitHub?
3. Are there multiple competing MemoryCore, DreamEngine, consensus, swarm, or agent-manager implementations?
4. Which implementation is truly wired into boot/orchestrator paths?
5. Which tests currently protect mutation, rollback, trust, browser, and agent execution?
6. Are any credentials, generated data, local databases, or private histories present that must never be committed?
7. What is the smallest adapter layer needed to run EC-001 without refactoring the whole system?
