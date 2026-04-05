# How to Interact with Elysia

**Date**: November 22, 2025

---

## 🎯 Quick Start - Choose Your Interface

### Option 1: Chat Interface (Easiest) 💬
**Best for**: Natural conversation, asking questions, getting help

**Start**:
- Double-click `CHAT_ELYSIA.bat`
- Or run: `python chat_with_elysia.py`

**Features**:
- Natural conversation with Elysia
- AI-enhanced understanding (if OpenAI API key set)
- Memory storage and recall
- Context-aware responses

**Example**:
```
You: What have you been learning?
Elysia: [Responds with recent memories and insights]
```

---

### Option 2: Interactive CLI (Command-Based) 🖥️
**Best for**: System operations, memory management, status checks

**Start**:
- Double-click `INTERACT_ELYSIA.bat`
- Or run: `python interactive_elysia.py`

**Features**:
- Menu-driven interface
- Store/recall memories
- System status
- Memory search
- Startup verification

**Menu Options**:
1. Store Memory
2. Recall Memories
3. Show System Status
4. Show Startup Verification
5. Search Memories
6. Exit

---

### Option 3: Web UI Control Panel (Most Powerful) 🌐
**Best for**: Full system monitoring, real-time status, advanced controls

**Start**:
- Run: `python start_ui_panel.py`
- Or: `python start_ui_with_elysia.py`
- Access at: `http://127.0.0.1:5000`

**Features**:
- **Dashboard**: Real-time system status, uptime, memory stats
- **Tasks Tab**: View and manage active tasks
- **Security Tab**: Monitor security violations and audit logs
- **Memory Tab**: Search and browse memories
- **Introspection Tab**: System self-analysis, behavior patterns
- **Control Tab**: Pause/resume, snapshots, dream cycles
- **Logs Tab**: Real-time console output

**What You Can See**:
- System uptime and status
- Active tasks in queue
- Memory statistics
- Security violations
- Recent behavior patterns
- Focus analysis (what Elysia has been thinking about)
- Real-time logs

**What You Can Do**:
- Pause/resume the event loop
- Create memory snapshots
- Trigger introspection cycles
- Search memories
- Submit custom tasks
- View comprehensive system introspection

---

### Option 4: REST API (For Developers) 🔌
**Best for**: Programmatic access, automation, integration

**Start**: API server runs automatically with the system, or start manually:
```python
from project_guardian.api_server import APIServer
server = APIServer(host="0.0.0.0", port=8080)
server.start()
```

**Access**: `http://localhost:8080/api/`

**Key Endpoints**:
- `GET /api/status` - System status
- `GET /api/health` - Health check
- `GET /api/metrics` - System metrics
- `GET /api/memory/search?q=query` - Search memories
- `POST /api/control/pause` - Pause system
- `POST /api/control/resume` - Resume system

**Full API Docs**: See `API_REFERENCE.md`

---

## 📊 Monitoring What Elysia Is Doing

### Real-Time Status

**Via Web UI** (Recommended):
1. Start: `python start_ui_panel.py`
2. Open browser: `http://127.0.0.1:5000`
3. Dashboard shows:
   - Current uptime
   - Active tasks
   - Memory statistics
   - Recent activity

**Via Logs**:
- Main log: `elysia_unified.log`
- Unified log: `organized_project/data/logs/unified_autonomous_system.log`
- Status updates every 5 minutes

**Via Status Script**:
```cmd
python show_status.py
```

---

### What Elysia Is Thinking About

**Via Web UI - Introspection Tab**:
1. Open Web UI: `http://127.0.0.1:5000`
2. Click "Introspection" tab
3. See:
   - **Identity Summary**: Who Elysia thinks it is
   - **Memory Health**: Quality of memories
   - **Focus Analysis**: What Elysia has been focusing on (last 24h)
   - **Behavior Patterns**: Recent behavior analysis
   - **Memory Correlations**: Related thoughts and memories

**Via API**:
```bash
# Get comprehensive introspection
curl http://localhost:8080/api/introspection/comprehensive

# Get focus analysis
curl http://localhost:8080/api/introspection/focus?hours=24

# Get behavior patterns
curl http://localhost:8080/api/introspection/behavior
```

---

### Memory and Learning

**View Memories**:
- **Web UI**: Memory tab → Browse recent memories
- **Chat**: Ask "What do you remember about X?"
- **CLI**: Use "Search Memories" option
- **API**: `GET /api/memory/search?q=query`

**See What Elysia Learned**:
- **Web UI**: Introspection → Focus Analysis
- **Chat**: Ask "What have you been learning?"
- **Logs**: Check `elysia_unified.log` for learning events

---

## 🎮 Control Elysia

### Pause/Resume
**Web UI**: Control tab → Pause/Resume buttons
**API**: 
```bash
POST /api/control/pause
POST /api/control/resume
```

### Trigger Actions
**Web UI - Control Tab**:
- Create Memory Snapshot
- Trigger Dream Cycle (introspection)
- Submit Custom Tasks

**CLI**:
- Use menu options in `interactive_elysia.py`

---

## 💬 Example Interactions

### Chat Interface
```
You: Hello Elysia
Elysia: Hello! How can I help you today?

You: What have you been thinking about?
Elysia: [Shares recent focus and memories]

You: Remember that I like Python programming
Elysia: [Stores memory]

You: What do you remember about me?
Elysia: [Recalls stored memories]
```

### Interactive CLI
```
Main Menu:
  1. Store Memory
  2. Recall Memories
  3. Show System Status
  4. Show Startup Verification
  5. Search Memories
  6. Exit

Choice: 3
[Shows system status]
```

### Web UI
1. Open `http://127.0.0.1:5000`
2. Dashboard shows real-time status
3. Click tabs to explore:
   - **Dashboard**: Overall status
   - **Memory**: Search and browse
   - **Introspection**: Deep analysis
   - **Control**: System controls
   - **Logs**: Real-time output

---

## 🚀 Recommended Workflow

### For Daily Use:
1. **Start System**: `START_ELYSIA_UNIFIED.bat`
2. **Open Web UI**: `python start_ui_panel.py` → `http://127.0.0.1:5000`
3. **Monitor**: Watch dashboard for activity
4. **Interact**: Use chat or CLI as needed

### For Quick Check:
1. **Status**: `python show_status.py`
2. **Chat**: `CHAT_ELYSIA.bat`

### For Deep Analysis:
1. **Web UI**: Introspection tab
2. **API**: Comprehensive introspection endpoints

---

## 📝 Quick Reference

| Interface | Start Command | Best For |
|-----------|---------------|----------|
| **Chat** | `CHAT_ELYSIA.bat` | Conversation |
| **CLI** | `INTERACT_ELYSIA.bat` | Commands |
| **Web UI** | `python start_ui_panel.py` | Monitoring |
| **API** | Auto-starts with system | Automation |

---

## 🔍 Troubleshooting

**Web UI won't start**:
- Check if port 5000 is available
- Install Flask: `pip install flask flask-socketio`

**Chat interface not responding**:
- Check if GuardianCore initialized
- Review error messages

**Can't see what Elysia is doing**:
- Use Web UI Dashboard (most comprehensive)
- Check logs: `elysia_unified.log`
- Use status script: `python show_status.py`

---

## 📚 More Information

- **UI Guide**: `UI_CONTROL_PANEL_README.md`
- **API Reference**: `API_REFERENCE.md`
- **User Guide**: `USER_GUIDE.md`

---

**Recommended**: Start with **Web UI** (`python start_ui_panel.py`) for the best overview of what Elysia is doing!

