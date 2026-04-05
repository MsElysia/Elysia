# Restart and Verify Runtime Loop Fix

**Date**: November 22, 2025

---

## Step-by-Step Instructions

### Step 1: Stop Current System (if running)

1. Find the terminal/command prompt where the system is running
2. Press `Ctrl+C` to stop it
3. Wait for it to shut down gracefully

**Or**: Close the terminal window

---

### Step 2: Verify Fix Before Restart (Optional)

Run this to test if the fix will work:

```cmd
python verify_runtime_loop_fix.py
```

**Expected Output**:
```
✅ RuntimeLoop imported successfully
✅ RuntimeLoop instantiated successfully
✅ VERIFICATION PASSED
```

---

### Step 3: Restart System

**Option A: Using Batch File** (Easiest)
- Double-click `START_ELYSIA_UNIFIED.bat`

**Option B: Using Command Line**
```cmd
python run_elysia_unified.py
```

---

### Step 4: Watch for Success Indicators

Look for these messages in the startup output:

**✅ Success Indicators**:
```
[3/5] Initializing Elysia Runtime Loop...
✓ RuntimeLoop (project_guardian) initialized
```

And in the status output:
```
Components Active: {
    'architect_core': True, 
    'guardian_core': True, 
    'runtime_loop': True,  ← Should be True now!
    'integrated_modules': 7
}
```

**❌ If Still Failing**:
```
⚠ Runtime Loop failed (both attempts): [error message]
runtime_loop: False
```

---

### Step 5: Check Logs

If you want to verify later, check the log file:

**Log File**: `elysia_unified.log`

Look for:
- `RuntimeLoop (project_guardian) initialized` ← Success
- `Runtime Loop failed` ← Failure

---

## Troubleshooting

### If Runtime Loop Still Shows False

1. **Check the error message** in the startup output
2. **Review logs**: Check `elysia_unified.log` for details
3. **Run verification script**: `python verify_runtime_loop_fix.py`
4. **Check dependencies**: Make sure all project_guardian modules are available

### Common Issues

**Import Error**:
- Check if `project_guardian` directory exists
- Verify Python path includes project root

**Initialization Error**:
- Check if ElysiaLoopCore is available
- Verify dependencies are installed

---

## Quick Reference

```cmd
# Verify fix works
python verify_runtime_loop_fix.py

# Restart system
START_ELYSIA_UNIFIED.bat

# Or directly
python run_elysia_unified.py
```

---

## Expected Result

After restart, you should see:
- ✅ `runtime_loop: True` in status
- ✅ System fully operational
- ✅ All components active

---

**Ready to restart?** Follow steps 1-4 above!

