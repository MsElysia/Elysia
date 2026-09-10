# Genesis Tranche: Capability Realism, Bounded Tools, and Staged Adoption

**Tranche scope:** repository-backed reconstruction of the transition from broad tool discovery/registration toward bounded execution, explicit capability evidence, and staged governance before adoption.

**Chronology:** repository evidence confirms relevant Guardian code was present by **2026-04-05** and updated through at least **2026-04-13**; the Collective capability-intake protocol was committed **2026-09-06**. Some design comments point to an earlier conversation source but do not provide a recoverable date, so that origin remains **unverified**.

**Confidence:** high for inspected repository behavior and commit dates; medium-to-low for the chronology of the underlying conversations and for claims about which local implementation was active at runtime.

---

## 1. Provenance ledger

### Source A — Guardian AI Tool Registry
- **Type:** REPOSITORY_EVIDENCE
- **Path:** `project_guardian/ai_tool_registry_engine.py`
- **Inspected branch:** `elysia-local-reconciliation-20260909-1657`
- **Blob:** `1207411a6fac53d4d30a8622276e8ec4295e9245`
- **Repository history:** file history on the reconciled branch reaches the initial Guardian/Elysia commit `cf3462f69edc555bd023137cddd9df8db1482759` dated 2026-04-05 and later tooling sync `2c4deb81a55ea598662da2b7ef3391f72ed7876c` dated 2026-04-13. The 2026-09-09 reconciliation commit preserved the local version without proving when every local hunk was authored.
- **Important source note:** the file header says it is based on “Conversation 3 (elysia 4 sub a) design specifications.” The raw conversation has not been recovered in this tranche, so its date, exact wording, and authority remain **UNVERIFIED**.

### Source B — Guardian Capability Registry
- **Type:** REPOSITORY_EVIDENCE
- **Path:** `project_guardian/capability_registry.py`
- **Inspected branch:** `elysia-local-reconciliation-20260909-1657`
- **Blob:** `f7f46d056120decd314add7354f127133cd7c902`

### Source C — Bounded Browser Capability
- **Type:** REPOSITORY_EVIDENCE
- **Path:** `project_guardian/bounded_browser/capability.py`
- **Inspected branch:** `elysia-local-reconciliation-20260909-1657`
- **Blob:** `0d72c2e6b19b1d2fcdb77ba10977caee42904e14`

### Source D — OpenClaw Integration
- **Type:** REPOSITORY_EVIDENCE
- **Path:** `docs/OPENCLAW_INTEGRATION.md`
- **Inspected branch:** `elysia-local-reconciliation-20260909-1657`
- **Blob:** `53817b094b63d6cc235598bdda3618da2d721bee`
- **Caution:** this document describes intended/configured integration behavior. It is not by itself proof that a live OpenClaw worker was running or that every documented route was exercised successfully.

### Source E — Collective Capability Intake Protocol
- **Type:** REPOSITORY_EVIDENCE / IMPLEMENTED_DOCUMENTATION
- **Path:** `elysia_collective_seed/capability_intake_protocol.md`
- **Inspected branch:** `elysia-collective-0.1-seed`
- **Blob:** `5cab3dbbb7b4147745d995ba3e2c064c0390464e`
- **Commit:** `cbb535659841a37f03fee9de7f559288c4acee2d`
- **Date:** 2026-09-06

---

## 2. Early/expansive design: finding tools was treated as a first-class capability

**IMPLEMENTED / REPOSITORY_EVIDENCE**

Guardian's `ai_tool_registry_engine.py` was designed to discover and manage external AI tools rather than hard-code one provider. The inspected version includes live read-only discovery routines for Hugging Face Hub and OpenRouter, provider metadata, capability metadata, usage/success/failure counts, adapter fields, rate/cost metadata, and environment-variable-based token lookup.

This is evidence of an important design instinct: Elysia/Guardian was not meant to be a single-model shell. It was intended to survey available computational affordances and represent them as tools that could be selected or routed.

The same file also preserves an early security warning: tool registration is sensitive; API-key material in metadata would require stronger protection in production; network operations were intended to route through a controlled gateway. This shows that expansion of capability and concern about the authority surface coexisted rather than appearing only later.

**UNVERIFIED HISTORICAL ORIGIN**

The comment tying the design to “Conversation 3 (elysia 4 sub a)” is valuable provenance, but until the raw transcript is recovered it must not be converted into a dated Genesis claim or quoted as a user decision beyond the literal repository comment.

---

## 3. Capability awareness evolved beyond a simple tool list

**IMPLEMENTED / REPOSITORY_EVIDENCE**

`project_guardian/capability_registry.py` shows a later or more developed idea of capability awareness. The registry does not merely enumerate names. It records snapshots, system-understanding reports, outcomes, a scoreboard, usage logs, and usage statistics. It also contains diagnostics to distinguish states such as “never registered in storage” from “storage non-empty but active list empty.”

That distinction matters historically. It reflects recognition that **a tool being mentioned, stored, or configured is not equivalent to a tool being available and usable**.

The same inspected version contains a direct-autonomy denylist for generic LLM transport and bare web fetching. The comments explain the rationale: autonomous selection should prefer concrete bounded work rather than generic “ask an LLM,” and web fetch should not be selected without URL-bearing payload/context.

**INTERPRETATION**

This is an early form of what the Collective later makes explicit as *capability realism*: Elysia should reason about what is actually operational, under what conditions, and with what cost or restrictions, rather than infer power from module names alone.

This interpretation is strong but should not be mistaken for recovered historical wording from the user or an original Constitution.

---

## 4. Bounded browser: autonomy expressed as budgets, allowlists, and refusal paths

**IMPLEMENTED / REPOSITORY_EVIDENCE**

The bounded-browser capability provides a concrete example of capability expansion being paired with limits.

The inspected implementation:
- defaults to three pages, two scrolls, depth one, and one followed link per page;
- hard-caps pages, scrolls, depth, and links even when payloads request more;
- rejects unsafe URL schemes;
- supports host allowlists;
- returns structured results and budget usage;
- reports unavailable browser infrastructure instead of silently pretending success.

It also includes an explicit `allow_any_domain` override in the payload contract.

**SAFETY TENSION / UNRESOLVED QUESTION**

The bounded defaults and refusal paths are strong evidence of a “limited agency” philosophy in code. However, the existence and authority model of `allow_any_domain` needs separate governance review. This tranche does not establish who was permitted to set that override in the live runtime, whether that permission was sufficiently constrained, or whether all call paths preserved the same limits.

---

## 5. OpenClaw: separation of the Elysia brain from external execution surfaces

**REPOSITORY_EVIDENCE**

The OpenClaw integration document describes Elysia as a reasoning/backend service that can be connected to external messaging channels and, separately, to an execution worker.

Important controls documented in the inspected version include:
- localhost-oriented endpoints;
- optional bearer authentication, with a warning not to expose the service publicly without protection;
- an execution-worker adapter separated from chat transport;
- explicit health checks and structured worker responses;
- task-log and stop routes;
- autostart disabled by default unless explicitly configured;
- no guessed executable path when no real OpenClaw installation is known.

**PROVENANCE / PRIVACY NOTE**

The reconciliation process deliberately excluded the local `config/openclaw.json` pending review. Therefore this Genesis record uses only the sanitized repository documentation and does not import potentially private local configuration or credentials.

**UNRESOLVED**

The documentation establishes design intent and interface shape, not proof of production use. Runtime reachability, actual worker identity, deployed channel connections, and historical live-action scope remain unverified here.

---

## 6. September 2026 Collective rule: discovery is not adoption

**IMPLEMENTED_DOCUMENTATION / REPOSITORY_EVIDENCE**

The 2026-09-06 Collective capability-intake protocol makes a sharper distinction than the older tool-registry design:

`discovery -> CANDIDATE -> VERIFIED -> PROPOSED -> security/Erebus review -> SANDBOXED -> ADOPTED or REJECTED`

The protocol explicitly says that a newly discovered product, connector, model tool, site integration, agent framework, protocol, or data source is **not automatically an Elysia capability**. It first becomes a candidate.

The candidate record is expected to include evidence, authentication requirements, read/write/external-action permissions, provider data exposure, cost, risk, mapping to existing Guardian architecture, a concrete experiment, and a rollback path.

It further says to prefer adapters over duplicate subsystems, test capabilities in bounded experiments, and require human governance for consequential integration. Capability Watch may recommend adoption but may not grant itself permissions or enable a capability autonomously.

---

## 7. Historical design arc

**INTERPRETATION**

Taken together, the repository evidence supports a coherent evolution:

1. **Discover the environment.** Guardian should be able to discover and represent many external tools/models rather than remain tied to one provider.
2. **Know what is really available.** Capability registries add operational state, diagnostics, usage, outcomes, and selection constraints.
3. **Bound dangerous surfaces.** Browsing and external execution gain budgets, allowlists, structured errors, local defaults, and disable paths.
4. **Separate discovery from authority.** The Collective formalizes that an available external affordance starts as a candidate, not an adopted power.
5. **Require evidence before phenotype change.** Adoption becomes an experiment-and-governance process with rollback and provenance.

This arc should be treated as a reconstruction from code and later documentation, not as a verbatim founding philosophy.

---

## 8. Contradictions and tensions to preserve

### Expansion vs minimum authority
Guardian contains a strong drive to discover new models/tools while later Collective policy emphasizes minimum permissions and staged adoption. These are not necessarily contradictory, but they create a permanent design tension: **environmental curiosity must not silently become execution authority**.

### Registry presence vs operational truth
Older registry structures can contain metadata for tools that are unavailable, unregistered, revoked, or only partially implemented. Later diagnostics and Collective intake policy respond to this problem, but no evidence here proves every historical capability claim was accurate.

### Local convenience vs production security
OpenClaw documentation permits unauthenticated localhost operation and optional local placeholder keys while warning against public exposure. This is a legitimate development convenience but must not be generalized into a production security rule.

### Operator override vs bounded autonomy
The browser implementation includes strong caps and host constraints, but also an `allow_any_domain` override. The authority boundary around that override is not resolved by this tranche.

### Self-extension vs governance
The early registry architecture encourages external-tool discovery; the later Collective expressly forbids the discovery mechanism from granting itself permissions. This is an important constraint on future self-improvement designs.

---

## 9. Unresolved questions for future Genesis recovery

1. Recover the raw “Conversation 3 (elysia 4 sub a)” referenced by `ai_tool_registry_engine.py`. What exact requirements came from the user, and when?
2. Which capability-registry/tool-registry implementation was actually wired into the canonical Guardian runtime at each stage?
3. Which external tools were genuinely executed successfully, versus merely discoverable or registered?
4. Was API-key metadata ever persisted unencrypted in historical runtime data, and if so can provenance be retained without copying secrets into Genesis?
5. Who could set browser `allow_any_domain`, and was that authority always human/operator controlled?
6. Was OpenClaw ever used for live external actions, or did it remain local/scaffolded during the preserved period?
7. Can current CapabilityRegistry outcome/usage history be recovered without importing unrelated private activity?
8. Should the Collective distinguish `DISCOVERED`, `REACHABLE`, `AUTHENTICATED`, `TESTED`, and `AUTHORIZED` as separate capability states to prevent future false-capability claims?
9. How should model/tool availability changes over time affect Genesis: append a new state, never rewrite the old state.
10. Which parts of the older auto-discovery registry should survive, and which should be replaced by the stricter candidate-intake protocol?

---

## 10. Genesis preservation decision

**PRESERVE** the historical aspiration for a tool-using, environmentally adaptive Elysia.

**PRESERVE** the evidence that Guardian increasingly represented capability as operational state rather than mere module presence.

**PRESERVE** bounded browser budgets, refusal behavior, adapter separation, rollback/disable paths, and usage/outcome measurement as historically significant design patterns.

**DO NOT INFER** that discovered or documented tools were live capabilities without runtime evidence.

**DO NOT IMPORT** local OpenClaw configuration, API keys, private provider data, or unrelated user activity into Genesis merely to improve completeness.

**DO NOT TREAT** this reconstructed arc as Constitution/Covenant text. The original governance source remains higher priority when recovered.

The durable lesson of this tranche is narrow: **Elysia's capability architecture evolved from asking “what can I connect to?” toward also asking “what is actually available, bounded, verified, authorized, and worth adopting?”**
