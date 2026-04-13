#!/usr/bin/env python3
"""
Verification script for dashboard startup from Elysia interface.

Simulates the same call path as option [7] in elysia_interface.py
and verifies the server starts and returns HTTP 200.
"""

import sys
import os
import time
import socket
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("WARNING: requests not available, will only test TCP connection")

def check_port_listening(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if a port is listening by attempting TCP connect."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((host, port))
            return result == 0  # 0 means connection succeeded
    except Exception as e:
        return False

def wait_for_port(host: str, port: int, timeout: float = 10.0, interval: float = 0.25) -> bool:
    """Wait for port to become listening, checking every interval seconds."""
    start_time = time.time()
    attempt = 0
    while time.time() - start_time < timeout:
        attempt += 1
        if check_port_listening(host, port, timeout=0.5):
            elapsed = time.time() - start_time
            print(f"  [OK] Port {port} is listening (after {elapsed:.2f}s, {attempt} attempts)")
            return True
        time.sleep(interval)
        if attempt % 4 == 0:  # Print every second
            elapsed = time.time() - start_time
            print(f"  ... waiting for port {port} ({elapsed:.1f}s elapsed)")
    return False

def test_http_get(url: str, timeout: float = 5.0) -> bool:
    """Test HTTP GET request to URL."""
    if not HAS_REQUESTS:
        print(f"  [SKIP] Skipping HTTP test (requests not available)")
        return False
    
    try:
        response = requests.get(url, timeout=timeout)
        print(f"  [OK] HTTP GET {url} -> {response.status_code}")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        print(f"  [FAIL] HTTP GET failed: Connection refused")
        return False
    except requests.exceptions.Timeout:
        print(f"  [FAIL] HTTP GET failed: Timeout")
        return False
    except Exception as e:
        print(f"  [FAIL] HTTP GET failed: {e}")
        return False

def main():
    print("=" * 70)
    print("DASHBOARD FROM INTERFACE VERIFICATION")
    print("=" * 70)
    print()
    
    # Simulate the same code path as elysia_interface.py open_web_dashboard()
    print("[1/4] Getting GuardianCore instance (same as interface option [7])...")
    
    guardian = None
    guardian_source = None
    
    # Try autonomous_system.guardian first (if UnifiedElysiaSystem was used)
    try:
        from run_elysia_unified import UnifiedElysiaSystem
        print("  [DEBUG] UnifiedElysiaSystem available")
        
        # Create UnifiedElysiaSystem (this creates GuardianCore singleton)
        config = {
            "ui_config": {
                "enabled": True,
                "auto_start": False,  # We'll start manually
                "host": "127.0.0.1",
                "port": 5000
            }
        }
        autonomous_system = UnifiedElysiaSystem(config=config)
        
        if hasattr(autonomous_system, 'guardian') and autonomous_system.guardian:
            guardian = autonomous_system.guardian
            guardian_source = "autonomous_system.guardian"
            import inspect
            module_path = inspect.getfile(type(guardian))
            print(f"  [OK] Got GuardianCore from autonomous_system.guardian")
            print(f"  [DEBUG] GuardianCore module path: {module_path}")
    except Exception as e:
        print(f"  [WARN] Could not get from autonomous_system: {e}")
        import traceback
        traceback.print_exc()
    
    # Fall back to singleton
    if not guardian:
        try:
            from project_guardian.guardian_singleton import get_guardian_core
            import inspect
            singleton_module = inspect.getfile(get_guardian_core)
            print(f"  [DEBUG] Attempting singleton")
            print(f"  [DEBUG] Singleton module path: {singleton_module}")
            
            config = {
                "ui_config": {
                    "enabled": True,
                    "auto_start": False,  # We'll start manually
                    "host": "127.0.0.1",
                    "port": 5000
                }
            }
            guardian = get_guardian_core(config=config)
            guardian_source = "singleton"
            
            if guardian:
                import inspect
                module_path = inspect.getfile(type(guardian))
                print(f"  [OK] Got GuardianCore from singleton")
                print(f"  [DEBUG] GuardianCore module path: {module_path}")
        except Exception as e:
            print(f"  [FAIL] Failed to get GuardianCore from singleton: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    if not guardian:
        print("  [FAIL] Could not get GuardianCore from any source")
        return 1
    
    print(f"\n[2/4] Checking UI panel...")
    print(f"  [DEBUG] GuardianCore source: {guardian_source}")
    print(f"  [DEBUG] GuardianCore instance exists: {guardian is not None}")
    print(f"  [DEBUG] UI panel attribute exists: {hasattr(guardian, 'ui_panel')}")
    
    if not hasattr(guardian, 'ui_panel') or guardian.ui_panel is None:
        print("  [WARN] UI panel not initialized, creating...")
        try:
            from project_guardian.ui_control_panel import UIControlPanel
            guardian.ui_panel = UIControlPanel(
                orchestrator=guardian,
                host="127.0.0.1",
                port=5000
            )
            print("  [OK] UI panel created")
        except Exception as e:
            print(f"  [FAIL] Failed to create UI panel: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    print(f"  [OK] UI panel exists: {guardian.ui_panel is not None}")
    
    print(f"\n[3/4] Starting dashboard server...")
    try:
        guardian.ui_panel.start(debug=False, source="verify_dashboard_from_interface")
        print("  [OK] start() called successfully")
    except Exception as e:
        print(f"  [FAIL] start() failed: {e}")
        if hasattr(guardian.ui_panel, '_server_error') and guardian.ui_panel._server_error:
            print(f"  Server error: {guardian.ui_panel._server_error}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Get actual port
    actual_port = guardian.ui_panel._actual_port or guardian.ui_panel.port
    actual_host = guardian.ui_panel.host
    print(f"  Expected port: {guardian.ui_panel.port}")
    print(f"  Actual port: {actual_port}")
    print(f"  Host: {actual_host}")
    
    # Wait for server ready
    print(f"\n[4/4] Waiting for server to be ready...")
    if hasattr(guardian.ui_panel, '_wait_for_server_ready'):
        if guardian.ui_panel._wait_for_server_ready(timeout=10.0):
            print("  [OK] Server reported ready")
        else:
            print("  [FAIL] Server did not become ready within timeout")
            if guardian.ui_panel._server_error:
                print(f"  Server error: {guardian.ui_panel._server_error}")
            return 1
    else:
        print("  [WARN] _wait_for_server_ready not available, waiting 2 seconds...")
        time.sleep(2)
    
    # Test TCP connection
    print(f"\n[5/5] Testing TCP connection...")
    if wait_for_port(actual_host, actual_port, timeout=10.0, interval=0.25):
        print("  [OK] TCP connection successful")
    else:
        print(f"  [FAIL] TCP connection failed - port {actual_port} not listening")
        return 1
    
    # Test HTTP GET
    print(f"\n[6/6] Testing HTTP GET request...")
    url = f"http://{actual_host}:{actual_port}"
    if test_http_get(url, timeout=5.0):
        print("  [OK] HTTP GET successful")
    else:
        print("  [FAIL] HTTP GET failed")
        return 1
    
    # Success
    print("\n" + "=" * 70)
    print("VERIFICATION SUCCESSFUL")
    print("=" * 70)
    print(f"\n[OK] Dashboard server is listening on {actual_host}:{actual_port}")
    print(f"[OK] TCP connection successful")
    print(f"[OK] HTTP GET successful")
    print(f"\nDashboard URL: {url}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
