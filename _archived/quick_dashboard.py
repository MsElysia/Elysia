#!/usr/bin/env python3
"""
Quick Dashboard for Elysia - No GuardianCore Required
Provides immediate access to system status
"""

from flask import Flask, render_template_string, jsonify
import json
import os
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
start_time = datetime.now()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Elysia Quick Dashboard</title>
    <meta charset="utf-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72, #2a5298);
            color: #fff;
            padding: 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        h1 {
            font-size: 32px;
            text-align: center;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        .status-bar {
            background: rgba(255,255,255,0.15);
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            backdrop-filter: blur(5px);
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
            background: #00ff00;
            box-shadow: 0 0 10px #00ff00;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }
        .card {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 25px;
            border-radius: 15px;
            border: 1px solid rgba(255,255,255,0.2);
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.2);
        }
        .card h2 {
            font-size: 20px;
            margin-bottom: 20px;
            color: #fff;
            border-bottom: 2px solid rgba(255,255,255,0.3);
            padding-bottom: 10px;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .metric:last-child {
            border-bottom: none;
        }
        .metric-value {
            font-weight: bold;
            color: #4fc3f7;
        }
        button {
            background: linear-gradient(45deg, #2196F3, #21CBF3);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            margin: 5px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(33, 203, 243, 0.3);
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(33, 203, 243, 0.4);
        }
        .actions {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 25px;
            text-align: center;
        }
        .success { color: #4caf50; }
        .warning { color: #ff9800; }
        .error { color: #f44336; }
        .console {
            background: rgba(0,0,0,0.5);
            color: #0f0;
            padding: 20px;
            border-radius: 10px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            height: 300px;
            overflow-y: auto;
            margin-top: 20px;
        }
        .log-entry {
            margin: 5px 0;
            padding: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 Elysia Quick Dashboard</h1>
        </header>
        
        <div class="status-bar">
            <div>
                <span class="status-indicator"></span>
                <strong>System Status:</strong> <span id="system-status">RUNNING</span>
            </div>
            <div>
                <strong>Uptime:</strong> <span id="uptime">0</span> seconds
            </div>
        </div>
        
        <div class="actions">
            <h2 style="margin-bottom: 15px;">Quick Actions</h2>
            <button onclick="refreshDashboard()">🔄 Refresh Dashboard</button>
            <button onclick="checkMemory()">🧠 Check Memory</button>
            <button onclick="viewApiKeys()">🔑 View API Keys</button>
            <button onclick="systemHealth()">💚 System Health</button>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>📊 System Information</h2>
                <div class="metric">
                    <span>Project Path:</span>
                    <span class="metric-value">{{ project_path }}</span>
                </div>
                <div class="metric">
                    <span>Python Version:</span>
                    <span class="metric-value">{{ python_version }}</span>
                </div>
                <div class="metric">
                    <span>Start Time:</span>
                    <span class="metric-value" id="start-time">{{ start_time }}</span>
                </div>
                <div class="metric">
                    <span>Status:</span>
                    <span class="metric-value success">ACTIVE</span>
                </div>
            </div>
            
            <div class="card">
                <h2>🧠 Memory System</h2>
                <div class="metric">
                    <span>Memory File:</span>
                    <span class="metric-value" id="memory-file">Checking...</span>
                </div>
                <div class="metric">
                    <span>Total Memories:</span>
                    <span class="metric-value" id="total-memories">Loading...</span>
                </div>
                <div class="metric">
                    <span>Vector Index:</span>
                    <span class="metric-value" id="vector-status">Checking...</span>
                </div>
            </div>
            
            <div class="card">
                <h2>🔑 API Configuration</h2>
                <div class="metric">
                    <span>OpenAI Key:</span>
                    <span class="metric-value" id="openai-status">Checking...</span>
                </div>
                <div class="metric">
                    <span>Total API Keys:</span>
                    <span class="metric-value" id="total-keys">Checking...</span>
                </div>
                <div class="metric">
                    <span>Configuration:</span>
                    <span class="metric-value success">LOADED</span>
                </div>
            </div>
            
            <div class="card">
                <h2>📁 File System</h2>
                <div class="metric">
                    <span>Memory Files:</span>
                    <span class="metric-value" id="memory-files">Checking...</span>
                </div>
                <div class="metric">
                    <span>Log Files:</span>
                    <span class="metric-value" id="log-files">Checking...</span>
                </div>
                <div class="metric">
                    <span>Config Files:</span>
                    <span class="metric-value" id="config-files">Checking...</span>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>📝 System Console</h2>
            <div class="console" id="console">
                <div class="log-entry">[SYSTEM] Dashboard initialized successfully</div>
                <div class="log-entry">[INFO] Ready for operations</div>
            </div>
        </div>
    </div>
    
    <script>
        let uptime = 0;
        
        function addLog(message, type = 'INFO') {
            const console = document.getElementById('console');
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            const timestamp = new Date().toLocaleTimeString();
            entry.textContent = `[${timestamp}] [${type}] ${message}`;
            console.appendChild(entry);
            console.scrollTop = console.scrollHeight;
        }
        
        function refreshDashboard() {
            addLog('Refreshing dashboard...', 'INFO');
            fetch('/api/dashboard')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('memory-file').textContent = data.memory_file || 'Not found';
                    document.getElementById('total-memories').textContent = data.total_memories || '0';
                    document.getElementById('vector-status').textContent = data.vector_enabled ? 'Enabled' : 'Disabled';
                    document.getElementById('openai-status').textContent = data.openai_key ? 'Loaded' : 'Not found';
                    document.getElementById('total-keys').textContent = data.total_keys || '0';
                    document.getElementById('memory-files').textContent = data.memory_files || '0';
                    document.getElementById('log-files').textContent = data.log_files || '0';
                    document.getElementById('config-files').textContent = data.config_files || '0';
                    addLog('Dashboard refreshed successfully', 'SUCCESS');
                })
                .catch(err => {
                    addLog('Error refreshing dashboard: ' + err, 'ERROR');
                });
        }
        
        function checkMemory() {
            addLog('Checking memory system...', 'INFO');
            fetch('/api/memory-check')
                .then(r => r.json())
                .then(data => {
                    addLog(`Memory check complete: ${data.total_memories} memories found`, 'SUCCESS');
                    document.getElementById('total-memories').textContent = data.total_memories || '0';
                })
                .catch(err => {
                    addLog('Error checking memory: ' + err, 'ERROR');
                });
        }
        
        function viewApiKeys() {
            addLog('Checking API keys...', 'INFO');
            fetch('/api/api-keys')
                .then(r => r.json())
                .then(data => {
                    addLog(`Found ${data.count} API keys`, 'SUCCESS');
                    for (let key in data.keys) {
                        addLog(`  ${key}: ${data.keys[key]}`, 'INFO');
                    }
                })
                .catch(err => {
                    addLog('Error checking API keys: ' + err, 'ERROR');
                });
        }
        
        function systemHealth() {
            addLog('Running system health check...', 'INFO');
            fetch('/api/health')
                .then(r => r.json())
                .then(data => {
                    addLog('System health check complete', 'SUCCESS');
                    addLog(`  Status: ${data.status}`, 'INFO');
                    addLog(`  Memory: ${data.memory_status}`, 'INFO');
                    addLog(`  Files: ${data.files_status}`, 'INFO');
                })
                .catch(err => {
                    addLog('Error checking system health: ' + err, 'ERROR');
                });
        }
        
        // Update uptime counter
        setInterval(() => {
            uptime++;
            document.getElementById('uptime').textContent = uptime;
        }, 1000);
        
        // Initial load
        setTimeout(refreshDashboard, 1000);
        
        addLog('Dashboard ready - All systems operational', 'SUCCESS');
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    import sys
    return render_template_string(HTML_TEMPLATE,
        project_path=os.getcwd(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        start_time=start_time.strftime("%H:%M:%S")
    )

@app.route('/api/dashboard')
def dashboard_status():
    """Quick dashboard status without GuardianCore"""
    try:
        # Check memory file
        memory_file = Path("guardian_memory.json")
        total_memories = 0
        if memory_file.exists():
            try:
                with open(memory_file, 'r') as f:
                    data = json.load(f)
                    total_memories = len(data.get('memories', []))
            except:
                pass
        
        # Check for vector index
        vector_enabled = Path("memory/vectors/index.faiss").exists()
        
        # Check API keys
        openai_key = bool(os.getenv('OPENAI_API_KEY'))
        total_keys = sum(1 for k in os.environ if 'KEY' in k or 'TOKEN' in k)
        
        # Count files
        memory_files = len(list(Path(".").glob("*.json")))
        log_files = len(list(Path(".").glob("*.log")))
        config_files = len(list(Path("config").glob("*.json"))) if Path("config").exists() else 0
        
        return jsonify({
            "memory_file": str(memory_file) if memory_file.exists() else "Not found",
            "total_memories": total_memories,
            "vector_enabled": vector_enabled,
            "openai_key": openai_key,
            "total_keys": total_keys,
            "memory_files": memory_files,
            "log_files": log_files,
            "config_files": config_files
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/memory-check')
def memory_check():
    """Check memory system"""
    try:
        memory_file = Path("guardian_memory.json")
        if memory_file.exists():
            with open(memory_file, 'r') as f:
                data = json.load(f)
                return jsonify({
                    "total_memories": len(data.get('memories', [])),
                    "file_size": memory_file.stat().st_size
                })
        return jsonify({"total_memories": 0, "file_size": 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/api-keys')
def api_keys():
    """Check API keys"""
    keys = {}
    for key in ['OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'COHERE_API_KEY', 
                'HUGGINGFACE_API_KEY', 'REPLICATE_API_KEY', 'ALPHA_VANTAGE_API_KEY']:
        if os.getenv(key):
            keys[key] = "Loaded"
        else:
            keys[key] = "Not found"
    return jsonify({"count": sum(1 for v in keys.values() if v == "Loaded"), "keys": keys})

@app.route('/api/health')
def health():
    """System health check"""
    return jsonify({
        "status": "healthy",
        "uptime": (datetime.now() - start_time).total_seconds(),
        "memory_status": "OK" if Path("guardian_memory.json").exists() else "Missing",
        "files_status": "OK"
    })

if __name__ == '__main__':
    print("\n" + "="*60)
    print("ELYSIA QUICK DASHBOARD")
    print("="*60)
    print(f"\nStarting dashboard server...")
    print(f"Open your browser to: http://127.0.0.1:5000")
    print("Press Ctrl+C to stop\n")
    app.run(host='127.0.0.1', port=5000, debug=False)






























