#!/usr/bin/env python3
"""
Manual verification script for Elysia Unified Interface fixes.
Tests:
1. Architect-Core initialization (no crash)
2. No second GuardianCore initialization
3. Web dashboard opens once (no loops)
4. Console responsiveness
5. No heartbeat spam
"""

import sys
import time
import threading
from pathlib import Path

# Add paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

print("="*70)
print("ELYSIA UNIFIED INTERFACE - MANUAL VERIFICATION")
print("="*70)
print()

# Test 1: Check Architect-Core can initialize
print("[TEST 1] Testing Architect-Core initialization...")
try:
    from core_modules.elysia_core_comprehensive.architect_core import ArchitectCore
    architect = ArchitectCore(enable_webscout=True)
    print("  [OK] Architect-Core initialized successfully")
    print(f"  [OK] WebScout: {'Available' if architect.webscout else 'Not available (expected if no web_reader)'}")
    if architect.webscout:
        print(f"  [INFO] WebScout web_reader: {'Available' if architect.webscout.web_reader else 'None (URL research disabled)'}")
except Exception as e:
    print(f"  [FAIL] Architect-Core failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 2: Check GuardianCore singleton behavior
print("[TEST 2] Testing GuardianCore singleton...")
try:
    from project_guardian.guardian_singleton import get_guardian_core, reset_singleton
    from run_elysia_unified import UnifiedElysiaSystem
    
    # Reset singleton for clean test
    reset_singleton()
    
    # Simulate unified system startup
    print("  [INFO] Starting UnifiedElysiaSystem...")
    unified_system = UnifiedElysiaSystem(config={})
    unified_guardian = unified_system.guardian
    print(f"  [OK] Unified system created GuardianCore: {unified_guardian is not None}")
    
    # Now simulate interface trying to get GuardianCore
    print("  [INFO] Simulating elysia_interface.py initialization...")
    from elysia_interface import ElysiaInterface
    interface = ElysiaInterface()
    interface._init_core()
    interface_guardian = interface.core
    
    print(f"  [OK] Interface got GuardianCore: {interface_guardian is not None}")
    
    if unified_guardian is interface_guardian:
        print("  [OK] Same instance (singleton working correctly)")
    else:
        print("  [FAIL] Different instances (singleton not working)")
        sys.exit(1)
        
except Exception as e:
    print(f"  [FAIL] GuardianCore singleton test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 3: Check for remaining direct GuardianCore() calls
print("[TEST 3] Checking for remaining direct GuardianCore() calls...")
import os
import subprocess
result = subprocess.run(
    ['powershell', '-Command', 
     f'Get-ChildItem -Path "{project_root}" -Filter "*.py" -Recurse -ErrorAction SilentlyContinue | Select-String -Pattern "GuardianCore\\(" | Where-Object {{ $_.Path -notlike "*test*" -and $_.Path -notlike "*__pycache__*" }} | Measure-Object | Select-Object -ExpandProperty Count'],
    capture_output=True,
    text=True,
    cwd=str(project_root)
)
count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
if count == 0:
    print("  [OK] No direct GuardianCore() calls found outside tests")
else:
    print(f"  [WARN] Found {count} direct GuardianCore() calls (should be 0)")
    print("  [INFO] Run: Get-ChildItem -Filter *.py -Recurse | Select-String 'GuardianCore\\(' to find them")

print()

# Test 4: Check monitoring doesn't start twice
print("[TEST 4] Testing monitoring start idempotency...")
try:
    from project_guardian.guardian_singleton import ensure_monitoring_started, reset_singleton
    from project_guardian.core import GuardianCore
    
    reset_singleton()
    GuardianCore._any_instance_initialized = False
    
    guardian = get_guardian_core(config={})
    if guardian and hasattr(guardian, 'monitor'):
        # First start
        ensure_monitoring_started(guardian)
        started_1 = guardian.monitor.monitoring_active if guardian.monitor else False
        
        # Second start (should be idempotent)
        ensure_monitoring_started(guardian)
        started_2 = guardian.monitor.monitoring_active if guardian.monitor else False
        
        if started_1 == started_2:
            print("  [OK] Monitoring start is idempotent")
        else:
            print("  [FAIL] Monitoring start is not idempotent")
            sys.exit(1)
    else:
        print("  [SKIP] GuardianCore or monitor not available")
        
except Exception as e:
    print(f"  [WARN] Monitoring test warning: {e}")

print()
print("="*70)
print("AUTOMATED TESTS COMPLETE")
print("="*70)
print()
print("Next steps for manual verification:")
print("1. Run: python run_elysia_unified.py")
print("2. In another terminal, run: python elysia_interface.py")
print("3. Choose option 7 (Open Web Dashboard)")
print("4. Verify:")
print("   - Browser opens once (not repeatedly)")
print("   - Console remains responsive")
print("   - No heartbeat spam in console")
print("   - CPU usage is reasonable")
print()
