# Dashboard Server Connection Fix

## Root Cause Analysis

### Issues Identified:

1. **Race Condition**: Server starts in daemon thread, but success message printed before server actually binds/listens
2. **No Readiness Check**: Browser opens after fixed 3-second sleep without verifying server is listening
3. **No Port Conflict Handling**: If port 5000 is in use, server fails silently
4. **Silent Failures**: Exceptions in server thread are caught but main thread doesn't know
5. **No Actual Port Verification**: Log says "started" but doesn't verify socket is listening

### Execution Path:

1. `elysia_interface.py:open_web_dashboard()` calls `get_guardian_core()`
2. `GuardianCore.__init__()` creates `UIControlPanel` and calls `start()`
3. `UIControlPanel.start()` marks `_dashboard_started = True` immediately
4. Server starts in daemon thread with `socketio.run()`
5. `elysia_interface.py` prints "[OK] Web UI started!" immediately
6. Waits 3 seconds, then opens browser
7. **Problem**: Server might not be listening yet, or port might be in use

## Fix Required

1. Add port conflict detection with fallback
2. Add readiness check (socket connect or health endpoint)
3. Wait for server to be ready before printing success
4. Log actual bind address and port
5. Verify server is listening before opening browser
