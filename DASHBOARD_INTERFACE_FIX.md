# Dashboard Interface Fix - Root Cause & Solution

## Root Cause

**Issue**: Dashboard fails to start from Elysia interface option [7] with errors:
- `[ERROR] Could not get GuardianCore instance or UI panel for Web UI`
- `[WARN] UI panel not available, cannot determine URL`

**Root Cause**: The `open_web_dashboard()` method was trying to get GuardianCore from singleton in a background thread, but:
1. The singleton was created by `UnifiedElysiaSystem` without UI config (no `ui_config` in config)
2. When `get_guardian_core(config=config)` is called with UI config, it returns the existing singleton instance (which doesn't have UI panel)
3. The method didn't try `self.core` or `self.autonomous_system.guardian` first
4. No fallback to create UI panel if it doesn't exist
5. Missing detailed logging to diagnose the issue

## Fix Applied

### File: `elysia_interface.py` - `open_web_dashboard()` method

**Changes**:
1. **Multi-source GuardianCore lookup** (in order of preference):
   - `self.core` (if available - already initialized)
   - `self.autonomous_system.guardian` (actual instance from UnifiedElysiaSystem)
   - Singleton fallback (with UI config)

2. **Detailed logging**:
   - Module path for singleton class
   - GuardianCore instance existence
   - UI panel existence
   - Full exception tracebacks (no silent failures)

3. **UI panel initialization fallback**:
   - If UI panel doesn't exist, try `start_ui_panel()` method
   - If that doesn't exist, create UI panel directly
   - Start server after creation

4. **Use same guardian instance** throughout the method (not re-fetching from singleton)

### File: `project_guardian/core.py` - `start_ui_panel()` method

**Fix**: Changed parameter from `guardian_core=self` to `orchestrator=self` to match UIControlPanel constructor.

## Verification Script

**File**: `scripts/verify_dashboard_from_interface.py`

**Features**:
- Simulates the same call path as option [7]
- Tests all three GuardianCore sources
- Verifies UI panel initialization
- Tests TCP connection and HTTP GET
- Full logging of module paths and instance states

## Manual Verification Steps

1. Run: `python run_elysia_unified.py`
2. Choose option [7] (Open Web Dashboard)
3. Expected output:
   - `[DEBUG] Using GuardianCore from: autonomous_system.guardian` (or `self.core`)
   - `[OK] UI panel initialized`
   - `[OK] Web UI started!`
   - Browser opens to dashboard URL
4. Dashboard should be accessible and return HTTP 200

## Files Modified

1. `elysia_interface.py` - Complete rewrite of `open_web_dashboard()` method
2. `project_guardian/core.py` - Fixed `start_ui_panel()` parameter name
3. `scripts/verify_dashboard_from_interface.py` - New verification script

## Expected Behavior After Fix

1. Dashboard launcher tries `self.core` first (preferred)
2. Falls back to `autonomous_system.guardian` if available
3. Falls back to singleton only if needed
4. Creates UI panel if it doesn't exist
5. Starts server and waits for readiness
6. Opens browser only after server is listening
7. Full diagnostic logging at each step
