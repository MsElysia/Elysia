# Where Are The Logs?

## 📁 Log File Locations

### Main System Log
**Location**: `elysia_unified.log` (in project root)

**Path**: `C:\Users\mrnat\Project guardian\elysia_unified.log`

**Contains**:
- System startup messages
- Component initialization
- Runtime loop status
- General system activity

**How to view**:
```cmd
# View last 50 lines
powershell Get-Content elysia_unified.log -Tail 50

# Or open in text editor
notepad elysia_unified.log
```

---

### Unified Autonomous System Log (Main Log)
**Location**: `organized_project/data/logs/unified_autonomous_system.log`

**Path**: `C:\Users\mrnat\Project guardian\organized_project\data\logs\unified_autonomous_system.log`

**Contains**:
- Detailed system status updates (every 5 minutes)
- Component status
- Uptime information
- All system activity

**Size**: Very large (405,000+ lines)

**How to view**:
```cmd
# View last 100 lines
powershell Get-Content "organized_project\data\logs\unified_autonomous_system.log" -Tail 100

# Or open in text editor (may be slow due to size)
notepad "organized_project\data\logs\unified_autonomous_system.log"
```

---

### Timeline Memory Database
**Location**: `elysia_timeline.db` (SQLite database)

**Path**: `C:\Users\mrnat\Project guardian\elysia_timeline.db`

**Contains**:
- Event timeline
- Task execution history
- Structured event data

**How to view**:
- Use SQLite browser
- Or query via Python

---

## 🔍 Quick Ways to View Logs

### Option 1: View Last Lines (Recommended)
```cmd
# Main log - last 50 lines
powershell Get-Content elysia_unified.log -Tail 50

# Unified log - last 100 lines  
powershell Get-Content "organized_project\data\logs\unified_autonomous_system.log" -Tail 100
```

### Option 2: Open in Editor
```cmd
# Main log
notepad elysia_unified.log

# Unified log (may be slow - it's huge!)
notepad "organized_project\data\logs\unified_autonomous_system.log"
```

### Option 3: Follow Log in Real-Time
```cmd
# Watch log as it updates (like tail -f)
powershell Get-Content elysia_unified.log -Wait -Tail 20
```

---

## 📊 What Each Log Shows

### elysia_unified.log
- System startup
- Component initialization
- Runtime loop status
- Error messages
- General activity

### unified_autonomous_system.log
- Status updates (every 5 minutes)
- Component status: `{'architect_core': True, 'guardian_core': True, 'runtime_loop': True/False}`
- Uptime information
- Time until scheduled events
- All system activity

---

## 🎯 Finding Specific Information

### Check Runtime Loop Status
```cmd
powershell Select-String -Path "organized_project\data\logs\unified_autonomous_system.log" -Pattern "runtime_loop" | Select-Object -Last 5
```

### Check Recent Status Updates
```cmd
powershell Select-String -Path "organized_project\data\logs\unified_autonomous_system.log" -Pattern "STATUS UPDATE" | Select-Object -Last 5
```

### Check Component Status
```cmd
powershell Select-String -Path "organized_project\data\logs\unified_autonomous_system.log" -Pattern "Components Active" | Select-Object -Last 5
```

---

## 💡 Quick Reference

| Log File | Location | Size | Best For |
|----------|----------|------|----------|
| `elysia_unified.log` | Project root | Small | Recent activity |
| `unified_autonomous_system.log` | `organized_project/data/logs/` | Very Large | Historical status |

---

## 🚀 Recommended

**For recent activity**: Check `elysia_unified.log`  
**For status history**: Check `organized_project/data/logs/unified_autonomous_system.log`

**Quick view**:
```cmd
powershell Get-Content elysia_unified.log -Tail 50
```

