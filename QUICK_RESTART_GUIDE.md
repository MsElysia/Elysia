# Quick Restart Guide

## 🚀 Restart Steps (2 minutes)

### Step 1: Stop Current System
1. Go to the terminal/command prompt where the system is running
2. Press `Ctrl+C` 
3. Wait for it to stop (you'll see "Shutdown signal received..." or similar)

### Step 2: Start System Again

**Easiest Method**:
- Double-click `START_ELYSIA_UNIFIED.bat`

**Or use command line**:
```cmd
python run_elysia_unified.py
```

**Or use restart script**:
- Double-click `restart_system.bat` (new helper script)

### Step 3: Watch for Success

Look for these messages:

**✅ Success**:
```
[3/5] Initializing Elysia Runtime Loop...
✓ RuntimeLoop (project_guardian) initialized
```

**Status should show**:
```
runtime_loop: True  ← This is what we want!
```

---

## ⚡ Quick Commands

```cmd
# Stop: Ctrl+C in running terminal
# Start: Double-click START_ELYSIA_UNIFIED.bat
```

---

## ✅ What Success Looks Like

After restart, you should see:
- `✓ RuntimeLoop (project_guardian) initialized`
- `runtime_loop: True` in components status
- System running normally

---

**Ready?** Stop the current system (Ctrl+C), then start it again!

