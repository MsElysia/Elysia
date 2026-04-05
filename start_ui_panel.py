#!/usr/bin/env python
# start_ui_panel.py
# Quick launcher for Elysia UI Control Panel

"""
Quick launcher for the Elysia UI Control Panel.
Starts GuardianCore with UI enabled on localhost:5000
"""

import sys
import time
import logging
from pathlib import Path

# Add project_guardian to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from project_guardian import GuardianCore

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Start GuardianCore with UI Control Panel."""
    print("=" * 60)
    print("  Elysia UI Control Panel - Starting...")
    print("=" * 60)
    print()
    
    # Configuration with UI enabled
    config = {
        "ui_config": {
            "enabled": True,
            "auto_start": True,
            "host": "127.0.0.1",
            "port": 5000,
            "debug": False
        }
    }
    
    try:
        # Initialize GuardianCore with UI
        print("Initializing GuardianCore...")
        guardian = GuardianCore(config)
        print("✅ GuardianCore initialized")
        
        # Show status
        print("\n📊 System Status:")
        status = guardian.get_system_status()
        print(f"  - Memory entries: {status.get('memory_entries', 0)}")
        print(f"  - Active tasks: {status.get('active_tasks', 0)}")
        print(f"  - Components: {status.get('components', 0)}")
        
        loop_status = guardian.get_loop_status()
        if loop_status:
            print(f"  - Event loop: {'Running' if loop_status.get('running') else 'Stopped'}")
            print(f"  - Queue size: {loop_status.get('queue_size', 0)}")
        
        print("\n" + "=" * 60)
        print("  🌐 UI Control Panel is starting...")
        print("  📍 Access at: http://127.0.0.1:5000")
        print("=" * 60)
        print("\n💡 Press Ctrl+C to stop the server\n")
        
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
            guardian.shutdown()
            print("✅ Shutdown complete")
            
    except ImportError as e:
        print(f"\n❌ Error: Missing dependencies")
        print(f"   {e}")
        print("\n💡 Install required packages:")
        print("   pip install flask flask-socketio")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n[ERROR] Error starting UI Panel: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()






















