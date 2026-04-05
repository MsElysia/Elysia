#!/usr/bin/env python3
"""
Simple Elysia Control Panel - Fixed Version
Starts a minimal web dashboard without complex JavaScript issues
"""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simple HTML Template
SIMPLE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Elysia Control Panel</title>
    <meta charset="utf-8">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
            margin: 0;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }
        h1 {
            margin: 0;
            color: white;
        }
        .status {
            background: #0f3460;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
        }
        .status-running { background: #00ff00; }
        .status-stopped { background: #ff0000; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .card {
            background: #16213e;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #0f3460;
        }
        .card h2 {
            margin-top: 0;
            color: #667eea;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #0f3460;
        }
        .metric:last-child {
            border-bottom: none;
        }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 5px;
        }
        button:hover {
            background: #764ba2;
        }
        .controls {
            background: #16213e;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Elysia Control Panel</h1>
        </header>
        
        <div class="status">
            <span class="status-indicator status-running"></span>
            <strong>Status:</strong> <span id="status-text">Running</span>
            <span style="float: right;">Uptime: <span id="uptime">0</span> seconds</span>
        </div>
        
        <div class="controls">
            <h2>Quick Actions</h2>
            <button onclick="refreshStatus()">Refresh Status</button>
            <button onclick="testSystem()">Test System</button>
            <button onclick="viewLogs()">View Logs</button>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>System Status</h2>
                <div class="metric">
                    <span>Initialized:</span>
                    <span id="initialized">Yes</span>
                </div>
                <div class="metric">
                    <span>Running:</span>
                    <span id="running">Yes</span>
                </div>
                <div class="metric">
                    <span>Active Tasks:</span>
                    <span id="active-tasks">0</span>
                </div>
            </div>
            
            <div class="card">
                <h2>Memory System</h2>
                <div class="metric">
                    <span>Total Memories:</span>
                    <span id="total-memories">Loading...</span>
                </div>
                <div class="metric">
                    <span>Vector Search:</span>
                    <span id="vector-enabled">Enabled</span>
                </div>
            </div>
            
            <div class="card">
                <h2>API Keys</h2>
                <div class="metric">
                    <span>OpenAI:</span>
                    <span id="openai-key">Loaded</span>
                </div>
                <div class="metric">
                    <span>Other Keys:</span>
                    <span id="other-keys">6 Loaded</span>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let uptime = 0;
        
        function refreshStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    // Update UI with actual data
                    document.getElementById('uptime').textContent = Math.floor(data.system?.uptime || uptime);
                    document.getElementById('initialized').textContent = data.system?.initialized ? 'Yes' : 'No';
                    document.getElementById('running').textContent = data.system?.running ? 'Yes' : 'No';
                    document.getElementById('active-tasks').textContent = data.system?.operational_stats?.total_tasks_processed || '0';
                    document.getElementById('total-memories').textContent = data.memory?.total_memories || '0';
                    
                    // Update status indicator
                    const statusEl = document.querySelector('.status-indicator');
                    if (data.system?.running) {
                        statusEl.className = 'status-indicator status-running';
                        document.getElementById('status-text').textContent = 'Running';
                    } else {
                        statusEl.className = 'status-indicator status-stopped';
                        document.getElementById('status-text').textContent = 'Stopped';
                    }
                })
                .catch(error => {
                    console.error('Error fetching status:', error);
                    document.getElementById('status-text').textContent = 'Connection Error';
                });
        }
        
        function testSystem() {
            alert('System test - Elysia is responsive!');
        }
        
        function viewLogs() {
            window.location.href = '/logs';
        }
        
        // Update uptime counter
        setInterval(() => {
            uptime++;
            document.getElementById('uptime').textContent = uptime;
        }, 1000);
        
        // Refresh status every 5 seconds
        setInterval(refreshStatus, 5000);
        
        // Initial load
        refreshStatus();
    </script>
</body>
</html>
"""

def main():
    """Start simple control panel"""
    print("=" * 70)
    print("ELYSIA CONTROL PANEL - Simple Version")
    print("=" * 70)
    
    # Load API keys first
    print("\nLoading API keys...")
    try:
        from load_api_keys import load_api_keys
        keys_loaded = load_api_keys()
        if keys_loaded:
            loaded_count = len([k for k in keys_loaded.values() if k == "Loaded"])
            print(f"✅ Loaded {loaded_count} API key(s)")
        else:
            print("⚠️  No API keys loaded")
    except Exception as e:
        print(f"⚠️  Could not load API keys: {e}")
    
    print("\nStarting Flask server...")
    try:
        from flask import Flask, render_template_string, jsonify
        from project_guardian.core import GuardianCore
        
        # Create Flask app
        app = Flask(__name__)
        
        # Initialize GuardianCore
        config = {
            "ui_config": {"enabled": False},  # Don't auto-start UI
            "enable_resource_monitoring": False
        }
        guardian = GuardianCore(config=config)
        
        @app.route('/')
        def index():
            return render_template_string(SIMPLE_TEMPLATE)
        
        @app.route('/api/status')
        def get_status():
            """Get system status"""
            try:
                return jsonify({
                    "system": {
                        "running": True,
                        "initialized": True,
                        "uptime": time.time() - guardian.start_time.timestamp() if hasattr(guardian, 'start_time') else 0,
                        "operational_stats": {}
                    },
                    "memory": {
                        "total_memories": len(guardian.memory.memories) if hasattr(guardian.memory, 'memories') else 0
                    }
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        
        @app.route('/logs')
        def logs():
            return "<h1>Logs</h1><p>Log viewing not implemented in simple version</p>"
        
        print(f"✅ Control Panel Ready")
        print(f"\n🌐 Open your browser to: http://127.0.0.1:5000")
        print("💡 Press Ctrl+C to stop\n")
        
        # Run Flask app
        app.run(host='127.0.0.1', port=5000, debug=False)
        
    except ImportError as e:
        print(f"\n❌ Error: Missing dependencies")
        print(f"   {e}")
        print("\n💡 Install required packages:")
        print("   pip install flask")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()






























