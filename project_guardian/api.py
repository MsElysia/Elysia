# project_guardian/api.py
# REST API Interface for Project Guardian

from flask import Flask, jsonify, request, send_from_directory
from .core import GuardianCore
import os

class GuardianAPI:
    """
    REST API interface for Project Guardian.
    Provides web-based control and monitoring capabilities.
    """
    
    def __init__(self, guardian: GuardianCore, port: int = 5000):
        self.guardian = guardian
        self.port = port
        self.app = Flask(__name__)
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.route("/")
        def control_panel():
            return self._get_control_panel()
            
        @self.app.route("/status", methods=["GET"])
        def get_status():
            """Get system status."""
            return jsonify(self.guardian.get_system_status())
            
        @self.app.route("/memory", methods=["GET"])
        def get_memory():
            """Get memory log. Default bounded (200). Use ?limit=0 for full export (admin)."""
            try:
                limit = int(request.args.get("limit", 200))
            except (ValueError, TypeError):
                limit = 200
            if limit > 0 and hasattr(self.guardian.memory, "get_recent_memories"):
                data = self.guardian.memory.get_recent_memories(limit=limit, load_if_needed=True)
            else:
                data = self.guardian.memory.dump_all()
            return jsonify(data)
            
        @self.app.route("/memory", methods=["POST"])
        def add_memory():
            """Add a memory entry."""
            data = request.json
            thought = data.get("thought", "").strip()
            category = data.get("category", "general")
            priority = data.get("priority", 0.5)
            
            if not thought:
                return jsonify({"status": "error", "message": "No thought provided"}), 400
                
            self.guardian.memory.remember(thought, category, priority)
            return jsonify({"status": "ok", "message": "Memory added"})
            
        @self.app.route("/tasks", methods=["GET"])
        def get_tasks():
            """Get active tasks."""
            return jsonify(self.guardian.tasks.get_active_tasks())
            
        @self.app.route("/tasks", methods=["POST"])
        def create_task():
            """Create a new task."""
            data = request.json
            name = data.get("name", "").strip()
            description = data.get("description", "").strip()
            priority = data.get("priority", 0.5)
            category = data.get("category", "general")
            
            if not name or not description:
                return jsonify({"status": "error", "message": "Name and description required"}), 400
                
            task = self.guardian.create_task(name, description, priority, category)
            return jsonify({"status": "ok", "task": task})
            
        @self.app.route("/tasks/<int:task_id>/complete", methods=["POST"])
        def complete_task(task_id):
            """Complete a task."""
            success = self.guardian.tasks.complete_task(task_id)
            if success:
                return jsonify({"status": "ok", "message": "Task completed"})
            else:
                return jsonify({"status": "error", "message": "Task not found"}), 404
                
        @self.app.route("/mutation", methods=["POST"])
        def propose_mutation():
            """Propose a code mutation."""
            data = request.json
            filename = data.get("filename", "").strip()
            code = data.get("code", "").strip()
            require_consensus = data.get("require_consensus", True)
            
            if not filename or not code:
                return jsonify({"status": "error", "message": "Filename and code required"}), 400
                
            result = self.guardian.propose_mutation(filename, code, require_consensus)
            return jsonify({"status": "ok", "result": result})
            
        @self.app.route("/trust", methods=["GET"])
        def get_trust():
            """Get trust matrix."""
            return jsonify(self.guardian.trust.get_trust_report())
            
        @self.app.route("/trust", methods=["POST"])
        def update_trust():
            """Update trust level."""
            data = request.json
            component = data.get("component", "").strip()
            delta = data.get("delta", 0.0)
            reason = data.get("reason", "API update")
            
            if not component:
                return jsonify({"status": "error", "message": "Component required"}), 400
                
            new_trust = self.guardian.trust.update_trust(component, delta, reason)
            return jsonify({"status": "ok", "new_trust": new_trust})
            
        @self.app.route("/consensus", methods=["GET"])
        def get_consensus():
            """Get consensus status."""
            return jsonify(self.guardian.consensus.get_agent_stats())
            
        @self.app.route("/consensus/vote", methods=["POST"])
        def cast_vote():
            """Cast a consensus vote."""
            data = request.json
            voter = data.get("voter", "").strip()
            action = data.get("action", "").strip()
            confidence = data.get("confidence", 1.0)
            reasoning = data.get("reasoning", "")
            
            if not voter or not action:
                return jsonify({"status": "error", "message": "Voter and action required"}), 400
                
            success = self.guardian.consensus.cast_vote(voter, action, confidence, reasoning)
            return jsonify({"status": "ok" if success else "error", "success": success})
            
        @self.app.route("/consensus/decide", methods=["POST"])
        def make_decision():
            """Make a consensus decision."""
            data = request.json
            action = data.get("action", None)
            
            decision = self.guardian.consensus.decide(action)
            return jsonify({"status": "ok", "decision": decision})
            
        @self.app.route("/safety/check", methods=["GET"])
        def safety_check():
            """Run safety check."""
            return jsonify(self.guardian.run_safety_check())
            
        @self.app.route("/safety/challenge", methods=["POST"])
        def safety_challenge():
            """Challenge a claim."""
            data = request.json
            claim = data.get("claim", "").strip()
            context = data.get("context", "API challenge")
            
            if not claim:
                return jsonify({"status": "error", "message": "Claim required"}), 400
                
            challenge = self.guardian.safety.challenge(claim, context)
            return jsonify({"status": "ok", "challenge": challenge})
            
        @self.app.route("/rollback/backups", methods=["GET"])
        def get_backups():
            """Get backup statistics."""
            return jsonify(self.guardian.rollback.get_backup_stats())
            
        @self.app.route("/rollback/restore", methods=["POST"])
        def restore_backup():
            """Restore from backup."""
            data = request.json
            filename = data.get("filename", "").strip()
            backup_name = data.get("backup_name", "").strip()
            
            if not filename or not backup_name:
                return jsonify({"status": "error", "message": "Filename and backup name required"}), 400
                
            result = self.guardian.rollback.restore_backup(filename, backup_name)
            return jsonify({"status": "ok", "result": result})
            
        @self.app.route("/summary", methods=["GET"])
        def get_summary():
            """Get system summary."""
            return jsonify({"summary": self.guardian.get_system_summary()})
            
        @self.app.route("/shutdown", methods=["POST"])
        def shutdown():
            """Safely shutdown the system."""
            self.guardian.shutdown()
            return jsonify({"status": "ok", "message": "Shutdown initiated"})
            
    def _get_control_panel(self):
        """Generate a simple HTML control panel."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Project Guardian Control Panel</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ccc; }}
                button {{ padding: 10px; margin: 5px; }}
                input, textarea {{ width: 100%; padding: 5px; margin: 5px 0; }}
            </style>
        </head>
        <body>
            <h1>🛡️ Project Guardian Control Panel</h1>
            
            <div class="section">
                <h2>System Status</h2>
                <button onclick="getStatus()">Refresh Status</button>
                <div id="status"></div>
            </div>
            
            <div class="section">
                <h2>Memory Management</h2>
                <input type="text" id="memoryThought" placeholder="Memory content">
                <input type="text" id="memoryCategory" placeholder="Category (optional)">
                <button onclick="addMemory()">Add Memory</button>
                <button onclick="getMemory()">Get Memory</button>
                <div id="memory"></div>
            </div>
            
            <div class="section">
                <h2>Task Management</h2>
                <input type="text" id="taskName" placeholder="Task name">
                <textarea id="taskDescription" placeholder="Task description"></textarea>
                <button onclick="createTask()">Create Task</button>
                <button onclick="getTasks()">Get Tasks</button>
                <div id="tasks"></div>
            </div>
            
            <div class="section">
                <h2>Safety & Trust</h2>
                <button onclick="safetyCheck()">Run Safety Check</button>
                <button onclick="getTrust()">Get Trust Matrix</button>
                <div id="safety"></div>
            </div>
            
            <script>
                async function getStatus() {{
                    const response = await fetch('/status');
                    const data = await response.json();
                    document.getElementById('status').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                }}
                
                async function addMemory() {{
                    const thought = document.getElementById('memoryThought').value;
                    const category = document.getElementById('memoryCategory').value || 'general';
                    
                    const response = await fetch('/memory', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{thought, category}})
                    }});
                    
                    const data = await response.json();
                    alert(data.message);
                }}
                
                async function getMemory() {{
                    const response = await fetch('/memory');
                    const data = await response.json();
                    document.getElementById('memory').innerHTML = '<pre>' + JSON.stringify(data.slice(-5), null, 2) + '</pre>';
                }}
                
                async function createTask() {{
                    const name = document.getElementById('taskName').value;
                    const description = document.getElementById('taskDescription').value;
                    
                    const response = await fetch('/tasks', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{name, description}})
                    }});
                    
                    const data = await response.json();
                    alert(data.status === 'ok' ? 'Task created' : 'Error creating task');
                }}
                
                async function getTasks() {{
                    const response = await fetch('/tasks');
                    const data = await response.json();
                    document.getElementById('tasks').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                }}
                
                async function safetyCheck() {{
                    const response = await fetch('/safety/check');
                    const data = await response.json();
                    document.getElementById('safety').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                }}
                
                async function getTrust() {{
                    const response = await fetch('/trust');
                    const data = await response.json();
                    document.getElementById('safety').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                }}
                
                // Load initial status
                getStatus();
            </script>
        </body>
        </html>
        """
        
    def run(self, debug: bool = False):
        """Run the API server."""
        print(f"[Guardian API] Starting server on port {self.port}")
        self.app.run(host="0.0.0.0", port=self.port, debug=debug) 