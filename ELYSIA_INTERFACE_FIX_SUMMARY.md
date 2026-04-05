# Elysia Unified Interface Startup Fixes

## Issues Fixed

### Issue 1: Architect-Core Fails - ElysiaWebScout Missing web_reader ✅

**Problem:**
- `ElysiaWebScout.__init__() missing 1 required positional argument: 'web_reader'`
- Architect-Core was creating ElysiaWebScout without passing web_reader

**Root Cause:**
- `architect_core.py` line 160: `ElysiaWebScout(proposals_root=proposals_root)` - missing web_reader argument
- `ElysiaWebScout.__init__()` required web_reader as first positional argument

**Solution:**
1. Made `web_reader` optional in `ElysiaWebScout.__init__()` (defaults to None)
2. Added automatic lookup from GuardianCore singleton if web_reader is None
3. Added safe fallback behavior - methods that use web_reader check for None and return gracefully
4. Updated Architect-Core to explicitly pass `web_reader=None`

**Changes:**
- `project_guardian/webscout_agent.py`:
  - Changed `__init__(self, web_reader, ...)` → `__init__(self, web_reader=None, ...)`
  - Added singleton lookup: tries to get web_reader from GuardianCore if None
  - Added None checks in `_brave_search()`, `_tavily_search()`, `_fetch_and_parse_webpage()`
- `core_modules/elysia_core_comprehensive/architect_core.py`:
  - Changed `ElysiaWebScout(proposals_root=proposals_root)` → `ElysiaWebScout(web_reader=None, proposals_root=proposals_root)`

### Issue 2: Second GuardianCore Initialization ✅

**Problem:**
- `elysia_interface.py` prints "Initializing system..." then errors: "GuardianCore instance already exists"
- Interface was creating a second GuardianCore instance instead of using the singleton

**Root Cause:**
- `elysia_interface.py` line 431: `self.core = GuardianCore({...})` - direct instantiation
- `elysia_interface.py` line 340: `guardian = GuardianCore(config)` - also direct instantiation

**Solution:**
- Replaced all `GuardianCore()` calls with `get_guardian_core()` from singleton module
- Interface now reuses the instance created by UnifiedElysiaSystem

**Changes:**
- `elysia_interface.py`:
  - `_init_core()`: Uses `get_guardian_core()` instead of `GuardianCore()`
  - `open_web_dashboard()`: Uses `get_guardian_core()` instead of `GuardianCore()`

## Files Changed

### Modified:
1. `project_guardian/webscout_agent.py`
   - Made web_reader optional with singleton lookup
   - Added None checks in web_reader-using methods

2. `core_modules/elysia_core_comprehensive/architect_core.py`
   - Explicitly passes `web_reader=None` to ElysiaWebScout

3. `elysia_interface.py`
   - Replaced `GuardianCore()` with `get_guardian_core()` (2 locations)

### Created:
1. `tests/test_architect_webscout_init.py` - WebScout initialization tests (5 tests)
2. `tests/test_unified_interface_no_double_init.py` - Double init prevention tests (3 tests)

## Test Results

```bash
pytest tests/test_architect_webscout_init.py tests/test_unified_interface_no_double_init.py -v
# Result: 8 passed, 0 failed ✅
```

### Test Coverage:
- ✅ ElysiaWebScout can initialize without web_reader
- ✅ ElysiaWebScout works with web_reader provided
- ✅ ElysiaWebScout gets web_reader from singleton if available
- ✅ Architect-Core can initialize ElysiaWebScout without web_reader
- ✅ WebScout methods handle None web_reader gracefully
- ✅ Unified + Interface use same GuardianCore instance
- ✅ Interface doesn't raise "instance already exists" exception
- ✅ Monitoring not started twice

## Verification

### Expected Behavior:

**Before Fix:**
- ❌ Architect-Core crashes: "missing 1 required positional argument: 'web_reader'"
- ❌ Interface crashes: "GuardianCore instance already exists"
- ❌ Double initialization errors

**After Fix:**
- ✅ Architect-Core initializes successfully (ElysiaWebScout works without web_reader)
- ✅ Interface uses singleton (no double initialization)
- ✅ No "instance already exists" exceptions
- ✅ Monitoring starts exactly once

### Manual Test:
```bash
# Run unified system
python run_elysia_unified.py

# Then run interface (in another terminal or after shutdown)
python elysia_interface.py

# Should see:
# - No "missing web_reader" error
# - No "instance already exists" error
# - Interface connects to existing GuardianCore
```

## Code Changes Summary

### Key Changes:

1. **ElysiaWebScout web_reader optional:**
   ```python
   def __init__(self, web_reader=None, ...):
       self.agent_name = "Elysia-WebScout"  # Set early
       if web_reader is None:
           # Try to get from GuardianCore singleton
           guardian_core = get_guardian_core()
           if guardian_core and guardian_core.web_reader:
               web_reader = guardian_core.web_reader
       self.web_reader = web_reader
   ```

2. **Safe method handling:**
   ```python
   def _brave_search(self, ...):
       if not self.web_reader:
           logger.warning("Brave Search requires WebReader (not available)")
           return []
       # ... use web_reader
   ```

3. **Interface uses singleton:**
   ```python
   # Before:
   self.core = GuardianCore({...})
   
   # After:
   from project_guardian.guardian_singleton import get_guardian_core
   self.core = get_guardian_core(config={...})
   ```

## Acceptance Criteria Met

✅ Architect-Core initializes without crashing  
✅ ElysiaWebScout works without web_reader (graceful fallback)  
✅ Interface doesn't cause double GuardianCore initialization  
✅ No "instance already exists" exceptions  
✅ Monitoring starts exactly once  
✅ All tests pass (8/8)  

**Status**: ✅ COMPLETE
