# Dashboard Connection Fix - Minimal Patch

## Root Cause

**Primary Issue**: Server thread errors might not be detected immediately during readiness check, causing false "ready" signals or delayed error detection.

**Secondary Issues**:
1. No initial delay after thread start (server might fail before readiness check begins)
2. Readiness check doesn't check for server errors during the wait loop
3. Potential timing race: thread starts → immediately check readiness → thread hasn't bound yet

## Minimal Diff Patch

### File: `project_guardian/ui_control_panel.py`

**Change 1**: Improve `_wait_for_server_ready()` to check for errors during wait loop

```diff
    def _wait_for_server_ready(self, timeout: float = 10.0) -> bool:
        """Wait for server to be ready by checking if port is listening."""
        start_time = time.time()
        while time.time() - start_time < timeout:
+           # Check for server errors first (fast failure)
+           if self._server_error:
+               logger.error(f"[DASHBOARD] Server error detected during readiness check: {self._server_error}")
+               return False
+           
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    result = s.connect_ex((self.host, self._actual_port or self.port))
                    if result == 0:  # Port is listening
                        return True
            except Exception:
                pass
            time.sleep(0.1)
        return False
```

**Change 2**: Add small initial delay after thread start

```diff
        server_thread = threading.Thread(target=run_server, daemon=True, name="UIControlPanel-Server")
        server_thread.start()
        
+       # Wait for server to be ready (with small initial delay to let thread start)
+       time.sleep(0.2)  # Give thread a moment to start and potentially fail
+       
        if self._wait_for_server_ready(timeout=10.0):
```

## Verification

1. Run verification script: `python scripts/verify_dashboard_listening.py`
2. Run tests: `pytest tests/test_dashboard_listening.py -v`
3. Manual test: Start dashboard, verify browser opens only after server is listening

## Expected Behavior After Fix

1. Server thread starts
2. Small delay (0.2s) allows thread to initialize or fail
3. Readiness check runs, checking for errors on each iteration
4. If error detected, immediately return False (fast failure)
5. If port listening, return True
6. Browser opens only after True returned
