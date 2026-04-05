# TASK-0014 Complete ✅

## Summary

UI hardened: dependencies split (optional UI deps), acceptance artifacts are durable, and safety enhanced with input sanitization and error handling.

---

## What Changed

### 1. Dependency Split

**Before:**
- All deps in `requirements.txt` (UI mandatory)

**After:**
- `requirements.txt` - Core runtime only
- `requirements-ui.txt` - UI deps (fastapi, uvicorn, jinja2) - optional
- Headless operation doesn't require UI

**Installation:**
```bash
# Core only
pip install -r requirements.txt

# With UI
pip install -r requirements.txt -r requirements-ui.txt
# Or
pip install -r requirements-ui.txt  # (includes core)
```

### 2. Acceptance Artifacts

**acceptance.ps1 now writes:**

1. **REPORTS/acceptance_last.json:**
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "exit_code": 0,
  "status": "pass",
  "duration_seconds": 5.23,
  "pytest_exit_code": 0,
  "invariant_exit_code": 0,
  "checks_run": 2,
  "checks_skipped": 3
}
```

2. **REPORTS/acceptance_last.log:**
- Full output (stdout + stderr)
- Redacted sensitive patterns
- Summary with timing info

**UI reads artifacts:**
- Dashboard shows status from JSON (not file timestamp)
- Shows pass/fail badge
- Shows exit code
- Link to view full log

### 3. Safety Enhancements

**Input Sanitization:**
- Task name: alphanumeric, dash, underscore, dots only
- Approver: max 100 chars
- Notes: max 1000 chars

**Encoding & Error Handling:**
- Explicit utf-8 encoding everywhere
- Try/except blocks for file operations
- Graceful degradation on errors

**Context Escaping:**
- Pre-escaped JSON in templates
- No raw context rendering
- Jinja2 auto-escaping (default)

**Command Execution:**
- Only runs exact `acceptance.ps1` path
- Path validation before execution
- Output redaction for sensitive patterns

---

## Files Modified

1. `requirements.txt` - Removed UI deps
2. `requirements-ui.txt` - New file with UI deps
3. `scripts/acceptance.ps1` - Writes artifacts
4. `project_guardian/ui/app.py` - Reads artifacts, safety enhancements
5. `project_guardian/ui/templates/dashboard.html` - Shows acceptance status
6. `project_guardian/ui/templates/log_viewer.html` - New log viewer
7. `project_guardian/ui/templates/error.html` - New error template
8. `scripts/start_control_panel.ps1` - Warns if deps missing
9. `CHANGELOG.md` - Updated
10. `REPORTS/AGENT_REPORT.md` - Complete report
11. `CONTROL.md` - Set to NONE

---

## Verification

### Test Dependency Split

```bash
# Core only (no UI)
pip install -r requirements.txt
python -c "from project_guardian.core import GuardianCore"  # Should work

# UI requires separate install
pip install -r requirements-ui.txt
python -m uvicorn project_guardian.ui.app:app  # Should work
```

### Test Acceptance Artifacts

```powershell
# Run acceptance
.\scripts\acceptance.ps1

# Check artifacts
Get-Content REPORTS\acceptance_last.json
Get-Content REPORTS\acceptance_last.log
```

### Test UI Reads Artifacts

```python
# UI should show correct status from JSON
# Dashboard: http://127.0.0.1:8000
# Should show: last acceptance time, status (pass/fail), exit code
```

---

## Acceptance Criteria Met

- ✅ Run acceptance: artifacts written (JSON + log)
- ✅ UI displays correct last-run info after restart
- ✅ No breaking changes to existing acceptance behavior
- ✅ Dependency split: UI deps optional
- ✅ start_control_panel.ps1 warns if deps missing
- ✅ CONTROL.md set to NONE

---

**TASK-0014 complete! UI is hardened, dependencies are split, and acceptance artifacts are durable.** ✅
