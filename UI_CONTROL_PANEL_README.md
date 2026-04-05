# UI Control Panel - Elysia Operator Interface

## Overview

The UI Control Panel provides a web-based interface for monitoring and controlling the Elysia system. It offers real-time status updates, task management, security monitoring, and system controls.

## Features

### 📊 Dashboard
- **System Status**: Uptime, event loop status, queue size, active tasks
- **Memory System**: Total memories, vector search status, last snapshot
- **Security Status**: Recent violations, pending reviews, policy status
- **Trust System**: Average trust levels, component count

### 📋 Tasks Tab
- View active tasks in the queue
- Monitor task execution status
- Submit new tasks

### 🔒 Security Tab
- View recent security violations
- Monitor audit logs
- Review escalated items

### 🧠 Memory Tab
- Search memories (keyword or semantic)
- View memory statistics
- Browse recent memories

### 🔍 Introspection Tab
- **System Identity**: View comprehensive identity summary
- **Memory Health**: Analyze memory system quality and health scores
- **Focus Analysis**: See what the system has been focusing on (24h window)
- **Behavior Patterns**: View recent behavior analysis and patterns
- **Memory Correlations**: Find related memories based on keywords and temporal proximity
- Real-time introspection data with refresh capabilities

### 🎮 Control Tab
- **Pause/Resume Event Loop**: Control system execution
- **Create Memory Snapshot**: Manual backup trigger
- **Trigger Dream Cycle**: Force introspection cycle
- **Submit Custom Tasks**: Execute user-defined async functions

### 📝 Logs Tab
- Real-time console output
- Filter by log level (info, warning, error)
- Auto-scrolling console view

## Usage

### Starting the Control Panel

**Option 1: Via Configuration**
```python
from project_guardian import GuardianCore

config = {
    "ui_config": {
        "enabled": True,
        "auto_start": True,
        "host": "127.0.0.1",
        "port": 5000,
        "debug": False
    }
}

core = GuardianCore(config)
# Panel will start automatically
```

**Option 2: Manual Start**
```python
from project_guardian import GuardianCore

core = GuardianCore()
core.start_ui_panel(host="127.0.0.1", port=5000)

# Access at http://127.0.0.1:5000
```

**Option 3: Standalone**
```python
from project_guardian import GuardianCore
from project_guardian.ui_control_panel import UIControlPanel

core = GuardianCore()
panel = UIControlPanel(core, host="127.0.0.1", port=5000)
panel.start()
```

### Stopping the Control Panel

```python
core.stop_ui_panel()

# Or on shutdown
core.shutdown()  # Also stops UI panel
```

## API Endpoints

The control panel exposes REST API endpoints:

- `GET /api/status` - Get comprehensive system status
- `POST /api/control/pause` - Pause event loop
- `POST /api/control/resume` - Resume event loop
- `POST /api/memory/snapshot` - Create memory snapshot
- `GET /api/memory/search?q=query` - Search memories
- `POST /api/control/dream-cycle` - Trigger dream cycle
- `GET /api/security/violations` - Get security violations
- `GET /api/tasks/list` - Get active tasks
- `GET /api/introspection/comprehensive` - Get full introspection report
- `GET /api/introspection/identity` - Get identity summary
- `GET /api/introspection/behavior` - Get behavior report
- `GET /api/introspection/health` - Get memory health analysis
- `GET /api/introspection/focus?hours=24` - Get focus analysis
- `GET /api/introspection/correlations?keyword=X&threshold=0.3` - Find memory correlations
- `GET /api/introspection/patterns` - Get memory patterns

## Real-time Updates

The panel uses WebSocket (Socket.IO) for real-time status updates:

- Status updates every 2 seconds
- Log entries streamed in real-time
- Task queue updates
- Security event notifications

## Security Considerations

⚠️ **Important**: The control panel provides direct system access.

1. **Default Binding**: Only binds to `127.0.0.1` (localhost) by default
2. **Network Exposure**: If exposing to network, use reverse proxy with authentication
3. **Task Execution**: Code submission disabled by default (requires secure execution context)
4. **Production**: Add authentication middleware for production deployments

## Dependencies

- `flask>=2.0.0` - Web framework
- `flask-socketio>=5.3.0` - WebSocket support
- All GuardianCore dependencies

## Architecture

```
UIControlPanel
├── Flask App (REST API)
├── SocketIO Server (WebSocket)
├── Real-time Status Polling
└── Integration with GuardianCore
    ├── System Status
    ├── Event Loop Control
    ├── Memory Operations
    ├── Security Monitoring
    └── Task Management
```

## Customization

### Custom Styling

Edit the `CONTROL_PANEL_TEMPLATE` in `ui_control_panel.py` to modify:
- Colors and theme
- Layout and grid structure
- Additional tabs or sections

### Additional Endpoints

Extend `UIControlPanel._setup_routes()` to add custom endpoints:

```python
@self.app.route('/api/custom/endpoint')
def custom_endpoint():
    return jsonify({"message": "Custom functionality"})
```

## Troubleshooting

**Panel won't start:**
- Check if port is already in use
- Verify Flask and Flask-SocketIO are installed
- Check firewall settings

**No updates in dashboard:**
- Verify GuardianCore is running
- Check browser console for WebSocket errors
- Ensure event loop is active

**Tasks not executing:**
- Verify event loop is not paused
- Check task queue status
- Review error logs in console

---

**Status**: ✅ Integrated with GuardianCore  
**Features**: Dashboard, Tasks, Security, Memory, **Introspection**, Control, Logs  
**Introspection**: Full self-analysis capabilities with memory health, focus analysis, and correlations

