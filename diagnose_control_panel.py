#!/usr/bin/env python3
"""Diagnose Elysia Control Panel issues."""

import sys
import socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("ELYSIA CONTROL PANEL DIAGNOSTIC")
print("=" * 70)

# Check if port is in use
print("\n1. Checking port 5000...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('127.0.0.1', 5000))
sock.close()

if result == 0:
    print("   ✅ Port 5000 is OPEN and accepting connections")
else:
    print("   ❌ Port 5000 is NOT accessible")
    print("   → Control panel is not running or crashed")

# Check for control panel module
print("\n2. Checking for control panel module...")
try:
    from project_guardian import ui_control_panel
    print("   ✅ ui_control_panel module found")
    
    # Check if it has Flask app
    if hasattr(ui_control_panel, 'app'):
        print("   ✅ Flask app found")
    else:
        print("   ⚠️  No Flask app attribute found")
        
except ImportError as e:
    print(f"   ❌ Cannot import ui_control_panel: {e}")

# Check GuardianCore
print("\n3. Checking GuardianCore...")
try:
    from project_guardian.core import GuardianCore
    print("   ✅ GuardianCore found")
    
    # Try to initialize
    try:
        config = {"ui_config": {"enabled": True, "auto_start": True}}
        core = GuardianCore(config=config)
        print("   ✅ GuardianCore initialized successfully")
        
        # Check if UI started
        if hasattr(core, 'ui_panel'):
            print("   ✅ UI panel attribute exists")
        else:
            print("   ⚠️  No ui_panel attribute")
            
    except Exception as e:
        print(f"   ❌ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        
except ImportError as e:
    print(f"   ❌ Cannot import GuardianCore: {e}")

# Check Flask
print("\n4. Checking Flask installation...")
try:
    import flask
    print(f"   ✅ Flask installed (version: {flask.__version__})")
except ImportError:
    print("   ❌ Flask not installed")
    print("   → Install with: pip install flask flask-cors")

print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)

if result != 0:
    print("""
The control panel is not running. To start it:

1. Use the unified runtime (includes control panel):
   python run_elysia_unified.py

2. Or start UI panel directly:
   python start_ui_panel.py

3. Or use the Elysia runtime:
   python -m elysia run

Then access at: http://127.0.0.1:5000
""")
else:
    print("""
Control panel appears to be running. Try:
- Open browser to: http://127.0.0.1:5000
- Check browser console for JavaScript errors
- Check if page loads but is blank (template issue)
""")

print("=" * 70)

