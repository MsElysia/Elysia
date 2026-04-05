# Boot memory map: why startup hits high memory pressure and auto-cleanup

## Summary

Startup loads **memory records**, **FAISS index**, and **metadata** **eagerly** during `GuardianCore.__init__`. That raises process RSS. Two separate mechanisms then trigger cleanup:

1. **Count-based:** `_check_and_cleanup_memory()` runs at the end of `_initialize_system()`. If `len(memory_log) > memory_cleanup_threshold` (default 3500), it runs consolidation immediately (“startup cleanup”).
2. **RSS-based:** `ResourceMonitor` starts a thread that calls `check_resources()` **once immediately**, then every 30s. If system memory use exceeds the configured limit (default 80%), it invokes the registered callback → `_on_memory_limit_exceeded` → `_perform_cleanup(2000, system_memory_high=True)`.

So “startup immediately hits high memory pressure and auto-cleanup” comes from: **eager load of all memory + FAISS + metadata** → high RSS and/or high memory count → one or both of the above triggers fire right after init.

---

## Boot sequence (memory-relevant)

| Order | Step | File:location | What is loaded |
|-------|------|---------------|----------------|
| 1 | `GuardianCore.__init__` starts | core.py:262 | config, paths, API keys, _validate_configuration |
| 2 | **Memory** (vector enabled) | core.py:151–159 | `EnhancedMemoryCore(json_filepath=..., enable_vector=True, vector_config=...)` |
| 2a | ↳ **MemoryCore** (inside EnhancedMemoryCore) | memory_vector.py:410 → memory.py:55 | **EAGER:** `MemoryCore(json_filepath)` → `self.load()` loads **full JSON** into `memory_log` (memory.py:414–422). |
| 2b | ↳ **VectorMemory** (inside EnhancedMemoryCore) | memory_vector.py:416–421 | **EAGER:** `VectorMemory(...)` in __init__ calls `_init_index()` (memory_vector.py:68–84) → **FAISS index** loaded from disk if `index_path` exists; else new empty index. Then `_load_metadata()` (86–97) → **full metadata JSON** into `self.metadata`. |
| 3 | TrustMatrix, ReviewQueue, ApprovalStore, MutationEngine, Safety, Rollback, TaskEngine, ConsensusEngine | core.py:166–185 | EAGER: all created and hold refs to `self.memory`. |
| 4 | Reflector, SystemMonitor | core.py:188–189 | EAGER. |
| 5 | **ResourceMonitor** + start_monitoring | core.py:194–227 | EAGER. **First `check_resources()` runs in thread immediately** (resource_limits.py:158–160). If system memory > limit (e.g. 80%), **callback fires** → `_on_memory_limit_exceeded` → `_perform_cleanup(2000, system_memory_high=True)`. |
| 6 | SecurityAuditor, ContextBuilder, DreamEngine, MemorySearch, WebReader, SubprocessRunner, AnalysisEngine, Voice, AIInteraction, Missions, Timeline, ModuleRegistry, ElysiaLoopCore, TrustEval*, PromptEvolver, FeedbackLoopCore, MemorySnapshot | core.py:227–316 | EAGER: many objects, all holding refs. |
| 7 | **UIControlPanel** (if ui_config.enabled) | core.py:319–334 | EAGER: Flask app + routes + SocketIO; **dashboard server started** if auto_start. No bulk data load; templates/JS in process. |
| 8 | _register_module_adapters, _register_core_agents | core.py:335–341 | EAGER. |
| 9 | **_initialize_system** | core.py:343–346 | memory.remember, tasks, trust, ensure_monitoring_started (heartbeat loop), _verify_startup |
| 10 | **_check_and_cleanup_memory** | core.py:426 → 1634–1682 | If `len(self.memory.memory_log) > memory_cleanup_threshold` (default 3500), runs **consolidate(max_memories=threshold, keep_recent_days=30)** immediately (“startup cleanup”). |

---

## What is eager vs lazy

| Component | Eager / Lazy | Where | Notes |
|-----------|----------------|-------|--------|
| **Memory records** | **EAGER** | memory.py:55 `self.load()` | Full `guardian_memory.json` read into `memory_log` in `MemoryCore.__init__`. |
| **FAISS index** | **EAGER** | memory_vector.py:68–84 `_init_index()` | In `VectorMemory.__init__`. If `index_path` exists, `faiss.read_index()` loads full index into RAM. |
| **Vector metadata** | **EAGER** | memory_vector.py:86–97 `_load_metadata()` | In `VectorMemory.__init__`. Full `metadata.json` loaded into `self.metadata`. |
| **MemoryCore vector search** (memory_vector_search) | **Lazy** (unless EMBED_ON_STARTUP) | memory.py:71–82 | `MemoryVectorSearch()` created at init; `_build_vector_index()` only if `EMBED_ON_STARTUP=true`, else on-demand. (Separate from EnhancedMemoryCore’s VectorMemory.) |
| **Agents / modules** | **EAGER** | core.py:166–316, plus elysia init_integrated_modules | All core components and integrated modules created during GuardianCore / Elysia init. No lazy loading of agents. |
| **Dashboard** | **EAGER** | core.py:326–332, ui_control_panel.py:1887–1903 | Flask app, routes, SocketIO, and server thread started if enabled and auto_start. No large dataset loaded; UI is templates/JS. |
| **Learning systems** | **Lazy** (sessions) / **on first use** (paths) | auto_learning.py:587–591, 32–49 | `LearningScheduler` gets `storage_path`/`chatlogs_path` via `get_learned_storage_path()` / `get_chatlogs_path()` when created; **run_learning_session** and fetches run when scheduler runs or API is used. No full learned store loaded at boot. |

---

## Heaviest steps (by memory impact)

1. **Memory records (JSON → memory_log)**  
   - **EAGER.** Single largest in-process structure: full history in `memory_log`. Scale: thousands of dicts (thought, category, priority, time, metadata).  
   - **Location:** memory.py:55 `load()`.

2. **FAISS index**  
   - **EAGER.** Full vector index loaded in `VectorMemory.__init__` if file exists. Scale: dimension × num_vectors (e.g. 1536 × N floats).  
   - **Location:** memory_vector.py:70–74 `_init_index()` → `faiss.read_index()`.

3. **Vector metadata**  
   - **EAGER.** One metadata dict per vector, loaded in full. Duplicates a subset of what’s in `memory_log` for vector-backed memories.  
   - **Location:** memory_vector.py:86–97 `_load_metadata()`.

4. **All core components and modules**  
   - **EAGER.** Dozens of objects (TrustMatrix, MutationEngine, WebReader, DreamEngine, etc.) and integrated modules created up front; all hold references to `memory` and each other.  
   - **Location:** core.py:166–316 and Elysia module init.

5. **Dashboard**  
   - **EAGER** but small: Flask app, routes, SocketIO, one server thread. No large data load.

6. **Learning systems**  
   - **Lazy** for actual learning runs and bulk data; only config/paths resolved when scheduler or API is used.

---

## Why auto-cleanup runs “immediately”

- **Count-based:** Right after `_initialize_system()`, `_check_and_cleanup_memory()` runs (core.py:426). If you have more than `memory_cleanup_threshold` (default 3500) records, consolidation runs at once. So with a large `guardian_memory.json`, you see “[Auto-Cleanup] Memory count (...) exceeds threshold (3500), performing cleanup...” right at startup.
- **RSS-based:** `ResourceMonitor.start_monitoring(interval=30)` starts a daemon thread that runs `check_resources()` **once immediately**, then every 30s (resource_limits.py:154–164). So right after all the eager loading, the first `check_resources()` can see system memory already above the limit (e.g. 80%). That triggers `_check_limit` → callback → `_on_memory_limit_exceeded` → `_perform_cleanup(2000, system_memory_high=True)` (core.py:216–224).

So both triggers can fire within the same boot: one from **memory count** and one from **system RAM**, both caused by the same eager load of memory + FAISS + metadata and the rest of init.

---

## Exact code references

| What | File | Lines |
|------|------|--------|
| Memory JSON load (eager) | memory.py | 55 `self.load()`, 414–422 `load()` |
| FAISS load (eager) | memory_vector.py | 59–62 `_init_index()`, 70–74 `faiss.read_index()` |
| Metadata load (eager) | memory_vector.py | 61 `_load_metadata()`, 86–97 |
| EnhancedMemoryCore wires both | memory_vector.py | 410–421 (MemoryCore + VectorMemory in __init__) |
| Count-based startup cleanup | core.py | 426 `_check_and_cleanup_memory()`, 1634–1649 |
| Resource monitor first check | resource_limits.py | 124–145 `start_monitoring`, 154–164 `_monitor_loop` |
| RSS callback → cleanup | core.py | 216–224 `_on_memory_limit_exceeded` |
| Heartbeat cleanup (high watermark) | monitoring.py | 101–157 (memory_count > base_threshold or system_memory_high) |
