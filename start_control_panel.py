#!/usr/bin/env python3
"""
Start Elysia Control Panel and keep it running.
This script starts the control panel and keeps the process alive.
"""

import sys
import time
import signal
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Start control panel and keep running."""
    print("=" * 70)
    print("ELYSIA CONTROL PANEL - Starting...")
    print("=" * 70)
    
    # Load API keys FIRST before initializing GuardianCore
    print("\n[0/3] Loading API keys...")
    try:
        from load_api_keys import load_api_keys
        keys_loaded = load_api_keys()
        if keys_loaded:
            loaded_count = len([k for k in keys_loaded.values() if k == "Loaded"])
            print(f"✅ Loaded {loaded_count} API key(s)")
        else:
            print("⚠️  No API keys loaded - some features may be limited")
    except Exception as e:
        print(f"⚠️  Could not load API keys: {e}")
    
    try:
        from project_guardian.core import GuardianCore
        
        # Configuration with UI enabled
        config = {
            "ui_config": {
                "enabled": True,
                "auto_start": True,
                "host": "127.0.0.1",
                "port": 5000,
                "debug": False
            },
            "enable_resource_monitoring": False,  # Disable for cleaner output
            "enable_runtime_health_monitoring": True
        }
        
        print("\n[1/3] Initializing GuardianCore...")
        guardian = GuardianCore(config=config)
        print("✅ GuardianCore initialized")
        
        # Check if UI panel started
        print("\n[2/3] Starting Control Panel...")
        if hasattr(guardian, 'ui_panel') and guardian.ui_panel:
            if guardian.ui_panel.running:
                print(f"✅ Control Panel is RUNNING")
                print(f"📍 Access at: http://127.0.0.1:5000")
            else:
                print("   Attempting to start...")
                guardian.ui_panel.start()
                print("✅ Control Panel started")
        else:
            print("\n❌ Control Panel not found")
            print("   Check ui_config in config")
            return
        
        # Keep running
        print("\n" + "=" * 70)
        print("CONTROL PANEL IS RUNNING")
        print("=" * 70)
        print("\n🌐 Open your browser to: http://127.0.0.1:5000")
        print("💡 Press Ctrl+C to stop the server\n")
        
        try:
            while True:
                time.sleep(1)
                # Check if still running
                if hasattr(guardian, 'ui_panel') and guardian.ui_panel:
                    if not guardian.ui_panel.running:
                        logger.warning("Control panel stopped unexpectedly")
                        break
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
            if hasattr(guardian, 'ui_panel') and guardian.ui_panel:
                guardian.ui_panel.stop()
            guardian.shutdown()
            print("✅ Shutdown complete")
            
    except ImportError as e:
        print(f"\n❌ Error: Missing dependencies")
        print(f"   {e}")
        print("\n💡 Install required packages:")
        print("   pip install flask flask-socketio flask-cors")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error starting control panel: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

