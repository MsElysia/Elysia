# Cursor Agent Instruction for TASK-0001

## What to Tell Cursor Agent

**Copy and paste this into Cursor Agent Mode:**

---

Read `CONTROL.md`

Execute `TASK-0001`

Write report to `/REPORTS/AGENT_REPORT.md`

Append changelog entry if missing

**No other changes.**

---

## What Cursor Should Do

1. **Read CONTROL.md** - Understand current task is TASK-0001
2. **Read TASKS/TASK-0001.md** - Understand the task contract
3. **Verify all files exist:**
   - CONTROL.md ✓
   - SPEC.md ✓ (verify <= 120 lines)
   - CHANGELOG.md ✓ (verify TASK-0001 entry exists)
   - TASKS/.gitkeep ✓
   - REPORTS/AGENT_REPORT.md ✓
4. **Write report to REPORTS/AGENT_REPORT.md:**
   - Summary of what was verified
   - Files that exist
   - Any issues or ambiguities
5. **Verify CHANGELOG.md** has TASK-0001 entry (it should already)

## What Cursor Should NOT Do

- ❌ Modify any existing code
- ❌ Refactor anything
- ❌ Reorganize modules
- ❌ Change dependencies
- ❌ Create extra files beyond what's in scope
- ❌ "Improve" formatting or structure

## Success Criteria

All acceptance criteria in TASK-0001.md must be met:
1. ✅ All required files exist
2. ✅ SPEC.md is <= 120 lines (currently 24 lines)
3. ✅ CHANGELOG.md includes TASK-0001 entry
4. ✅ REPORTS/AGENT_REPORT.md contains required sections

---

**Remember:** Cursor is execution-only. It verifies and reports. It does not redesign.
