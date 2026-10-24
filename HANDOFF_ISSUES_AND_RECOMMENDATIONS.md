# Elysia / Project Guardian — Issues & Recommendations Handoff

**Audience:** Codex, ChatGPT, or other coding agents assisting with fixes and architecture improvements.  
**Date:** 2026-10-24 (America/New_York)  
**Repo:** https://github.com/MsElysia/Elysia  
**Related PR (partial fixes already in flight):** https://github.com/MsElysia/Elysia/pull/160 (`cursor/restore-module-activity-bbec`)  
**Environment tested:** Linux cloud agent (no USB `F:` drive, no `API keys/` folder, no Ollama, no OpenAI key)

Use this as a working backlog. Prefer **small, testable PRs**. Do not mix unrelated refactors with boot-critical fixes.

---

## How to verify after changes

```bash
pip install -r requirements.txt
pip install openai requests flask-socketio pyttsx3 watchdog  # commonly missing from root requirements
# Linux TTS backend for pyttsx3:
#   sudo apt-get install -y espeak-ng

ELYSIA_FORCE_FULL_BACKEND=1 PYTHONUNBUFFERED=1 python3 elysia.py
# Status API: http://127.0.0.1:8888/health and /status
# UI:        http://127.0.0.1:5000

python3 elysia_health_check.py
python3 scripts/test_chat.py "hello"
python3 quick_system_test.py
pytest tests/test_external_storage_fallback.py \
       project_guardian/tests/test_guardian_layer_lock.py \
       project_guardian/tests/test_startup_smoke.py -q
```

Healthy `/status` should show: `running: true`, `guardian_core`, `runtime_loop`, `architect_core` true.

---

## P0 — Boot / import blockers (ship or merge first)

### P0.1 Missing modules on `main` (import crash)

**Symptom:** `from project_guardian import GuardianCore` / `get_guardian_core()` fails before any UI/API comes up.

**Root cause:** `project_guardian/core.py` imports symbols that are **not on `main`**:

| Import | Status on `main` |
|--------|------------------|
| `project_guardian.module_activity` (`mark_module_activity`, `get_module_last_activity`, `activity_age_minutes`) | **Missing file** |
| `log_autonomy_routine`, `log_autonomy_exploration_routine` from `planner_readiness` | **Missing defs** (file exists, helpers absent) |

**Prior art:** commits `ec00e7d`, `5268c66`, `7fc5063`, `d2a551d`, and PR #160 restore these.

**Recommendation:**

1. Merge PR #160 (or cherry-pick the restore commits) onto `main` immediately.
2. Add `tests/test_project_guardian_import.py` (existed on fix branches) as a **required CI gate** so missing helpers cannot regress.
3. Policy: never land `core.py` import changes without the defining module in the same PR.

---

### P0.2 GuardianLayer fingerprint hang on Linux

**Symptom:** Boot freezes after `[OK] EAI safety framework initialized`; process sits in `futex_wait` / never reaches adapters.

**Root cause:** `GuardianLayer._generate_system_fingerprint()` used `platform.platform()` / `platform.processor()`, which can hang on some Linux hosts during libc/uname probing.

**Fix direction (already in PR #160):**

- Fingerprint with lightweight APIs only: `system`, `release`, `machine`, `node`, cwd, user, python paths.
- Bound SMTP (`smtplib.SMTP(..., timeout=10)`) so fingerprint-change email cannot hang init.
- Move `logger = logging.getLogger(__name__)` **above** the SMTP import try/except (old code referenced `logger` before definition on ImportError).

**Recommendation:**

1. Keep the lightweight fingerprint; do **not** reintroduce `platform.platform()` / `platform.processor()` without a hard timeout (e.g. subprocess with 1s timeout, never call from `__init__` without it).
2. Add a unit test that mocks/patches and asserts fingerprint generation completes under a short wall-clock budget.
3. Consider computing fingerprint **after** status HTTP is up (deferred), so identity checks never block boot.

---

### P0.3 Windows drive letters become `./F:` on POSIX

**Symptom:** Config `external_drive: "F:\\"` creates `/workspace/F:/ProjectGuardian/...` and is treated as “valid external storage.”

**Root cause:** `normalize_storage_root("F:\\")` → `"F:"`; on Linux `Path("F:")` is **cwd-relative**. Once that dir exists, validation succeeds.

**Fix direction (PR #160):** skip Windows drive-letter roots on non-`nt`; reject non-absolute roots on POSIX; regression test in `tests/test_external_storage_fallback.py`.

**Recommendation:**

1. Keep POSIX rejection of `F:`, `F:\`, `F:/`.
2. Add `.gitignore` entries for accidental `F:/`, `G:/`, etc., if any remain in the tree.
3. Document that Linux should use `/media/...`, `/mnt/...`, or marker-drive discovery (`ELYSIA_MEMORY` / `.elysia_memory`), not Windows letters in `config/external_storage.json` for cross-platform checkouts.
4. Ship a sample `config/external_storage.linux.json` or env-overridable path.

---

### P0.4 Hard dependency on `pyttsx3` at import time

**Symptom:** Entire Guardian stack fails with `No module named 'pyttsx3'` even when voice is unused.

**Location:** `project_guardian/external.py` — top-level `import pyttsx3`.

**Recommendation:**

1. Lazy-import inside `VoiceThread.__init__` / `speak()`.
2. If init fails (no espeak), set `engine = None` and continue (already partially done after import).
3. Move `pyttsx3` to optional extras: `requirements-optional.txt` or `.[voice]`.
4. Root `requirements.txt` should list critical runtime deps; do not require TTS for API-only deploys.
5. On Linux CI images, either install `espeak-ng` or skip voice tests.

---

### P0.5 Broken / non-installable `project_guardian/requirements.txt`

**Symptom:** `pip install -r project_guardian/requirements.txt` fails.

**Examples of invalid pins (stdlib / fake packages):**

- `sqlite3>=3.35.0`
- `asyncio>=3.4.3`
- `dataclasses>=0.6`
- `pathlib>=1.0.1`
- `uuid>=1.30`
- `hashlib>=3.2`

**Recommendation:**

1. Delete stdlib entries; keep only real PyPI packages.
2. Align **one** canonical requirements source: prefer root `requirements.txt` + optional extras; deprecate duplicate guardian requirements or generate it from the same lockfile.
3. Add CI job: `pip install -r requirements.txt` must succeed on Linux + Windows.

---

## P1 — Runtime / feature gaps found in live testing

### P1.1 Chat depended on missing `organized_project/launcher`

**Symptom:** `/chat` returned `Income generator or API manager not available` even when the rest of the system was healthy.

**Root cause:** `elysia_sub_income.py` loads `APIManager` from `organized_project/launcher/`, which is **not in this repo checkout**. Cloud chat only went through that manager.

**Fix direction (PR #160):**

- Direct `openai.OpenAI` from `OPENAI_API_KEY` / OpenRouter env.
- Offline status reply when no Ollama and no cloud keys.

**Recommendation:**

1. Treat `project_guardian/api_key_manager.py` (or a thin `LLMClient`) as the **canonical** cloud client for chat, mutations, WebScout — not income launcher.
2. Either vendor `organized_project/launcher` into the repo or delete dead code paths that assume it.
3. Document required env vars in README: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, optional `OLLAMA_*`.
4. Add integration test: with mocked OpenAI client, `/chat` returns reply without income generator.

---

### P1.2 API keys path is Windows-centric and often absent

**Location:** `load_api_keys.py` → `API keys/` with exact filenames like `chat gpt api key for elysia.txt`.

**Problems:**

- Folder name has a space; easy to omit from git (and should stay out of git for secrets).
- No keys ⇒ degraded income, WebScout simulated mode, offline chat.
- Filename matching is brittle.

**Recommendation:**

1. Prefer env vars / OS secret store / encrypted secrets manager already in the project.
2. Keep file-based loader as optional Windows convenience; support `.env` via `python-dotenv` for local/dev.
3. Never commit real keys; provide `API keys/.gitkeep` + example names only.
4. On startup, print a single clear “LLM backends available: …” matrix (OpenAI / OpenRouter / Ollama / offline).

---

### P1.3 Dual product surfaces: `elysia.py` vs `elysia/` package vs `run_elysia.py`

**Observation:**

- Main production path: `elysia.py` + `elysia_sub_*.py` (status on **8888**, UI on **5000**).
- Also: `elysia/` package (`elysia/api`, `elysia/shell.py` using `/api/chat`).
- Also: `run_elysia.py` → Guardian + API on **8080**.
- Docs disagree (README says API 8080; quick start emphasizes UI 5000; health check defaults to 8888).

**Recommendation:**

1. Declare **one** supported entrypoint in README (recommend: `python elysia.py` / `run_elysia_unified.py`).
2. Mark alternate launchers as deprecated wrappers or delete after migration.
3. Single port map in `elysia_config.py` only; all docs/scripts import from there.
4. Add a `python -m elysia doctor` (or extend health check) that prints ports, lock file, backends, and component flags.

---

### P1.4 Backend lock / zombie process UX

**Symptom:** Restart refused: “Existing backend process PID …” while `/status` shows `running: false` or port is dead; stale `.elysia_backend.lock`.

**Recommendation:**

1. On lock acquire: if PID is dead **or** `/health` fails, delete lock and continue.
2. If PID alive but `running: false` for N seconds, treat as crashed and allow `--force` restart.
3. Document: `rm .elysia_backend.lock` and `pkill -f 'python3 elysia.py'` for recovery.
4. `POST /shutdown` should always clear the lock (verify).

---

### P1.5 God-object `GuardianCore` (`core.py` ~9k lines)

**Problems:** Hard to test, review, and reason about; import graph pulls voice, UI, finance, mutations, adversarial learning, etc. into every boot.

**Recommendation (incremental, not big-bang rewrite):**

1. Extract cohesive modules already partially present: startup phases, chat/LLM, autonomy loop, UI wiring, financial ops.
2. Keep `GuardianCore` as a thin facade / composition root.
3. Enforce “Phase A minimal boot” strictly: status HTTP + memory stub first; defer embeddings, WebScout, income, adversarial cycles.
4. Add architectural lint or CODEOWNERS for `core.py` size growth (e.g. fail CI if file grows without extraction plan).

---

### P1.6 `EnhancedMemoryCore` / FAISS / embeddings mismatch

**Symptoms during test:**

- Warning: unexpected keyword (fixed in PR #160 via `defer_embeddings`).
- FAISS / sentence-transformers often missing → hash embeddings / basic memory.
- Vector path and JSON path can diverge.

**Recommendation:**

1. Keep `defer_embeddings` / `lazy_json` / `lazy_vector` as first-class, documented kwargs.
2. Make FAISS + sentence-transformers **optional extras**; boot must succeed without them.
3. Surface vector degraded state clearly in `/status` (`vector_mode: faiss|hash|disabled`).
4. Avoid silent vector loss on embedding `None` (see older ADDITIONAL_ISSUES / bandaid docs).

---

## P2 — Correctness, resources, and security

### P2.1 SQLite connections without context managers

**Locations (still present in places):**

- `project_guardian/timeline_memory.py`
- `project_guardian/error_handler.py`
- `project_guardian/orchestration/telemetry/sqlite_store.py`
- (Some `elysia_loop_core.py` paths already use `with sqlite3.connect`)

**Risk:** Leaks, “database is locked,” corruption under concurrency.

**Recommendation:** Always `with sqlite3.connect(...) as conn:`; set `timeout=`; use WAL mode for multi-reader; one writer policy.

---

### P2.2 Broad `except Exception` swallowing

Widespread across `core.py`, monitoring, UI. Many log correctly; some convert failures into “WARN continuing” and leave half-initialized state (`running: false` with components true was observed once).

**Recommendation:**

1. Distinguish **fatal** vs **degraded** init failures; set explicit component health enums.
2. `/health` should be `503` if critical components failed, not `200` with mixed flags.
3. Prefer typed errors for trust denial, missing keys, network timeouts.

---

### P2.3 Local-only security assumptions

Status/chat on `127.0.0.1` with optional `ELYSIA_API_TOKEN`. Mutation and exec capabilities exist in the tool registry.

**Recommendation:**

1. Default deny for exec / mutation unless trust policy + explicit enable env.
2. Require token for `/chat` and `/shutdown` in any non-dev profile.
3. Audit `elysia_builtin_exec` and bounded browser for sandboxing.
4. Never log API keys; scrub memory dumps.

---

### P2.4 Encoding / Windows file I/O

Prior finding: some writes omit `encoding="utf-8"` (e.g. historical WebScout summary path). Prefer utf-8 everywhere; use `pathlib` and newline=`\n` for cross-platform.

---

### P2.5 Secrets and config sprawl

Multiple config files under `config/` (autonomy, mistral, external storage, trust policies). Easy to get conflicting “source of truth.”

**Recommendation:** Document a config precedence order: env > `config/*.json` > defaults. Validate at startup (`ConfigValidator`) and fail fast on contradictory flags.

---

## P3 — Product / DX improvements

### P3.1 Test strategy

- Many tests exist (`tests/`, `project_guardian/tests/`), but full suite is heavy and environment-sensitive (Ollama, USB, keys, Windows paths).
- Prefer a documented **smoke tier** for CI:

```text
import guardian
external storage POSIX
guardian layer fingerprint budget
startup smoke
health endpoint (with test client or short-lived server)
```

### P3.2 Observability

- Good: rotating `elysia_unified.log`, status JSON, startup verification summary.
- Improve: structured JSON logs option; single `startup_phase` timeline; export Prometheus metrics already partially listed in guardian requirements.

### P3.3 Dependency hygiene

| Need | Package |
|------|---------|
| Core API/UI | flask, flask-cors, flask-socketio |
| HTTP | httpx or requests (pick one primary) |
| LLM | openai |
| Optional voice | pyttsx3 + espeak-ng |
| Optional vectors | faiss-cpu, sentence-transformers, numpy |
| Optional watch | watchdog |

Root `requirements.txt` currently omits `openai` / `pyttsx3` while guardian subtree expects them — **unify**.

### P3.4 Documentation drift

Update README / QUICK_START / API_REFERENCE to match real ports (8888 status, 5000 UI) and the single entrypoint. Archive obsolete bat-only instructions or mark Windows-only.

### P3.5 Cross-platform memory roots

USB marker discovery already exists in `elysia_config.py`. Prefer that over hard-coded `F:\` in committed `config/external_storage.json` for multi-OS contributors.

---

## Suggested work order for Codex / ChatGPT

1. **Merge/stabilize PR #160** — import restores, fingerprint hang, POSIX drive skip, chat env/offline fallback, `defer_embeddings`.
2. **CI smoke gate** — import test + external storage POSIX test + guardian layer lock/fingerprint + startup smoke.
3. **Lazy `pyttsx3` + clean requirements** — boot without voice; pip install must succeed.
4. **Canonical LLM client** — remove `organized_project/launcher` hard dependency; wire `api_key_manager` / env clients everywhere.
5. **Backend lock healing** — dead PID / dead health auto-clear.
6. **SQLite context managers** — remaining call sites.
7. **Health semantics** — accurate `running` + HTTP status codes for degraded boots.
8. **Split `core.py`** — extract modules behind facade (multi-PR).
9. **Docs + config samples** — Linux/Windows paths, env vars, one entrypoint.

---

## Acceptance criteria (definition of done for “Elysia runs”)

On a clean Linux VM **without** USB, **without** API key files, **without** Ollama:

- [ ] `pip install -r requirements.txt` succeeds (no stdlib fake deps).
- [ ] `ELYSIA_FORCE_FULL_BACKEND=1 python3 elysia.py` reaches “Status endpoint” in &lt; ~30s.
- [ ] `GET /health` → ok, `running: true`, guardian/memory checks true.
- [ ] `GET /status` → architect + guardian + runtime_loop true.
- [ ] `GET http://127.0.0.1:5000/` → 200.
- [ ] `POST /chat` returns a non-empty `reply` (offline status is OK).
- [ ] No `F:` / `G:` directories created under the repo.
- [ ] Smoke pytest tier green in CI.

With `OPENAI_API_KEY` set:

- [ ] `/chat` returns a model reply (not only offline template).

---

## Context for agents: what “good” looks like

- Prefer **degraded but running** over **hang or crash**.
- Prefer **env-based secrets** over committed key files.
- Prefer **absolute POSIX paths** and marker drives over Windows letters in shared config.
- Prefer **small PRs with tests** over drive-by refactors of `core.py`.
- Do not reintroduce boot-path network/SMTP/platform probes without timeouts.

---

## Quick file map

| Area | Primary files |
|------|----------------|
| Entrypoint / status HTTP | `elysia.py`, `elysia_config.py`, `elysia_sub_*.py` |
| Core orchestration | `project_guardian/core.py`, `guardian_singleton.py` |
| Fingerprint hang | `project_guardian/guardian_layer.py` |
| External storage | `project_guardian/external_storage.py`, `config/external_storage.json` |
| Chat / LLM route | `elysia.py` (`chat_with_llm`), `unified_llm_route.py`, `api_key_manager.py` |
| Voice hard import | `project_guardian/external.py` |
| Keys loader | `load_api_keys.py`, `elysia_sub_apikeys.py` |
| Income / missing launcher | `elysia_sub_income.py` → `organized_project/launcher` (absent) |

---

*End of handoff. Update this file as items are closed; link PRs next to each P0/P1 item.*
