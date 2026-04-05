# GuardianCore Double Initialization Fix

## Problem
GuardianCore was being initialized twice in the Elysia unified interface:
- First initialization during UnifiedElysiaSystem startup
- Second initialization when UI/interface accessed GuardianCore
- This caused duplicate background loops, repeated memory load attempts, and UI appearing unresponsive

## Solution

### 1. Created Singleton Module (`project_guardian/guardian_singleton.py`)
- `get_guardian_core()`: Returns existing instance or creates new one (singleton pattern)
- `ensure_monitoring_started()`: Ensures monitoring/heartbeat starts exactly once
- `reset_singleton()`: Resets singleton for testing

### 2. Updated Unified System (`run_elysia_unified.py`)
- Changed `_init_guardian_core()` to use `get_guardian_core()` from singleton module
- Added `ensure_monitoring_started()` call to prevent duplicate monitoring

### 3. Added Monitoring Guards
- `SystemMonitor.start_monitoring()`: Now idempotent (checks `monitoring_active` before starting)
- `GuardianCore._initialize_system()`: Uses `ensure_monitoring_started()` from singleton

### 4. Added Tests (`tests/test_guardian_singleton.py`)
- Test singleton pattern (same instance returned)
- Test direct initialization fails after singleton created
- Test monitoring started exactly once
- Test unified + interface uses same instance

## Files Modified

1. **Created:**
   - `project_guardian/guardian_singleton.py` - Singleton module
   - `tests/test_guardian_singleton.py` - Unit tests

2. **Modified:**
   - `run_elysia_unified.py` - Uses singleton for GuardianCore initialization
   - `project_guardian/core.py` - Uses singleton guard for monitoring
   - `project_guardian/monitoring.py` - Added idempotent guard to `start_monitoring()`

## Verification

Run the unified interface and check logs:
- Should see exactly **one** "Initializing Guardian Core..." message
- Should see exactly **one** heartbeat loop start
- No duplicate memory loads
- UI should be responsive

Run tests:
```bash
pytest tests/test_guardian_singleton.py -v
```

## Usage

### For Unified System:
```python
from project_guardian.guardian_singleton import get_guardian_core, ensure_monitoring_started

# Get or create singleton
guardian = get_guardian_core(config={...})

# Ensure monitoring started (idempotent)
ensure_monitoring_started(guardian)
```

### For Other Code:
Always use `get_guardian_core()` instead of `GuardianCore()` directly:
```python
# ✅ Correct
from project_guardian.guardian_singleton import get_guardian_core
core = get_guardian_core()

# ❌ Wrong (will fail if singleton exists)
from project_guardian.core import GuardianCore
core = GuardianCore()  # Raises RuntimeError if singleton exists
```

## Benefits

1. **Single Initialization**: GuardianCore initialized exactly once per process
2. **Single Monitoring Loop**: Heartbeat/monitoring starts exactly once
3. **Memory Efficiency**: No duplicate memory loads or background threads
4. **UI Responsiveness**: No duplicate operations causing UI to appear frozen
5. **Thread Safety**: Singleton uses locks to prevent race conditions
