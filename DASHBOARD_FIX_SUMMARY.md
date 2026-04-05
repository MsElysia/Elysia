# Dashboard Repeated Initialization Fix - Summary

## Root Cause

The web browser/dashboard was repeatedly initializing due to:

1. **Multiple call sites** starting the dashboard:
   - `GuardianCore._initialize_system()` (if `auto_start=True`)
   - `GuardianCore.start_ui_panel()` (manual start)
   - `SystemOrchestrator.start()` (if panel exists)

2. **Insufficient guard**: Only instance-level `self.running` flag, allowing multiple instances to start

3. **Heartbeat spam**: Printing to stdout every 30 seconds, interfering with user input

## Solution

### 1. Module-Level Idempotent Guard
- Added `_dashboard_started` (module-level boolean)
- Added `_dashboard_start_lock` (thread-safe lock)
- Added `_dashboard_start_attempts` (monotonic counter)
- `start()` checks module-level flag BEFORE starting
- Sets flag BEFORE server start (prevents race conditions)

### 2. Instrumentation
- Every start attempt logged with:
  - Attempt number (monotonic counter)
  - Source identifier (call site)
  - Thread name
- Example: `[DASHBOARD] start attempt 2 source=SystemOrchestrator.start thread=MainThread - Already started; skipping`

### 3. Call Site Labeling
All start calls now include source parameter:
- `GuardianCore._initialize_system()` → `source="GuardianCore._initialize_system"`
- `GuardianCore.start_ui_panel()` → `source="GuardianCore.start_ui_panel"`
- `SystemOrchestrator.start()` → `source="SystemOrchestrator.start"`

### 4. Heartbeat Output Fix
- Changed `print()` to `logger.debug()` / `logger.info()`
- Heartbeat logs to file, not stdout
- Prevents interference with user input

## Files Changed

### Modified:
1. `project_guardian/ui_control_panel.py`
   - Added module-level guard (lines 27-30)
   - Enhanced `start()` with idempotency (lines 2185-2220)
   - Added `reset_dashboard_guard()` for testing
   - Updated `stop()` to reset module flag

2. `project_guardian/core.py`
   - Added source parameter to 2 `ui_panel.start()` calls

3. `project_guardian/system_orchestrator.py`
   - Added source parameter to `ui_control_panel.start()` call

4. `project_guardian/monitoring.py`
   - Changed heartbeat prints to logger (2 locations)

### Created:
1. `tests/test_dashboard_idempotent.py` - Test suite (3 tests)

## Test Results

```bash
pytest tests/test_dashboard_idempotent.py -v
# Result: 3 passed, 0 failed ✅
```

## Verification

### Expected Behavior:
- ✅ Dashboard starts exactly once
- ✅ Subsequent attempts logged and skipped
- ✅ UI remains responsive
- ✅ No heartbeat spam in console
- ✅ Instrumentation shows all attempts

### Manual Test:
```bash
python run_elysia_unified.py
# Check logs for:
# - ONE "[DASHBOARD] start attempt 1 ... Starting..." message
# - Subsequent: "[DASHBOARD] start attempt N ... Already started; skipping"
# - Menu accepts input immediately
# - No repeated browser initialization
```

## Code Changes

### Key Addition (ui_control_panel.py):
```python
# Module-level guard
_dashboard_started = False
_dashboard_start_lock = threading.Lock()
_dashboard_start_attempts = 0

def start(self, debug=False, source="unknown"):
    global _dashboard_started, _dashboard_start_attempts
    with _dashboard_start_lock:
        _dashboard_start_attempts += 1
        if _dashboard_started:
            logger.info("[DASHBOARD] start attempt %d source=%s ... Already started; skipping", ...)
            return
        _dashboard_started = True
        # ... start server
```

## Acceptance Criteria Met

✅ Dashboard starts exactly once  
✅ Idempotent behavior (multiple calls = one start)  
✅ UI remains responsive  
✅ Heartbeat doesn't spam stdout  
✅ Instrumentation tracks attempts  
✅ Tests pass (3/3)  

**Status**: ✅ COMPLETE
