# run_elysia.py
# Main entry point to run the Elysia system

import sys
import logging
import signal
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from project_guardian.core import GuardianCore
from project_guardian.api_server import APIServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Run the Elysia system."""
    print("\n" + "="*70)
    print("ELYSIA SYSTEM - Starting...")
    print("="*70)
    
    # Configuration
    config = {
        "enable_resource_monitoring": True,
        "enable_runtime_health_monitoring": True,
    }
    
    # Initialize core system
    print("\n[1/3] Initializing Guardian Core...")
    core = GuardianCore(config=config)
    print("  [OK] Core system initialized")
    
    # Initialize API server
    print("\n[2/3] Starting API Server...")
    try:
        api_server = APIServer(orchestrator=None)  # Can pass orchestrator if available
        api_thread = threading.Thread(
            target=lambda: api_server.run(host="127.0.0.1", port=8080, debug=False),
            daemon=True
        )
        api_thread.start()
        print("  [OK] API Server started on http://127.0.0.1:8080")
    except Exception as e:
        print(f"  [WARN] API Server failed to start: {e}")
        api_server = None
    
    # System status
    print("\n[3/3] System Status...")
    status = core.get_system_status()
    print(f"  [OK] System operational")
    print(f"  - Uptime: {status.get('uptime', 'N/A')}")
    print(f"  - Memory: {status.get('memory', {}).get('total_memories', 'N/A')} memories")
    print(f"  - Tasks: {status.get('tasks', {}).get('active', 'N/A')} active")
    
    print("\n" + "="*70)
    print("ELYSIA SYSTEM IS RUNNING")
    print("="*70)
    print("\nSystem Components:")
    print("  - Guardian Core: Active")
    if api_server:
        print("  - API Server: http://127.0.0.1:8080")
    print("\nAvailable Endpoints (if API server running):")
    print("  - GET  /api/status - System status")
    print("  - GET  /api/memory - Memory operations")
    print("  - GET  /api/health - Health check")
    print("  - GET  /api/startup/verification - Startup verification")
    print("\nPress Ctrl+C to shutdown gracefully...")
    print("="*70 + "\n")
    
    # Handle shutdown gracefully
    def signal_handler(sig, frame):
        print("\n\nShutdown signal received. Shutting down gracefully...")
        core.shutdown()
        print("System shutdown complete. Goodbye!")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Keep running
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    import threading
    main()

