# Elysia Control Panel - Fix & Usage

## Issue Identified

The control panel was starting but not staying accessible because:
1. It runs in a **daemon thread** (background thread)
2. When the main script exits, daemon threads are killed
3. The control panel needs the main process to stay alive

## Solution

Created `start_control_panel.py` which:
- Starts GuardianCore with UI enabled
- Keeps the main process running
- Handles graceful shutdown with Ctrl+C

## How to Use

### Option 1: Use the new launcher (Recommended)
```bash
python start_control_panel.py
```

This will:
- Start GuardianCore
- Start the control panel on http://127.0.0.1:5000
- Keep running until you press Ctrl+C

### Option 2: Use unified runtime
```bash
python run_elysia_unified.py
```

This starts the full unified system including the control panel.

### Option 3: Use Elysia runtime
```bash
python -m elysia run
```

This starts the modern Elysia runtime with API server (port 8123) and optionally the control panel.

## Accessing the Control Panel

Once running, open your browser to:
- **http://127.0.0.1:5000**

## Troubleshooting

### Control Panel Not Accessible

1. **Check if it's running:**
   ```powershell
   netstat -ano | findstr :5000
   ```

2. **Check the log:**
   ```powershell
   Get-Content elysia_unified.log -Tail 50
   ```

3. **Look for these messages:**
   - "Starting Elysia Control Panel on http://127.0.0.1:5000"
   - "Running on http://127.0.0.1:5000"

4. **If not running, check dependencies:**
   ```bash
   pip install flask flask-socketio flask-cors
   ```

### Control Panel Loads But Is Blank

- Check browser console (F12) for JavaScript errors
- Check if Socket.IO is loading (network tab)
- Verify Flask is serving the template correctly

### Port Already in Use

If port 5000 is already in use:
- Find the process: `netstat -ano | findstr :5000`
- Kill it: `taskkill /PID <process_id> /F`
- Or change the port in the config

## Current Status

Based on the log:
- ✅ Control panel module exists
- ✅ GuardianCore can initialize it
- ✅ Flask is installed
- ⚠️  Control panel needs main process to stay alive

The new `start_control_panel.py` script fixes this by keeping the process running.

