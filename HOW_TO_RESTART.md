# How to Restart Project Guardian / Elysia System

**Date**: November 22, 2025

---

## Quick Restart Steps

### Option 1: Using Batch File (Easiest) ⚡

1. **Stop the current system**:
   - Press `Ctrl+C` in the terminal where it's running
   - Or close the terminal window

2. **Start it again**:
   - Double-click `START_ELYSIA_UNIFIED.bat`
   - Or run it from command prompt:
     ```cmd
     START_ELYSIA_UNIFIED.bat
     ```

---

### Option 2: Using Python Directly

1. **Stop the current system**:
   - Press `Ctrl+C` in the terminal
   - Or close the terminal window

2. **Start it again**:
   ```cmd
   python run_elysia_unified.py
   ```

---

### Option 3: Using Command Prompt

1. **Open Command Prompt** (or PowerShell)

2. **Navigate to project directory**:
   ```cmd
   cd "C:\Users\mrnat\Project guardian"
   ```

3. **Stop current process** (if running):
   - Press `Ctrl+C` in the running terminal

4. **Start the system**:
   ```cmd
   python run_elysia_unified.py
   ```

---

## Verify Restart Worked

After restarting, check the output for:

```
✓ RuntimeLoop (project_guardian) initialized
```

And in the status output, you should see:
```
Components Active: {'architect_core': True, 'guardian_core': True, 'runtime_loop': True, 'integrated_modules': 7}
```

**Key**: `runtime_loop: True` (should now be True instead of False)

---

## If System Won't Stop

If `Ctrl+C` doesn't work:

1. **Windows Task Manager**:
   - Press `Ctrl+Shift+Esc`
   - Find `python.exe` process
   - End task

2. **Command Line** (PowerShell):
   ```powershell
   taskkill /F /IM python.exe
   ```
   (Warning: This kills ALL Python processes)

---

## Troubleshooting

### Runtime Loop Still Shows False?

1. Check the logs for error messages
2. Look for: `Runtime Loop failed` or similar
3. Check `RUNTIME_LOOP_INVESTIGATION.md` for details

### System Won't Start?

1. Check Python is installed: `python --version`
2. Check dependencies: `pip install -r requirements.txt`
3. Check logs: `elysia_unified.log`

---

## Files Involved

- **Startup Script**: `run_elysia_unified.py`
- **Batch File**: `START_ELYSIA_UNIFIED.bat`
- **Log File**: `elysia_unified.log`
- **Status Log**: `organized_project/data/logs/unified_autonomous_system.log`

---

**Quick Command**:
```cmd
# Stop: Ctrl+C
# Start: python run_elysia_unified.py
```


