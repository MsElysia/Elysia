# TASK-0056: Optional Dependencies - Capability Flags + Setup Guidance

## Problem Solved

**Issue:** Runtime logs show "sentence_transformers not installed, embeddings use fallback", degrading vector search quality. No visibility into missing optional dependencies or how to install them.

**Root Cause:** No capability detection system to report optional dependencies and their installation status.

## Solution Implemented

### 1. Capability Detection Module (`project_guardian/capabilities.py`)

**Implementation Details:**
- Uses `importlib.util.find_spec` for safe package existence checks (no import-time crashes)
- Uses `importlib.metadata.version` for version detection (with fallback for older Python)
- All imports kept inside functions to avoid import-time crashes
- Provides module-level boolean flags: `HAS_SENTENCE_TRANSFORMERS`, `HAS_FAISS`, `HAS_HTTPX`, `HAS_PLAYWRIGHT`, `HAS_PSUTIL`, `HAS_ANTHROPIC`, `HAS_OPENAI`

**Key Functions:**
- `get_capabilities(checker=None) -> dict[str, dict]` - Returns capability dict with:
  - `"available": bool`
  - `"version": str | None`
  - `"notes": str | None`
- `format_capabilities_text(capabilities) -> str` - Returns ASCII-only formatted string with `[OK]`/`[MISSING]` status
- `detect_capabilities() -> dict[str, bool]` - Updates module-level flags

**Design:**
- `_check_package_exists()` uses `importlib.util.find_spec` (injectable checker for testing)
- `_get_package_version()` uses `importlib.metadata.version` with graceful fallback
- No import-time crashes - all checks are lazy

### 2. Status Display Integration

**File:** `elysia_interface.py`

**Changes:**
- Updated `view_status()` to display capabilities section
- Uses `format_capabilities_text()` for ASCII-safe output
- Gracefully handles missing capabilities module (no crashes)

**File:** `project_guardian/core.py`

**Changes:**
- Updated `get_system_status()` to include capabilities dict
- Uses `get_capabilities()` directly (not the old report format)

### 3. Documentation (`OPTIONAL_DEPENDENCIES.md`)

**Content:**
- Overview of all 7 optional dependencies
- Installation commands for each:
  - `sentence-transformers` (with PyTorch note)
  - `faiss-cpu` (with Windows caveats)
  - `playwright` + `playwright install` (important note)
  - `psutil`
  - `anthropic`
  - `httpx`
  - `openai`
- Python version recommendations:
  - **Recommended:** Python 3.11 or 3.12
  - **Python 3.13:** May have compatibility issues, recommend 3.11/3.12
  - **Python 3.8-3.10:** Supported but older
- Installation profiles: Minimal, Full, GPU Support
- Troubleshooting guide

### 4. Tests (`tests/test_capabilities.py`)

**Test Coverage (13 tests, all passing):**

1. ✅ `test_get_capabilities_returns_required_keys` - All 7 capabilities present
2. ✅ `test_capability_entry_structure` - Each entry has "available", "version", "notes"
3. ✅ `test_format_capabilities_text_ascii_only` - Output is ASCII-encodable
4. ✅ `test_format_capabilities_text_structure` - Has expected sections
5. ✅ `test_get_capabilities_with_checker_injection` - Checker injection works for testing
6. ✅ `test_find_spec_checker_mechanism` - Uses `find_spec` correctly
7. ✅ `test_check_package_exists_with_custom_checker` - Custom checker works
8. ✅ `test_get_package_version_handles_missing` - Gracefully handles missing packages
9. ✅ `test_capabilities_no_import_time_crashes` - Module imports safely
10. ✅ `test_detect_capabilities_updates_flags` - Updates module-level flags
11. ✅ `test_capabilities_in_system_status` - Included in system status
12. ✅ `test_format_capabilities_with_all_missing` - Handles all missing
13. ✅ `test_format_capabilities_with_all_available` - Handles all available

## Code Changes

### Created Files:

1. **`project_guardian/capabilities.py`**
   - Capability detection using `importlib.util.find_spec`
   - Version detection using `importlib.metadata.version`
   - ASCII-only formatting function
   - 7 optional dependencies detected

2. **`OPTIONAL_DEPENDENCIES.md`**
   - Comprehensive documentation
   - Installation commands with platform notes
   - Python version recommendations (3.11/3.12 recommended, 3.13 may have issues)
   - Troubleshooting guide

3. **`tests/test_capabilities.py`**
   - 13 comprehensive tests
   - Tests checker injection mechanism
   - Tests find_spec usage
   - Tests ASCII-only output
   - All tests passing

### Modified Files:

1. **`elysia_interface.py`**
   - Updated `view_status()` to display capabilities using `format_capabilities_text()`

2. **`project_guardian/core.py`**
   - Updated `get_system_status()` to include capabilities dict from `get_capabilities()`

## Test Results

```bash
pytest tests/test_capabilities.py -q
# Result: 13 passed, 0 failed ✅
```

## Verification

### Runtime Test:
```python
from project_guardian.capabilities import get_capabilities, format_capabilities_text
caps = get_capabilities()
print(format_capabilities_text(caps))
```

**Output:**
```
======================================================================
SYSTEM CAPABILITIES
======================================================================

[OK] Available Capabilities:
  [OK] faiss (v1.13.0): Fast vector similarity search
  [OK] httpx (v0.28.1): Modern HTTP client for web requests
  [OK] playwright (v1.53.0): Browser automation for JavaScript-heavy sites
  [OK] psutil (v7.1.3): System and process utilities
  [OK] openai (v1.97.0): OpenAI API client

[MISSING] Missing Capabilities (degraded functionality):
  [MISSING] sentence_transformers: Missing: pip install sentence-transformers
  [MISSING] anthropic: Missing: pip install anthropic

======================================================================
```

### Structure Verification:
- ✅ Each capability entry has: `available`, `version`, `notes`
- ✅ Output is ASCII-only (encodes successfully)
- ✅ Versions shown when available
- ✅ Installation guidance in notes

## Acceptance Criteria Met

✅ **Status screen shows capability flags clearly**
- Available capabilities shown with `[OK]` and version
- Missing capabilities shown with `[MISSING]` and installation note
- Integrated into "View System Status" option

✅ **Docs show how to enable higher-quality embeddings**
- `OPTIONAL_DEPENDENCIES.md` includes:
  - Installation: `pip install sentence-transformers`
  - PyTorch dependency note
  - Python version recommendations (3.11/3.12 recommended)
  - Troubleshooting guide

✅ **Tests pass**
- All 13 tests passing
- Tests verify structure, ASCII-only output, checker injection, find_spec usage

✅ **No new import-time crashes**
- All imports inside functions
- Uses `importlib.util.find_spec` (safe)
- Graceful error handling

## Implementation Details

### Design Decisions:

1. **`importlib.util.find_spec` over direct imports:**
   - Prevents import-time crashes
   - Allows dependency-free capability detection
   - Enables testability with checker injection

2. **`importlib.metadata.version` with fallback:**
   - Works on Python 3.8+ (primary)
   - Falls back to `importlib_metadata` for older Python
   - Returns `None` gracefully if version unavailable

3. **Checker injection for testing:**
   - `get_capabilities(checker=...)` allows deterministic tests
   - Tests can verify find_spec mechanism without actual packages

4. **ASCII-only output:**
   - `format_capabilities_text()` ensures ASCII encoding
   - Prevents Windows console encoding issues
   - Uses `[OK]` and `[MISSING]` markers (no emojis)

## Files Changed

### Created:
1. `project_guardian/capabilities.py` - Capability detection module
2. `OPTIONAL_DEPENDENCIES.md` - Comprehensive documentation
3. `tests/test_capabilities.py` - Test suite (13 tests)
4. `TASK-0056_COMPLETION.md` - This completion report

### Modified:
1. `elysia_interface.py` - Added capabilities display to status view
2. `project_guardian/core.py` - Added capabilities to system status

## Summary

The capability detection system is fully implemented according to specifications:
- **7 optional dependencies detected** using `importlib.util.find_spec`
- **Version detection** using `importlib.metadata.version`
- **ASCII-only formatted output** with `[OK]`/`[MISSING]` status
- **Status screen integration** in "View System Status"
- **Comprehensive documentation** with Python version recommendations
- **13 tests passing** with checker injection and find_spec verification
- **No import-time crashes** - all checks are lazy

Users can now easily see what capabilities are missing and how to enable them for better functionality.

**Status: ✅ COMPLETE**
