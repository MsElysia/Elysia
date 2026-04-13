#!/usr/bin/env python3
"""
Verification script for dashboard server listening.

Tests:
1. Server starts successfully
2. Port is actually listening (TCP connect)
3. HTTP GET request succeeds
4. Actual port matches expected (or fallback works)
"""

import sys
import os
import socket
import time
import subprocess
import platform
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
        print(f"  TCP connect error: {e}")
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
    except requests.exceptions.ConnectionError as e:
        print(f"  [FAIL] HTTP GET failed: Connection refused")
        return False
    except requests.exceptions.Timeout:
        print(f"  [FAIL] HTTP GET failed: Timeout")
        return False
    except Exception as e:
        print(f"  [FAIL] HTTP GET failed: {e}")
        return False

def check_port_owner(port: int) -> tuple:
    """Check which process owns the port (Windows or Unix)."""
    pid = None
    cmd = None
    
    if platform.system() == "Windows":
        # Windows: netstat -ano | findstr :<port>
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        cmd = f"netstat -ano | findstr :{port}"
                        break
        except Exception as e:
            print(f"  ⚠ Could not check port owner: {e}")
    else:
        # Unix: lsof -i :<port>
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                # Parse first line
                lines = result.stdout.strip().splitlines()
                if len(lines) > 1:  # Skip header
                    parts = lines[1].split()
                    if len(parts) >= 2:
                        pid = parts[1]
                        cmd = f"lsof -i :{port}"
        except Exception as e:
            print(f"  ⚠ Could not check port owner: {e}")
    
    return pid, cmd

def main():
    print("=" * 70)
    print("DASHBOARD LISTENING VERIFICATION")
    print("=" * 70)
    print()
    
    # Import after path setup
    try:
        from project_guardian.guardian_singleton import get_guardian_core
    except ImportError as e:
        print(f"ERROR: Could not import guardian_singleton: {e}")
        return 1
    
    # Initialize GuardianCore
    print("[1/5] Initializing GuardianCore...")
    try:
        config = {
            "ui_config": {
                "enabled": True,
                "auto_start": True,
                "host": "127.0.0.1",
                "port": 5000
            }
        }
        guardian = get_guardian_core(config=config)
        print("  [OK] GuardianCore initialized")
    except Exception as e:
        print(f"  ✗ Failed to initialize GuardianCore: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Check UI panel
    print("\n[2/5] Checking UI panel...")
    if not guardian or not guardian.ui_panel:
        print("  [FAIL] UI panel not available")
        return 1
    
    ui_panel = guardian.ui_panel
    print(f"  [OK] UI panel found: {type(ui_panel).__name__}")
    
    # Check for required attributes
    required_attrs = ['_server_ready', '_server_error', '_actual_port', '_check_port_available', 
                      '_find_available_port', '_wait_for_server_ready']
    missing = [attr for attr in required_attrs if not hasattr(ui_panel, attr)]
    if missing:
        print(f"  [FAIL] Missing required attributes: {missing}")
        return 1
    print(f"  [OK] All required attributes present")
    
    # Start server
    print("\n[3/5] Starting dashboard server...")
    try:
        ui_panel.start(debug=False, source="verify_dashboard_listening")
        print("  [OK] start() called successfully")
    except Exception as e:
        print(f"  [FAIL] start() failed: {e}")
        if hasattr(ui_panel, '_server_error') and ui_panel._server_error:
            print(f"  Server error: {ui_panel._server_error}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Get actual port
    actual_port = ui_panel._actual_port or ui_panel.port
    actual_host = ui_panel.host
    print(f"  Expected port: {ui_panel.port}")
    print(f"  Actual port: {actual_port}")
    print(f"  Host: {actual_host}")
    
    # Wait for server ready
    print("\n[4/5] Waiting for server to be ready...")
    if ui_panel._wait_for_server_ready(timeout=10.0):
        print("  [OK] Server reported ready")
    else:
        print("  [FAIL] Server did not become ready within timeout")
        if ui_panel._server_error:
            print(f"  Server error: {ui_panel._server_error}")
        return 1
    
    # Check for server errors
    if ui_panel._server_error:
        print(f"  ⚠ Server error set: {ui_panel._server_error}")
    
    # Test TCP connection
    print("\n[5/5] Testing TCP connection...")
    if wait_for_port(actual_host, actual_port, timeout=10.0, interval=0.25):
        print("  [OK] TCP connection successful")
    else:
        print(f"  [FAIL] TCP connection failed - port {actual_port} not listening")
        
        # Check port owner
        print(f"\n  Checking port owner...")
        pid, cmd = check_port_owner(actual_port)
        if pid:
            print(f"  Port {actual_port} is owned by PID: {pid}")
            print(f"  Check with: {cmd}")
            current_pid = os.getpid()
            if pid == str(current_pid):
                print(f"  [OK] PID matches our process ({current_pid})")
            else:
                print(f"  [WARN] PID mismatch: our PID is {current_pid}, port owner is {pid}")
        else:
            print(f"  Port {actual_port} appears to be free (no process found)")
        
        return 1
    
    # Test HTTP GET
    print("\n[6/6] Testing HTTP GET request...")
    urls = [
        f"http://{actual_host}:{actual_port}",
        f"http://127.0.0.1:{actual_port}",
        f"http://localhost:{actual_port}",
    ]
    
    success = False
    for url in urls:
        print(f"  Testing {url}...")
        if test_http_get(url, timeout=5.0):
            print(f"  [OK] HTTP GET successful: {url}")
            success = True
            break
        else:
            print(f"  ✗ HTTP GET failed: {url}")
    
    if not success:
        print("\n  [WARN] All HTTP GET attempts failed")
        print("  TCP connection works, but HTTP requests fail")
        print("  Possible causes:")
        print("    - Server bound to wrong interface (0.0.0.0 vs 127.0.0.1)")
        print("    - IPv6 vs IPv4 mismatch (::1 vs 127.0.0.1)")
        print("    - Server not fully initialized")
        return 1
    
    # Success
    print("\n" + "=" * 70)
    print("VERIFICATION SUCCESSFUL")
    print("=" * 70)
    print(f"\n[OK] Server is listening on {actual_host}:{actual_port}")
    print(f"[OK] TCP connection successful")
    print(f"[OK] HTTP GET successful")
    print(f"\nDashboard URL: http://{actual_host}:{actual_port}")
    print(f"Alternative URLs:")
    for url in urls:
        print(f"  - {url}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
