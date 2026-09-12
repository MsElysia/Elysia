# Guardian Canonical Runtime Map

**Agent:** Guardian Canonical Mapper  
**Date:** 2026-09-09  
**Workspace:** `C:\Users\Owner\Project guardian`  
**GitHub:** `MsElysia/Elysia`  
**Analyzed branch tip:** `elysia-local-reconciliation-20260909-1657` @ `821570c`  
**Compared to:** `main` @ `722d8e4` (2026-05-09)

**Scope rule:** Analysis and classification only. No runtime code modified. No merges, deletes, history rewrites, or live-autonomy enablement.

Machine-readable twin: [`canonical_runtime_map.json`](canonical_runtime_map.json)  
Priority queue: [`reconciliation_priority_queue.md`](reconciliation_priority_queue.md)

---

## 0. Executive verdict

The **real current Guardian runtime** is:

```
START_ELYSIA_UNIFIED.bat
  → Start_Elysia_Backend.cmd
      → ensure_ollama_running.ps1
      → ensure_openclaw_running.ps1
      → elysia.py (UnifiedElysiaSystem)
          → elysia_sub_guardian → GuardianCore (project_guardian/core.py)
          → ThreadingHTTPServer :8888
          → Flask UIControlPanel :5000
  → wait_for_elysia_backend.py
  → elysia_interface.py --attach-only
```

`main` is a **May 2026 baseline** (507 Python files). The reconciliation branch is **strictly ahead** (207 commits, 900 Python files) and contains both **newer live features** and a large amount of **legacy / stub / generated / archival** material. It must **not** be merged wholesale.

Three composition roots still coexist:

| Root | Entry | Role |
|------|-------|------|
| **UnifiedElysiaSystem** | `elysia.py` via desktop bats | **LIVE_CANONICAL** |
| **SystemOrchestrator** | `python -m project_guardian` | **LEGACY** (docs still advertise; bats do not) |
| **ElysiaRuntime** | `python -m elysia run` | **NEWER_VARIANT** parallel package stack |

---

## 1. Real boot paths

### 1.1 Primary live (desktop)

| Step | Artifact | Status |
|------|----------|--------|
| Launcher | `START_ELYSIA_UNIFIED.bat` | LIVE_CANONICAL |
| Backend | `Start_Elysia_Backend.cmd` → `python elysia.py` | LIVE_CANONICAL |
| Launch helper | `elysia_entrypoint.py` (imported, not executed) | LIVE_SUPPORTING |
| Core | `project_guardian/core.py` via `guardian_singleton` | LIVE_CANONICAL |
| Status API | `elysia.py` `ThreadingHTTPServer` `:8888` | LIVE_CANONICAL |
| Operator UI | `ui_control_panel.py` Flask `:5000` | LIVE_CANONICAL |
| Attach UI | `elysia_interface.py --attach-only` | LIVE_SUPPORTING |

### 1.2 Secondary / parallel (not desktop-primary)

| Path | Status | Notes |
|------|--------|-------|
| `python -m project_guardian` → `SystemOrchestrator` | LEGACY | README/USER_GUIDE still say this is primary |
| `python -m elysia run` → `ElysiaRuntime` → Flask `:8123` | NEWER_VARIANT | `restart_elysia_runtime.ps1` |
| `scripts/start_control_panel.ps1` → FastAPI `:8000` | LIVE_SUPPORTING | Optional workbench |
| `project_guardian/api_server.py` `:8080` | LEGACY | Orchestrator host |
| Root `startup.py` | ARCHIVE_CANDIDATE | **Absent** from live root |

### 1.3 Reachability rule

File existence ≠ live. A module is treated as live only if:

1. a primary launcher reaches it, **or**
2. `GuardianCore` / `elysia_sub_*` imports it on the unified path, **or**
3. config + capability registry clearly enable it at runtime,

…with tests strengthening confidence.

---

## 2. Branch comparison (local vs GitHub)

| Branch | Tip | Character | Runtime impact |
|--------|-----|-----------|----------------|
| `main` | `722d8e4` | Published baseline (May 2026) | Older but coherent |
| `elysia-local-reconciliation-20260909-1657` | `821570c` | Local dump: newer + legacy + archive | **Current workspace** |
| `elysia-collective-0.1-seed` | `822035a` | Autopilot/agent schemas & prompts | None on Guardian boot |
| `elysia-collective-dryrun` | `a007fe4` | Read-only triage | None |
| `codex/eai-safety-framework` | `edbbf7b` | Safety lineage (partly merged to main) | Selective |
| `codex/limited-live-activation-wrapper` | `3223ebb` | Live-activation designs/experiments | Selective / gated |
| `codex/autonomy-stale-meta-fix` | `f08914d` | 0 files changed vs main tip | N/A |
| `autopilot-004-*` | various | Dispatcher/verifier contracts | Collective, not core boot |

### Features on reconciliation but **not** on `main`

High-value newer functioning code (PORT_FROM_LOCAL candidates):

- `project_guardian/context_pipeline/`
- `project_guardian/openclaw_adapter.py` + `config/openclaw.json`
- `project_guardian/mcp_capability.py` + `mcp_stdio_bridge.py`
- `project_guardian/autonomy_antiloop.py` (+ dry-run/log-health helpers)
- `elysia_entrypoint.py`
- `project_guardian/brain/` (EXPERIMENTAL — do not treat as canonical yet)
- `project_guardian/governance/` + `live_action_*.py` (gated; DEFER enabling)
- Large `ui_control_panel.py` growth
- Desktop toggle/stop launchers and OpenClaw/Ollama ensure scripts

### On `main` and still live on reconciliation

- `GuardianCore`, mutation/trust/memory, bounded browser, WebScout, ArchitectCore, ToolRegistry (core), consensus, creativity DreamEngine

### Collective branches

`elysia_collective_seed/` is **PROPOSAL_ONLY** process tooling (schemas, agent roles, autopilot state machine). It is **not** a competing Guardian runtime. Constitution/governance questions are out of scope for this mapper.

---

## 3. Subsystem map and classifications

Status vocabulary: `LIVE_CANONICAL` | `LIVE_SUPPORTING` | `EXPERIMENTAL` | `NEWER_VARIANT` | `LEGACY` | `SUPERSEDED` | `DUPLICATE` | `PARTIAL` | `STUB` | `GENERATED` | `PROPOSAL_ONLY` | `ARCHIVE_CANDIDATE` | `UNIQUE_RECOVERY_CANDIDATE` | `UNKNOWN`

Action vocabulary: `KEEP_CURRENT` | `PORT_FROM_LOCAL` | `MERGE_SELECTED_PARTS` | `REWRITE` | `ARCHIVE` | `DEFER`

### 3.1 Guardian core

| Field | Value |
|-------|-------|
| Canonical | `project_guardian/core.py` (+ `guardian_singleton.py`) |
| Status | LIVE_CANONICAL |
| Action | KEEP_CURRENT |
| Confidence | 0.96 |
| Alternatives | `guardian_layer.py` LIVE_SUPPORTING; `core_modules/*` LEGACY |

### 3.2 Elysia loop / runtime

| Field | Value |
|-------|-------|
| Canonical (Guardian path) | `elysia_loop_core.py` |
| Supporting | `runtime_loop_core.py` (fallback from `elysia_sub_runtime_loop`) |
| Parallel | `elysia/runtime.py` NEWER_VARIANT |
| Legacy try-first | `core_modules/.../elysia_runtime_loop.py` LEGACY |
| Action | MERGE_SELECTED_PARTS (document which loop is authoritative; stop preferring abandoned core loop) |
| Confidence | 0.90 |

### 3.3 Orchestrator

| Field | Value |
|-------|-------|
| Canonical for live autonomy | **GuardianCore** itself |
| SystemOrchestrator | LEGACY secondary composition root |
| `orchestration/` | LIVE_SUPPORTING pipelines |
| `brain/` | EXPERIMENTAL (reconciliation-only) |
| Action | KEEP_CURRENT for GuardianCore; DEFER brain promotion |
| Confidence | 0.88 |

### 3.4 Memory / timeline / context / vector

| Subsystem | Canonical | Status | Action | Confidence |
|-----------|-----------|--------|--------|------------|
| Memory | `memory.py` + `memory_vector.py` | LIVE_CANONICAL | KEEP_CURRENT | 0.92 |
| Timeline | `elysia_loop_core.TimelineMemory` | LIVE_CANONICAL | MERGE_SELECTED_PARTS vs SQLite twin | 0.85 |
| Timeline alt | `timeline_memory.py` (SQLite) | DUPLICATE | used by SystemOrchestrator | — |
| Context pipeline | `context_pipeline/` | NEWER_VARIANT / live-wired | **PORT_FROM_LOCAL** | 0.91 |
| Vector | `memory_vector.py` | LIVE_CANONICAL | KEEP_CURRENT | 0.86 |

**Note:** Two different classes share the name `TimelineMemory`. This is a top consolidation hazard.

### 3.5 DreamEngine

| Implementation | Status | Wired by |
|----------------|--------|----------|
| `creativity.DreamEngine` | **LIVE_CANONICAL** | GuardianCore `self.dreams` |
| `dream_engine.py` (reflective) | NEWER_VARIANT | SystemOrchestrator if `enable_dream_engine` (default **False**) |
| core_modules dream_engine | STUB (32 lines) | legacy API only |

**Action:** KEEP_CURRENT for creativity; optionally MERGE reflective features later. Do not confuse names.

### 3.6 ConsensusEngine

| Canonical | `project_guardian/consensus.py` LIVE_CANONICAL |
| Core stub | `core_modules/.../consensus_engine.py` STUB (14 lines) |
| Action | KEEP_CURRENT |
| Tests | Weak dedicated coverage (inventory only) — confidence 0.90 on wiring, lower on regression safety |

### 3.7 CapabilityRegistry / tool registry

| Capability | `capability_registry.py` + `capability_execution.py` | LIVE_CANONICAL |
| Tool/TaskRouter (boot) | **core** `ai_tool_registry.py` | LIVE_CANONICAL via `elysia_sub_modules` |
| Tool engine (PG) | `ai_tool_registry_engine.py` | NEWER_VARIANT dual |
| Action | MERGE_SELECTED_PARTS (unify registries without breaking TaskRouter tests) |

### 3.8 Agent manager

No real `AgentManager` on the live path. Roles filled by `ModuleRegistry` (two copies), `CapabilityRegistry`, and `elysia/agents/*`. Core `agent_manager.py` is a **STUB** with zero importers → ARCHIVE.

### 3.9 Prompts

Canonical: `project_guardian/prompts/` + `module_prompt_registry.py`.  
Supporting: `prompt_evolver.py`, context-pipeline packet builder.  
Newer: `prompt_evolution.py` (reconciliation).  
Action: KEEP_CURRENT; PORT prompt_evolution selectively.

### 3.10 Implementer

| Path | Status | Boot on desktop? |
|------|--------|------------------|
| `project_guardian/implementer/` | LIVE_SUPPORTING | **No** (SystemOrchestrator) |
| `elysia/agents/implementer.py` | NEWER_VARIANT | **No** (ElysiaRuntime) |

**Action:** DEFER canonical choice until composition-root policy is fixed. Both are real, tested implementations for different stacks.

### 3.11 Mutation / validator / recovery / approvals / trust

| Role | Canonical | Notes |
|------|-----------|-------|
| Safe apply | `mutation.py` | LIVE_CANONICAL on GuardianCore |
| Proposal engine | `mutation_engine.py` | LIVE_SUPPORTING; wraps SafeMutationEngine |
| Core mutation | core `mutation_engine.py` | SUPERSEDED / BROKEN |
| Validator | `ai_mutation_validator.py` | LIVE_SUPPORTING |
| Recovery | `recovery_vault.py` | LIVE_SUPPORTING |
| Approvals | ReviewQueue + ApprovalStore | LIVE_CANONICAL |
| Deprecated | `mutation.review_with_gpt` / `approve_last` | SUPERSEDED (intentionally disabled) |
| Trust/safety | trust\* + safety + eai_safety + guardian_layer | LIVE_CANONICAL |
| Governance extras | `governance/`, `live_action_*` | NEWER_VARIANT — PORT carefully, do not enable live |

### 3.12 Bounded browser / WebScout

| Bounded browser | `bounded_browser/` | LIVE_CANONICAL (also on main) |
| WebScout | `webscout_agent.py` | LIVE_CANONICAL |
| Wrapper | `elysia/agents/webscout.py` | LIVE_SUPPORTING |
| Action | KEEP_CURRENT |

### 3.13 MCP

`mcp_capability.py` + `mcp_stdio_bridge.py` — **NEWER_VARIANT**, boot-reachable via CapabilityRegistry, fail-closed without allowlist. **PORT_FROM_LOCAL.**

### 3.14 APIs / UI

| Surface | Port | Status |
|---------|------|--------|
| Status/OpenAI-compat in `elysia.py` | 8888 | LIVE_CANONICAL |
| Flask control panel | 5000 | LIVE_CANONICAL (**PORT** large local growth) |
| FastAPI workbench | 8000 | LIVE_SUPPORTING |
| ElysiaRuntime API | 8123 | NEWER_VARIANT |
| api_server | 8080 | LEGACY |
| core `elysia_api.py` | — | SUPERSEDED / broken |

### 3.15 Autonomy / anti-loop / live execution

| Piece | Status | Action |
|-------|--------|--------|
| GuardianCore autonomy selector | LIVE_CANONICAL | KEEP_CURRENT |
| `autonomy_antiloop.py` | NEWER_VARIANT, wired | **PORT_FROM_LOCAL** |
| `mission_autonomy.py` | LIVE_SUPPORTING | KEEP_CURRENT |
| `live_action_*` | NEWER_VARIANT, fail-closed | **DEFER** (do not enable) |
| `brain/live_execution_runtime.py` | EXPERIMENTAL | DEFER |

### 3.16 Logging / config / Ollama / OpenClaw

| Subsystem | Canonical | Status | Action |
|-----------|-----------|--------|--------|
| Logging | PG `logging_config` + audit modules | LIVE_CANONICAL | KEEP_CURRENT |
| Config | `config/*` + `elysia_config.py` | LIVE_CANONICAL | KEEP_CURRENT |
| Ollama | `ollama_model_config` + ensure script | LIVE_CANONICAL | KEEP_CURRENT |
| OpenClaw | `openclaw_adapter.py` | NEWER_VARIANT | **PORT_FROM_LOCAL** |
| OpenClaw stub worker | intentional STUB | keep for tests | KEEP_CURRENT as stub |

### 3.17 Unique live modules still under `core_modules/`

These have **no PG twin** and are reachable from unified boot via `sys.path`:

| Module | Status | Action |
|--------|--------|--------|
| `architect_core.py` | LIVE_CANONICAL | KEEP_CURRENT; later package under PG |
| `ai_tool_registry.py` | LIVE_CANONICAL (dual with PG engine) | MERGE_SELECTED_PARTS |
| `fractalmind.py` | LIVE_SUPPORTING | KEEP_CURRENT |
| `harvest_engine.py` | LIVE_SUPPORTING | KEEP_CURRENT |
| `hestia_bridge.py` | LIVE_SUPPORTING / UNIQUE_RECOVERY_CANDIDATE | KEEP_CURRENT; scrub hardcoded foreign paths |
| `identity_mutation_verifier.py` | LIVE_SUPPORTING | KEEP_CURRENT |
| `external_program_bridge.py` | UNIQUE_RECOVERY_CANDIDATE (unwired) | DEFER review |

---

## 4. False implementations (look complete / are not)

| Path | Classification | Evidence |
|------|----------------|----------|
| `core_modules/.../agent_manager.py` | STUB / DEAD | ~18 lines; zero importers |
| `core_modules/.../consensus_engine.py` | STUB / SUPERSEDED | ~14 lines; PG consensus is live |
| `core_modules/.../dream_engine.py` | STUB / TOY | ~32 lines hardcoded dreams |
| `core_modules/.../mutation_engine.py` | BROKEN_LEGACY | missing `sandbox`; rank API mismatch |
| `core_modules/.../memory_core.py` | TOY / SUPERSEDED | ~46-line JSON log |
| `core_modules/.../elysia_api.py` | LEGACY_BROKEN | calls nonexistent `approve_last` |
| Many core identity/intent/quantum/etc. | STUB / DEAD | 9–16 line print toys |
| `organized_project/**` | GENERATED / ARCHIVE | Placeholder modules; path bombs; forbidden on `sys.path` |
| `mutation.py` GPT review methods | SUPERSEDED | Explicitly DISABLED |
| `scripts/openclaw_stub_worker.py` | Intentional STUB | Documented stand-in |
| Root `file_a.py` / `safe.py` | JUNK | trivial prints |
| `proposals/**/todos.md` | GENERATED / PROPOSAL_ONLY | Template TODOs |
| `docs/*_DESIGN_PROPOSAL.md` | PROPOSAL_ONLY | Design without implementation |
| `REPORTS/_artifact_*.txt` | GENERATED operational | Smoke/log artifacts |
| `elysia_collective_seed/**` | PROPOSAL_ONLY | Specs/schemas, not Guardian engines |
| `extracted_modules/**` | LOOKS_REAL_BUT_MOSTLY_UNUSED | Comment references only |
| `_archived/**`, `old modules/**`, `mesh/**` | ARCHIVE_CANDIDATE | Historical dumps |

**Documentation is not capability.** README claiming `python -m project_guardian` as primary entry is **stale** relative to desktop launchers.

---

## 5. Worst duplications

1. **Three composition roots:** GuardianCore / SystemOrchestrator / ElysiaRuntime  
2. **Two DreamEngines** (creativity vs reflective) + core toy  
3. **Two MutationEngines** (safe `mutation.py` vs proposal `mutation_engine.py`) + broken core copy  
4. **Two TimelineMemory classes** (in-memory loop-core vs SQLite module)  
5. **Two ModuleRegistries**  
6. **Two tool registries** (core TaskRouter vs PG `ai_tool_registry_engine`)  
7. **Two WebScout entrypoints** (PG agent vs elysia wrapper — wrapper is OK)  
8. **Two Implementers** (PG package vs elysia agent)  
9. **Two logging_config packages**  
10. **Two control panels** (Flask `:5000` vs FastAPI `:8000`) plus Runtime API `:8123`

---

## 6. Unique recovery candidates

Worth preserving / packaging deliberately (not stubs):

1. **ArchitectCore** — already live; move under `project_guardian` to end `sys.path` hacks  
2. **FractalMind / HarvestEngine / identity_mutation_verifier** — live unique core modules  
3. **Hestia bridge** — unique; verify path hardcoding before wider use  
4. **OpenClaw adapter + MCP + context pipeline + antiloop** — newer local value not on `main`  
5. **Reflective `dream_engine.py` features** not present in creativity DreamEngine — selectively merge after naming cleanup  
6. **`external_program_bridge.py`** — unwired but non-trivial; review before archive  
7. **Collective seed schemas** — process tooling only; keep on collective branches, not forced into core runtime

Low value to recover: enhanced_* migration artifacts, toy engines, organized_project placeholders.

---

## 7. Archive candidates (after verification)

Safe to stage for archive **after** confirming no hidden importers:

- `organized_project/` (entire tree)  
- core toy engines listed in §4  
- `_archived/`, `old modules/`, `mesh/` scrap  
- broken core `elysia_api.py` / `mutation_engine.py` / `self_evolver.py`  
- root junk `file_a.py`, `safe.py`  
- generated proposal TODO shells under `proposals/`  
- operational `REPORTS/_artifact_*` noise (keep curated maps)

Do **not** archive without import grep + test run: `architect_core`, `ai_tool_registry`, `fractalmind`, `harvest_engine`, `hestia_bridge`.

---

## 8. Highest-risk consolidation areas

1. **Mutation stack** — wrong import breaks apply/review/approvals  
2. **TimelineMemory name collision** — memory persistence regressions  
3. **ToolRegistry dual** — TaskRouter tests + `elysia_sub_modules` path order  
4. **Removing `sys.path` core_modules insert** — can silently break Architect/Harvest/FractalMind  
5. **UI control panel** — large local delta; regressions hit operators immediately  
6. **Autonomy + antiloop + OpenClaw ranking** — behavioral loops, not just imports  
7. **Live execution enablement** — fail-closed by design; enabling is a governance decision  
8. **Wholesale reconciliation merge** — will reintroduce stubs and archives into `main`

---

## 9. Recommended canonical core (summary)

**KEEP / treat as live spine:**

- Launchers → `elysia.py` → `GuardianCore`
- `mutation.py` + ReviewQueue/ApprovalStore
- `consensus.py`, `creativity.DreamEngine`, `elysia_loop_core`, memory/vector
- `capability_registry` + bounded browser + WebScout
- `architect_core` (core_modules, for now)
- Flask UI panel + status `:8888`
- Ollama helpers

**PORT_FROM_LOCAL onto a curated integration branch (not wholesale):**

- context_pipeline  
- openclaw_adapter  
- mcp_*  
- autonomy_antiloop (+ related guards)  
- selected UI panel improvements  
- elysia_entrypoint attach-only behavior  
- ensure_*.ps1 launcher hardening  

**DEFER:**

- brain/ as canonical  
- live_action enablement  
- choosing single Implementer  
- collective constitution questions  

**ARCHIVE (staged):**

- organized_project, core toys, scrap trees  

---

## 10. Evidence sources used

- Launcher files (`.bat` / `.cmd` / `.ps1`)  
- Import graphs from `elysia.py`, `elysia_sub_*`, `GuardianCore`  
- `git` branch tips, `main...HEAD` file adds, ancestry (207 ahead / 0 behind)  
- Module line counts and stub markers  
- Test file hit counts (scoped away from `organized_project`)  
- Existing guardrail: `project_guardian/tests/test_stub_guardrails.py`  

Where evidence was incomplete, status was left as EXPERIMENTAL / DEFER / UNKNOWN rather than forced.

---

*End of canonical runtime map.*
