# Troubleshooting Interface Errors

## Common Errors and Fixes

### Error: "python is not recognized"
**Fix**: Python is not in your PATH
- Install Python or add it to PATH
- Or use full path: `C:\Users\mrnat\AppData\Local\Programs\Python\Python313\python.exe elysia_interface.py`

### Error: "No module named 'project_guardian'"
**Fix**: Run from the project directory
- Make sure you're in: `C:\Users\mrnat\Project guardian`
- The batch file should handle this automatically

### Error: Unicode/Encoding errors
**Fix**: Already fixed in latest version
- Make sure you have the latest `elysia_interface.py`

### Error: Import errors
**Fix**: Check dependencies
```cmd
pip install flask flask-socketio
```

## Quick Test

Run this to test:
```cmd
python test_interface.py
```

## Alternative: Use Web UI Instead

If the interface has issues, use the Web UI:
```cmd
python start_ui_panel.py
```
Then open: http://127.0.0.1:5000

## Get Help

**What error are you seeing?**
- Copy the error message
- Check which step failed
- Try the alternative methods above

---

**Quick Fix**: Try `RUN_INTERFACE.bat` (new launcher with better error handling)

