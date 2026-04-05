# Restart Control Panel to Apply Fixes

## What Was Fixed

The control panel was failing because `ModuleRegistry` was missing three methods:
- `get_registry_status()`
- `get_module_status()`
- `route_task()`

These methods have now been added to `project_guardian/elysia_loop_core.py`.

## How to Restart

### Option 1: If using start_control_panel.py
1. Stop the current process (Ctrl+C in the terminal)
2. Run: `python start_control_panel.py`

### Option 2: If using run_elysia_unified.py
1. Stop the current process (Ctrl+C in the terminal)
2. Run: `python run_elysia_unified.py`

### Option 3: Find and kill the process
```powershell
# Find Python process
Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Select-Object Id, ProcessName

# Kill specific process (replace <PID> with actual process ID)
Stop-Process -Id <PID> -Force

# Then restart
python start_control_panel.py
```

## After Restart

Test the fixed endpoints:

```powershell
# Test module list
Invoke-WebRequest -Uri http://127.0.0.1:5000/api/modules/list -UseBasicParsing

# Should return: {"success": true, "modules": [...]}
```

## What Should Work Now

1. ✅ `/api/modules/list` - Lists all registered modules
2. ✅ `/api/tasks/submit` - Submits tasks to modules
3. ✅ Module management in control panel UI

## If Still Not Working

1. Check that the control panel process actually restarted
2. Verify the code changes were saved
3. Check browser console for JavaScript errors
4. Hard refresh browser (Ctrl+F5)

