# Log File Locations

## 📁 Main Log Files

### 1. Unified Autonomous System Log (Main Log)
**Location**: 
```
organized_project\data\logs\unified_autonomous_system.log
```

**Full Path**:
```
C:\Users\mrnat\Project guardian\organized_project\data\logs\unified_autonomous_system.log
```

**Contains**:
- Status updates every 5 minutes
- Component status: `{'architect_core': True, 'guardian_core': True, 'runtime_loop': True/False}`
- Uptime information
- All system activity

**Size**: Very large (405,000+ lines)

**How to view**:
- Open in text editor (may be slow)
- Or use: `powershell Get-Content "organized_project\data\logs\unified_autonomous_system.log" -Tail 50`

---

### 2. Main System Log
**Location**: 
```
elysia_unified.log
```

**Full Path**:
```
C:\Users\mrnat\Project guardian\elysia_unified.log
```

**Contains**:
- System startup messages
- Component initialization
- Runtime loop status
- General activity

**Note**: Created when system starts

**How to view**:
- `powershell Get-Content elysia_unified.log -Tail 50`
- Or open in text editor

---

### 3. Other Log Files
**Location**: `organized_project\data\logs\`

- `autonomous_elysia.log`
- `autonomous_guardian.log`
- `enhanced_autonomous_guardian.log`

---

## 🔍 Quick View Commands

### View Last 50 Lines of Unified Log
```powershell
cd "C:\Users\mrnat\Project guardian"
Get-Content "organized_project\data\logs\unified_autonomous_system.log" -Tail 50
```

### View Last 50 Lines of Main Log
```powershell
cd "C:\Users\mrnat\Project guardian"
Get-Content elysia_unified.log -Tail 50
```

### Watch Log in Real-Time
```powershell
Get-Content elysia_unified.log -Wait -Tail 20
```

---

## 📊 What You'll See

### Status Updates (every 5 minutes)
```
2025-11-20 00:34:35,298 - __main__ - INFO - STATUS UPDATE
2025-11-20 00:34:35,298 - __main__ - INFO - Uptime: 3:17:44.887411
2025-11-20 00:34:35,298 - __main__ - INFO - Components Active: {'architect_core': True, 'guardian_core': True, 'runtime_loop': False, 'integrated_modules': 7}
```

### Component Initialization
```
[3/5] Initializing Elysia Runtime Loop...
✓ RuntimeLoop (project_guardian) initialized
```

---

## 💡 Easy Way to View

**Use the batch file**:
```cmd
view_logs.bat
```

Or **open directly**:
- Navigate to: `organized_project\data\logs\`
- Open: `unified_autonomous_system.log` in text editor
- Scroll to bottom for most recent entries

---

## 🎯 Finding Specific Info

### Check Runtime Loop Status
Look for lines containing: `Components Active`
Last entry shows: `runtime_loop: True` or `runtime_loop: False`

### Check Recent Activity
Scroll to bottom of log file (most recent entries are at the end)

---

**Main Log**: `organized_project\data\logs\unified_autonomous_system.log`  
**System Log**: `elysia_unified.log` (created when system starts)

