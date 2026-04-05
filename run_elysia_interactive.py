# run_elysia_interactive.py
# Interactive Elysia system runner

import sys
import logging
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from project_guardian.core import GuardianCore

# Reduce logging noise
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s: %(message)s'
)

def main():
    """Run Elysia system interactively."""
    print("\n" + "="*70)
    print("ELYSIA SYSTEM - Starting...")
    print("="*70)
    
    # Configuration
    config = {
        "enable_resource_monitoring": False,  # Disable for cleaner output
        "enable_runtime_health_monitoring": False,
    }
    
    # Initialize core system
    print("\n[1/2] Initializing Guardian Core...")
    try:
        core = GuardianCore(config=config)
        print("  [OK] Core system initialized")
    except Exception as e:
        print(f"  [ERROR] Failed to initialize: {e}")
        return
    
    # System status
    print("\n[2/2] System Status...")
    try:
        status = core.get_system_status()
        print("  [OK] System operational")
        print(f"\n  System Information:")
        print(f"    - Uptime: {status.get('uptime', 'N/A')}")
        
        memory_info = status.get('memory', {})
        print(f"    - Total Memories: {memory_info.get('total_memories', 'N/A')}")
        print(f"    - Memory Categories: {len(memory_info.get('categories', {}))}")
        
        tasks_info = status.get('tasks', {})
        print(f"    - Active Tasks: {tasks_info.get('active', 0)}")
        print(f"    - Completed Tasks: {tasks_info.get('completed', 0)}")
        
        trust_info = status.get('trust', {})
        print(f"    - Trust Nodes: {trust_info.get('total_nodes', 0)}")
        
        consensus_info = status.get('consensus', {})
        print(f"    - Consensus Agents: {consensus_info.get('agents', 0)}")
        
    except Exception as e:
        print(f"  [WARN] Could not get status: {e}")
    
    # Startup verification
    try:
        verification = core.get_startup_verification()
        if verification:
            checks = verification.get("checks", [])
            successes = sum(1 for c in checks if c.get("status") == "success")
            print(f"\n  Startup Verification: {successes}/{len(checks)} checks passed")
    except:
        pass
    
    print("\n" + "="*70)
    print("ELYSIA SYSTEM IS RUNNING")
    print("="*70)
    print("\nSystem is active and monitoring.")
    print("You can interact with it programmatically or via API.")
    print("\nExample: Test memory operations")
    print("  core.memory.remember('Hello from Elysia!', category='test')")
    print("  memories = core.memory.recall_last(count=5)")
    print("\nPress Ctrl+C to shutdown gracefully...")
    print("="*70 + "\n")
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutdown signal received. Shutting down gracefully...")
        core.shutdown()
        print("System shutdown complete. Goodbye!\n")
        sys.exit(0)

if __name__ == "__main__":
    main()

