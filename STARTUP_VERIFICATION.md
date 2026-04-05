# Startup Verification Guide

## Overview

This document describes how to verify that embeddings are properly deferred during startup and that the interactive prompt remains clean.

## Key Requirements

1. **No embeddings during startup**: Embedding HTTP requests should NOT occur before `enable_embeddings()` is called
2. **Clean stdout prompt**: Interactive menu prompts should not be contaminated with log output
3. **Idempotent enable_embeddings()**: Multiple calls to `enable_embeddings()` should be safe and logged appropriately

## Implementation Details

### Idempotent Guard

The `enable_embeddings()` method in `project_guardian/memory.py` includes an idempotent guard:

```python
def enable_embeddings(self):
    """Enable embeddings (call after startup completes). Idempotent: safe to call multiple times."""
    if self._embeddings_enabled:
        logger.debug("MemoryCore: Embeddings already enabled, skipping")
        return
    
    self._embeddings_enabled = True
    logger.info("MemoryCore: Embeddings enabled (startup complete)")
```

**Behavior:**
- First call: Enables embeddings, logs INFO message
- Subsequent calls: Returns early, logs DEBUG message (skipped)

### Call Sites

1. **Primary call site**: `run_elysia_unified.py` (line ~496)
   - Called after `UnifiedElysiaSystem.start()` completes
   - This is the main entry point for unified startup

2. **Defensive call site**: `elysia_interface.py` (line ~501)
   - Called after menu is shown (if interface is used standalone)
   - Idempotent guard ensures no duplicate work if already enabled

3. **Removed from**: `project_guardian/core.py`
   - Previously called during `__init__` which was too early
   - Now deferred until after unified startup completes

## Verification Methods

### 1. Automated Probe Script

Run the startup probe to automatically verify no embeddings during startup:

```bash
python run_startup_probe.py
```

**Expected output:**
```
[PASS] No embedding calls detected during startup!
```

**What it checks:**
- Patches `MemoryVectorSearch._get_embedding` to raise if called
- Patches `httpx.Client.request` to detect embedding API calls
- Initializes `GuardianCore` and `UnifiedElysiaSystem`
- Verifies no embedding calls occurred before `enable_embeddings()`

### 2. Manual Verification

#### A. Check Logs for Embedding Calls

**Before `enable_embeddings()`:**
- Should see: `MemoryCore: Embeddings enabled (startup complete)` (INFO)
- Should NOT see: `httpx - INFO - HTTP Request: POST https://api.openai.com/v1/embeddings`

**After `enable_embeddings()`:**
- Embedding calls are allowed and expected

#### B. Verify Idempotent Behavior

```python
from project_guardian.memory import MemoryCore

m = MemoryCore(enable_vector_search=True)
m.enable_embeddings()  # Should log: "MemoryCore: Embeddings enabled (startup complete)"
m.enable_embeddings()  # Should log: "MemoryCore: Embeddings already enabled, skipping" (DEBUG)
m.enable_embeddings()  # Should log: "MemoryCore: Embeddings already enabled, skipping" (DEBUG)
```

#### C. Check Interactive Prompt

1. Start unified interface:
   ```bash
   python run_elysia_unified.py
   ```

2. Verify:
   - Menu prompt appears clean (no log lines mixed in)
   - Can type menu choice without contamination
   - Logs go to stderr (not stdout)

3. Check log file:
   ```bash
   tail -f elysia_unified.log
   ```
   - Should see logs in file
   - Should NOT see logs mixed with interactive prompt

### 3. Runtime Verification

#### Start Unified Interface

```bash
python run_elysia_unified.py
```

**Expected behavior:**
1. System initializes (no embedding calls)
2. Menu appears clean
3. After menu shown, `enable_embeddings()` is called
4. Subsequent operations can use embeddings

**Check logs:**
- Look for `MemoryCore: Embeddings enabled (startup complete)` AFTER menu appears
- Verify no `httpx` embedding requests BEFORE that log line

## Troubleshooting

### Issue: Embeddings called during startup

**Symptoms:**
- `httpx - INFO - HTTP Request: POST .../embeddings` appears in logs before `enable_embeddings()` is called
- Probe script fails with "Embedding call detected during startup"

**Fix:**
1. Check that `enable_embeddings()` is NOT called in `GuardianCore.__init__`
2. Verify `_embeddings_enabled = False` during initialization
3. Ensure `remember()` checks `self._embeddings_enabled` before calling vector search

### Issue: Prompt contamination

**Symptoms:**
- Menu prompt has log lines mixed in: `"Choice: 2025-... memory_cleanup - INFO ..."`

**Fix:**
1. Verify all `StreamHandler` instances use `sys.stderr` (not `sys.stdout`)
2. Check `project_guardian/logging_config.py`
3. Check `run_elysia_unified.py` logging configuration

### Issue: Multiple enable_embeddings() calls

**Symptoms:**
- Multiple INFO logs: "MemoryCore: Embeddings enabled (startup complete)"

**Expected:**
- First call: INFO log
- Subsequent calls: DEBUG log (skipped)

**If seeing multiple INFO logs:**
- Check that idempotent guard is working
- Verify `_embeddings_enabled` flag is being checked

## Summary

✅ **No embeddings during startup**: Verified by probe script and log inspection  
✅ **Clean stdout prompt**: Logs go to stderr, prompt stays clean  
✅ **Idempotent enable_embeddings()**: Guard prevents duplicate work, logs appropriately  

## Quick Verification Checklist

- [ ] Run `python run_startup_probe.py` - should PASS
- [ ] Start unified interface - menu prompt is clean
- [ ] Check logs - no embedding calls before `enable_embeddings()` INFO log
- [ ] Verify idempotent behavior - multiple calls only log once (INFO) then DEBUG
- [ ] Confirm stdout stays clean - no log contamination in interactive prompt

