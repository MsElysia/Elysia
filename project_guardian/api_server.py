# project_guardian/api_server.py
# REST API Server: Expose System State and Controls via REST
# Provides external API access to Elysia system

import logging
import json
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import threading

try:
    from .system_orchestrator import SystemOrchestrator
    from .mutation_engine import MutationEngine
    from .trust_registry import TrustRegistry
    from .franchise_manager import FranchiseManager
    from .revenue_sharing import RevenueSharing
    from .master_slave_controller import MasterSlaveController
    from .health_monitor import HealthMonitor, get_health_monitor
except ImportError:
    from system_orchestrator import SystemOrchestrator
    from mutation_engine import MutationEngine
    from trust_registry import TrustRegistry
    from franchise_manager import FranchiseManager
    from revenue_sharing import RevenueSharing
    from master_slave_controller import MasterSlaveController
    try:
        from health_monitor import HealthMonitor, get_health_monitor
    except ImportError:
        HealthMonitor = None
        get_health_monitor = None

logger = logging.getLogger(__name__)


class APIServer:
    """
    REST API Server for Elysia system.
    Provides external access to system state, controls, and operations.
    """
    
    def __init__(
        self,
        orchestrator: Optional[SystemOrchestrator] = None,
        host: str = "0.0.0.0",
        port: int = 8080,
        enable_cors: bool = True
    ):
        """
        Initialize API Server.
        
        Args:
            orchestrator: SystemOrchestrator instance
            host: Host to bind to
            port: Port to listen on
            enable_cors: Enable CORS for web access
        """
        self.orchestrator = orchestrator
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        
        if enable_cors:
            CORS(self.app)  # Enable CORS for all routes
        
        # Health monitor
        self.health_monitor = get_health_monitor() if get_health_monitor else None
        
        # Server thread
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Setup routes
        self._setup_routes()
        
        # Register API server component health
        if self.health_monitor and HealthMonitor:
            from .health_monitor import HealthStatus
            self.health_monitor.check_component_health(
                "api_server",
                HealthStatus.HEALTHY,
                "API server initialized"
            )
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "started_at": datetime.now()
        }
    
    def _setup_routes(self):
        """Setup API routes."""
        
        # Health check
        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            """Health check endpoint with detailed health status."""
            try:
                if get_health_monitor:
                    monitor = get_health_monitor()
                    health_response = monitor.get_health_endpoint_response()
                    status_code = health_response.pop("http_status", 200)
                    return jsonify(health_response), status_code
                else:
                    # Fallback simple health check
                    return jsonify({
                        "status": "healthy",
                        "timestamp": datetime.now().isoformat(),
                        "api_version": "1.0",
                        "components": {},
                        "resources": {}
                    })
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                return jsonify({
                    "status": "error",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                }), 503
        
        # Metrics endpoint
        @self.app.route('/api/metrics', methods=['GET'])
        def get_metrics():
            """Get system metrics for monitoring."""
            try:
                metrics = {}
                
                # Health monitor metrics
                if self.health_monitor:
                    metrics.update(self.health_monitor.get_metrics())
                
                # API server stats
                metrics["api_server"] = {
                    "total_requests": self.stats["total_requests"],
                    "successful_requests": self.stats["successful_requests"],
                    "failed_requests": self.stats["failed_requests"],
                    "uptime": (
                        (datetime.now() - self.stats["started_at"]).total_seconds()
                        if self.stats["started_at"] else None
                    )
                }
                
                self._record_request(success=True)
                return jsonify(metrics)
            except Exception as e:
                logger.error(f"Error getting metrics: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # System status
        @self.app.route('/api/system/status', methods=['GET'])
        def get_system_status():
            """Get system status."""
            try:
                if not self.orchestrator:
                    return jsonify({"error": "System not initialized"}), 503
                
                status = self.orchestrator.get_system_status()
                self._record_request(success=True)
                return jsonify(status)
            except Exception as e:
                logger.error(f"Error getting system status: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # System statistics
        @self.app.route('/api/system/stats', methods=['GET'])
        def get_system_stats():
            """Get system statistics."""
            try:
                if not self.orchestrator:
                    return jsonify({"error": "System not initialized"}), 503
                
                stats = {
                    "uptime": self.stats.get("started_at"),
                    "api_requests": {
                        "total": self.stats["total_requests"],
                        "successful": self.stats["successful_requests"],
                        "failed": self.stats["failed_requests"]
                    }
                }
                
                # Add orchestrator stats if available
                if self.orchestrator:
                    orchestrator_stats = self.orchestrator.get_system_status()
                    stats["system"] = orchestrator_stats
                
                self._record_request(success=True)
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Error getting system stats: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Mutation endpoints
        @self.app.route('/api/mutations', methods=['GET'])
        def list_mutations():
            """List all mutation proposals."""
            try:
                if not self.orchestrator or not self.orchestrator.mutation_engine:
                    return jsonify({"error": "MutationEngine not available"}), 503
                
                mutations = self.orchestrator.mutation_engine.get_all_proposals()
                mutations_data = [m.to_dict() for m in mutations]
                
                self._record_request(success=True)
                return jsonify({"mutations": mutations_data})
            except Exception as e:
                logger.error(f"Error listing mutations: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/mutations/<mutation_id>', methods=['GET'])
        def get_mutation(mutation_id):
            """Get specific mutation proposal."""
            try:
                if not self.orchestrator or not self.orchestrator.mutation_engine:
                    return jsonify({"error": "MutationEngine not available"}), 503
                
                proposal = self.orchestrator.mutation_engine.get_proposal(mutation_id)
                if not proposal:
                    return jsonify({"error": "Mutation not found"}), 404
                
                self._record_request(success=True)
                return jsonify(proposal.to_dict())
            except Exception as e:
                logger.error(f"Error getting mutation: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Trust Registry endpoints
        @self.app.route('/api/trust/nodes', methods=['GET'])
        def list_trust_nodes():
            """List all nodes in trust registry."""
            try:
                if not self.orchestrator or not self.orchestrator.trust_registry:
                    return jsonify({"error": "TrustRegistry not available"}), 503
                
                nodes = self.orchestrator.trust_registry.list_nodes()
                nodes_data = []
                for node_id in nodes:
                    trust = self.orchestrator.trust_registry.get_node_trust(node_id)
                    if trust:
                        nodes_data.append(trust.to_dict())
                
                self._record_request(success=True)
                return jsonify({"nodes": nodes_data})
            except Exception as e:
                logger.error(f"Error listing trust nodes: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/trust/nodes/<node_id>', methods=['GET'])
        def get_trust_node(node_id):
            """Get trust data for specific node."""
            try:
                if not self.orchestrator or not self.orchestrator.trust_registry:
                    return jsonify({"error": "TrustRegistry not available"}), 503
                
                trust = self.orchestrator.trust_registry.get_node_trust(node_id)
                if not trust:
                    return jsonify({"error": "Node not found"}), 404
                
                self._record_request(success=True)
                return jsonify(trust.to_dict())
            except Exception as e:
                logger.error(f"Error getting trust node: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Franchise endpoints
        @self.app.route('/api/franchises', methods=['GET'])
        def list_franchises():
            """List all franchises."""
            try:
                if not self.orchestrator or not hasattr(self.orchestrator, 'franchise_manager'):
                    return jsonify({"error": "FranchiseManager not available"}), 503
                
                # Get franchises from orchestrator if available
                franchises = []
                if self.orchestrator.franchise_manager:
                    agreements = self.orchestrator.franchise_manager.agreements
                    franchises = [
                        {
                            "agreement_id": aid,
                            "franchise_id": agreement.franchise_id,
                            "status": agreement.status.value,
                            "created_at": agreement.created_at.isoformat()
                        }
                        for aid, agreement in agreements.items()
                    ]
                
                self._record_request(success=True)
                return jsonify({"franchises": franchises})
            except Exception as e:
                logger.error(f"Error listing franchises: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/franchises/<franchise_id>', methods=['GET'])
        def get_franchise(franchise_id):
            """Get franchise report."""
            try:
                if not self.orchestrator or not hasattr(self.orchestrator, 'franchise_manager'):
                    return jsonify({"error": "FranchiseManager not available"}), 503
                
                if not self.orchestrator.franchise_manager:
                    return jsonify({"error": "FranchiseManager not initialized"}), 503
                
                report = self.orchestrator.franchise_manager.get_franchise_report(franchise_id)
                
                self._record_request(success=True)
                return jsonify(report)
            except Exception as e:
                logger.error(f"Error getting franchise: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Revenue endpoints
        @self.app.route('/api/revenue/summary', methods=['GET'])
        def get_revenue_summary():
            """Get master revenue summary."""
            try:
                if not self.orchestrator or not hasattr(self.orchestrator, 'revenue_sharing'):
                    return jsonify({"error": "RevenueSharing not available"}), 503
                
                if not self.orchestrator.revenue_sharing:
                    return jsonify({"error": "RevenueSharing not initialized"}), 503
                
                days = request.args.get('days', 30, type=int)
                summary = self.orchestrator.revenue_sharing.get_master_revenue_summary(days=days)
                
                self._record_request(success=True)
                return jsonify(summary)
            except Exception as e:
                logger.error(f"Error getting revenue summary: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Task submission
        @self.app.route('/api/tasks', methods=['POST'])
        def submit_task():
            """Submit a task to the system."""
            try:
                if not self.orchestrator:
                    return jsonify({"error": "System not initialized"}), 503
                
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No JSON data provided"}), 400
                
                # Extract task parameters
                task_func_name = data.get("function")
                priority = data.get("priority", 5)
                module = data.get("module", "api")
                kwargs = data.get("kwargs", {})
                
                if not task_func_name:
                    return jsonify({"error": "function name required"}), 400
                
                # Create a simple task function
                def task_function():
                    # In production, this would call the actual function
                    return {"status": "task_submitted", "function": task_func_name, "kwargs": kwargs}
                
                # Submit task
                task_id = self.orchestrator.submit_task(
                    task_function,
                    priority=priority,
                    module=module
                )
                
                self._record_request(success=True)
                return jsonify({
                    "success": True,
                    "task_id": task_id,
                    "message": "Task submitted successfully"
                }), 201
            except Exception as e:
                logger.error(f"Error submitting task: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Memory endpoints
        @self.app.route('/api/memory/search', methods=['POST'])
        def search_memory():
            """Search memories."""
            try:
                if not self.orchestrator or not self.orchestrator.memory:
                    return jsonify({"error": "MemoryCore not available"}), 503
                
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No JSON data provided"}), 400
                
                keyword = data.get("keyword")
                limit = data.get("limit", 10)
                
                if not keyword:
                    return jsonify({"error": "keyword required"}), 400
                
                memories = self.orchestrator.memory.search_memories(keyword, limit=limit)
                
                self._record_request(success=True)
                return jsonify({"memories": memories})
            except Exception as e:
                logger.error(f"Error searching memory: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Security audit endpoints
        @self.app.route('/api/security/audit', methods=['GET'])
        def run_security_audit():
            """Run security audit."""
            try:
                # Try to get GuardianCore if available
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'run_security_audit'):
                    audit_results = guardian_core.run_security_audit()
                else:
                    # Fallback: create auditor directly
                    from .security_audit import SecurityAuditor
                    auditor = SecurityAuditor()
                    audit_results = auditor.run_audit()
                
                self._record_request(success=True)
                return jsonify(audit_results)
            except Exception as e:
                logger.error(f"Error running security audit: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Resource monitoring endpoints
        @self.app.route('/api/resources/status', methods=['GET'])
        def get_resource_status():
            """Get resource usage and limits status."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'get_resource_status'):
                    resource_status = guardian_core.get_resource_status()
                else:
                    resource_status = {"error": "Resource monitoring not available"}
                
                self._record_request(success=True)
                return jsonify(resource_status)
            except Exception as e:
                logger.error(f"Error getting resource status: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/resources/stats', methods=['GET'])
        def get_resource_stats():
            """Get current resource statistics."""
            try:
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'get_resource_stats'):
                    resource_stats = guardian_core.get_resource_stats()
                else:
                    resource_stats = {}
                
                self._record_request(success=True)
                return jsonify(resource_stats)
            except Exception as e:
                logger.error(f"Error getting resource stats: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/resources/violations', methods=['GET'])
        def get_resource_violations():
            """Get resource limit violations."""
            try:
                limit = request.args.get('limit', type=int)
                guardian_core = getattr(self.orchestrator, 'guardian_core', None) if self.orchestrator else None
                
                if guardian_core and hasattr(guardian_core, 'get_resource_violations'):
                    violations = guardian_core.get_resource_violations(limit=limit)
                else:
                    violations = []
                
                self._record_request(success=True)
                return jsonify({"violations": violations})
            except Exception as e:
                logger.error(f"Error getting resource violations: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Configuration validation endpoint
        @self.app.route('/api/config/validation', methods=['GET'])
        def get_config_validation():
            """Get configuration validation status."""
            try:
                if not self.orchestrator or not self.orchestrator.guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                verification = self.orchestrator.guardian_core.get_startup_verification()
                self._record_request(success=True)
                return jsonify(verification)
            except Exception as e:
                logger.error(f"Error getting config validation: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/health/runtime', methods=['GET'])
        def get_runtime_health():
            """Get current runtime health status."""
            try:
                if not self.orchestrator or not self.orchestrator.guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                health = self.orchestrator.guardian_core.get_runtime_health()
                self._record_request(success=True)
                return jsonify(health)
            except Exception as e:
                logger.error(f"Error getting runtime health: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/health/history', methods=['GET'])
        def get_health_history():
            """Get runtime health check history."""
            try:
                if not self.orchestrator or not self.orchestrator.guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                limit = request.args.get('limit', type=int)
                history = self.orchestrator.guardian_core.get_runtime_health_history(limit=limit)
                self._record_request(success=True)
                return jsonify({"history": history})
            except Exception as e:
                logger.error(f"Error getting health history: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        @self.app.route('/api/startup/verification', methods=['GET'])
        def get_startup_verification():
            """Get startup verification results."""
            try:
                if not self.orchestrator or not self.orchestrator.guardian_core:
                    return jsonify({"error": "GuardianCore not available"}), 503
                
                verification = self.orchestrator.guardian_core.get_startup_verification()
                self._record_request(success=True)
                return jsonify(verification)
            except Exception as e:
                logger.error(f"Error getting startup verification: {e}", exc_info=True)
                self._record_request(success=False)
                return jsonify({"error": str(e)}), 500
        
        # Error handlers
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({"error": "Endpoint not found"}), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({"error": "Internal server error"}), 500
    
    def _record_request(self, success: bool = True):
        """Record API request statistics."""
        self.stats["total_requests"] += 1
        if success:
            self.stats["successful_requests"] += 1
        else:
            self.stats["failed_requests"] += 1
    
    def start(self, threaded: bool = True):
        """
        Start the API server.
        
        Args:
            threaded: If True, run in background thread
        """
        if self._running:
            logger.warning("API server already running")
            return
        
        self.stats["started_at"] = datetime.now().isoformat()
        
        if threaded:
            def run_server():
                self.app.run(host=self.host, port=self.port, debug=False)
            
            self._server_thread = threading.Thread(target=run_server, daemon=True)
            self._server_thread.start()
            self._running = True
            logger.info(f"API server started on http://{self.host}:{self.port}")
        else:
            logger.info(f"API server starting on http://{self.host}:{self.port}")
            logger.warning("Running in non-threaded mode - this will block")
            self._running = True
            self.app.run(host=self.host, port=self.port, debug=False)
    
    def stop(self):
        """Stop the API server."""
        if not self._running:
            return
        
        # Flask doesn't have a built-in stop method
        # In production, use a proper WSGI server like gunicorn
        logger.warning("Flask development server cannot be stopped gracefully")
        self._running = False
        logger.info("API server stopped")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get API server statistics."""
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "started_at": self.stats["started_at"],
            "total_requests": self.stats["total_requests"],
            "successful_requests": self.stats["successful_requests"],
            "failed_requests": self.stats["failed_requests"],
            "success_rate": (
                self.stats["successful_requests"] / max(1, self.stats["total_requests"])
            )
        }


# Example usage
if __name__ == "__main__":
    # Initialize system
    orchestrator = SystemOrchestrator()
    # await orchestrator.initialize()  # Would need async context
    
    # Create API server
    api_server = APIServer(
        orchestrator=orchestrator,
        host="0.0.0.0",
        port=8080
    )
    
    # Start server
    api_server.start(threaded=False)  # Run in main thread for testing

