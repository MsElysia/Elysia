# Config validation trace: max_actions_per_hour / throttle_minutes

## 1. Where values are loaded from

| Config | File | Loaded in | Fallback when file missing |
|--------|------|-----------|----------------------------|
| **autonomy** | `config/autonomy.json` | `GuardianCore._load_autonomy_config()` (core.py ~1080) | `max_actions_per_hour: 0` (line 1088) |
| **introspection** | `config/introspection.json` | `GuardianCore._load_introspection_config()` (core.py ~1166) | `throttle_minutes: 30` (line 1174) |

- **core.py**
  - `_load_autonomy_config()`: `Path(__file__).parent.parent / "config" / "autonomy.json"`; on read error or missing file returns default dict including `"max_actions_per_hour": 0`.
  - `_load_introspection_config()`: same pattern for `config/introspection.json`; default includes `"throttle_minutes": 30`.

- **config_validator.py**
  - `validate_runtime_configs(project_root)` loads the same files again: `config_dir = root / "config"`, then `_load("autonomy.json")` / `_load("introspection.json")` (lines 314–324). Used only for validation; does not feed GuardianCore.

So runtime config values are loaded from **JSON files under `config/`**; GuardianCore reads them in `_load_autonomy_config` / `_load_introspection_config` and uses them (with the fallbacks above) whenever autonomy or introspection run.

---

## 2. Where validation happens

- **Runtime configs (autonomy, introspection, auto_learning)**  
  **config_validator.py** `validate_runtime_configs(project_root)` (lines 306–377):
  - Loads `config/autonomy.json`, `config/introspection.json`, `config/auto_learning.json`.
  - **autonomy**: `max_actions_per_hour` must be int in 1–60 (lines 338–340). If not (e.g. 0): **warning** `"max_actions_per_hour={mh} invalid (use 1-60)"`.
  - **introspection**: `throttle_minutes` must be int/float in 1–120 (lines 350–352). If not (e.g. 0): **warning** `"throttle_minutes={tm} invalid (use 1-120)"`.
  - All such issues are appended with `"severity": "warning"` (never `"error"`).
  - Then the function **logs every issue** (lines 367–374): `logger.warning(msg)` for non-error issues. It **does not** fix values or write back to disk.

- **Main guardian config (guardian_config.json)**  
  **config_validator.py** `ConfigValidator(config_path).validate_all()` (lines 77–111):
  - Validates directories, API keys, dependencies, permissions, database.
  - **Does not** validate `autonomy.json` or `introspection.json`; it only uses the single file at `config_path` (guardian_config.json or None).

So **the only place** that validates `max_actions_per_hour` and `throttle_minutes` is `validate_runtime_configs()`; it only ever emits **warnings**, never errors, and never changes the config files.

---

## 3. Whether normalized values are written back

**No.** There is no code that:

- Clamps or normalizes `max_actions_per_hour` or `throttle_minutes` to valid ranges, or  
- Writes any corrected values back to `config/autonomy.json` or `config/introspection.json`.

Validation only appends issues and logs them. Consumers use the raw values from the JSON (or the in-code defaults when the key is missing). So invalid values (e.g. 0) remain 0 and are used as-is.

---

## 4. Why invalid values only produce warnings and don’t stop startup

- In **validate_runtime_configs** all autonomy/introspection issues are added with `"severity": "warning"` (config_validator.py 340, 352). There is no branch that sets `"severity": "error"` for these fields.

- **run_startup_health_check** (startup_health.py 32–38) calls `validate_runtime_configs(project_root)` and only treats **errors** as critical:
  - `if i.get("severity") == "error": critical = True`.
  - Warnings are not used to set `critical`, so startup is not blocked.

- **GuardianCore._validate_configuration()** (core.py 1442–1487) uses `ConfigValidator(config_path).validate_all()` only for the main guardian config (directories, API keys, etc.). It does not call `validate_runtime_configs` and does not validate autonomy/introspection. So runtime config warnings are not re-evaluated or turned into errors there.

So by design, invalid `max_actions_per_hour` and `throttle_minutes` are **warnings only** and never cause startup to stop; nothing corrects them or writes them back.

---

## 5. Why the same warnings can appear more than once in a single boot

- **Single caller of runtime validation:**  
  `validate_runtime_configs()` is only invoked from **run_startup_health_check()** (startup_health.py 33), and that is only called **once** per process from **elysia.py** (lines 276–277) inside `UnifiedElysiaSystem.__init__()` before `init_guardian_core()`.

- So in one normal boot you get **one** execution of `validate_runtime_configs` and **one** set of log lines for autonomy/introspection (e.g. one warning for `max_actions_per_hour=0` and one for `throttle_minutes=0` if both are invalid).

- If the **exact same** warning line appears **twice** in the same boot, plausible causes are:
  1. **Multiple logging handlers** – e.g. the same `logger.warning()` being printed to both console and a log file, so the same text appears in two places.
  2. **Two processes** – e.g. starting the app twice or another script that also calls `run_startup_health_check` or `validate_runtime_configs`.
  3. **Two different issues** – e.g. one warning for `max_actions_per_hour` and one for `throttle_minutes`, which can look like “the same” if you expect only one kind of problem.

There is no second call path to `validate_runtime_configs` from GuardianCore or from the main `ConfigValidator.validate_all()` path.

---

## 6. Consumption of the values (why 0 is still used)

- **core.py**
  - **Autonomy:** `run_autonomous_cycle()` (lines 1096–1108) does `cfg = self._load_autonomy_config()`, then `max_per_hour = cfg.get("max_actions_per_hour", 0)`. If `max_per_hour > 0` it enforces the cap; if `max_per_hour == 0` that block is skipped, so **0 is effectively “no limit”** (no hourly cap), which conflicts with the validation text “use 1–60”.
  - **Introspection:** `_run_introspection()` (line 806) does `throttle_min = cfg.get("throttle_minutes", 30)`. That value is used in `(now - last_ts).total_seconds() > throttle_min * 60`. So **throttle_minutes=0** means “no throttle” (any time since last trigger is enough), which may be undesirable and is why validation says “use 1–120”.

So invalid values are not corrected or rejected at startup; they are loaded and used as-is, and only trigger warnings in `validate_runtime_configs()`.
