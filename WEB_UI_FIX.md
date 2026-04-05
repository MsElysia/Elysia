# Web UI Fix Applied

## Issue Found
The `UIControlPanel` was being initialized with wrong parameter name:
- **Expected**: `orchestrator`
- **Was passing**: `guardian_core`

## Fix Applied
Updated `project_guardian/core.py` to use correct parameter name.

## How to Start Web UI

### Option 1: Using start_ui_panel.py
```cmd
python start_ui_panel.py
```

### Option 2: Via GuardianCore Config
```python
from project_guardian import GuardianCore

config = {
    "ui_config": {
        "enabled": True,
        "auto_start": True,
        "host": "127.0.0.1",
        "port": 5000
    }
}

guardian = GuardianCore(config)
# UI will start automatically
```

## Access Web UI
Once started, open in browser:
```
http://127.0.0.1:5000
```

## What You'll See
- Dashboard with system status
- Memory tab
- Introspection tab
- Control tab
- Logs tab

## Troubleshooting

**If UI still doesn't start**:
1. Check if port 5000 is available
2. Check for error messages in terminal
3. Verify Flask is installed: `pip install flask flask-socketio`

**If you see connection errors**:
- Make sure the UI process is running
- Check firewall settings
- Try accessing `http://localhost:5000` instead

---

**Fix Applied**: Parameter name corrected in `project_guardian/core.py`

