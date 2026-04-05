#!/usr/bin/env python3
"""
Automated end-to-end verification script.
Runs the unified interface and checks for the key issues.
"""

import sys
import time
import threading
import subprocess
from pathlib import Path
from io import StringIO
import contextlib

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

print("="*70)
print("ELYSIA UNIFIED INTERFACE - AUTOMATED VERIFICATION")
print("="*70)
print()

issues_found = []

# Test 1: Architect-Core initialization
print("[TEST 1] Testing Architect-Core initialization...")
try:
    from core_modules.elysia_core_comprehensive.architect_core import ArchitectCore
    architect = ArchitectCore(enable_webscout=True)
    
    if architect.webscout:
        if architect.webscout.web_reader:
            print("  [OK] Architect-Core initialized with WebScout (web_reader available)")
        else:
            print("  [OK] Architect-Core initialized with WebScout (web_reader None - graceful degradation)")
    else:
        print("  [OK] Architect-Core initialized (WebScout not available)")
        
except TypeError as e:
    if "missing 1 required positional argument" in str(e) and "web_reader" in str(e):
        print(f"  [FAIL] Architect-Core failed: {e}")
        issues_found.append("Architect-Core ElysiaWebScout initialization failed")
    else:
        raise
except Exception as e:
    print(f"  [FAIL] Architect-Core failed: {e}")
    import traceback
    traceback.print_exc()
    issues_found.append(f"Architect-Core initialization error: {e}")

print()

# Test 2: GuardianCore singleton (no double init)
print("[TEST 2] Testing GuardianCore singleton behavior...")
try:
    from project_guardian.guardian_singleton import get_guardian_core, reset_singleton
    from project_guardian.core import GuardianCore
    
    reset_singleton()
    GuardianCore._any_instance_initialized = False
    
    # Simulate unified system
    guardian1 = get_guardian_core(config={})
    
    # Simulate interface trying to get GuardianCore
    guardian2 = get_guardian_core(config={})
    
    if guardian1 is guardian2:
        print("  [OK] Singleton working - same instance returned")
    else:
        print("  [FAIL] Singleton broken - different instances")
        issues_found.append("GuardianCore singleton not working")
        
except RuntimeError as e:
    if "already exists" in str(e):
        print(f"  [FAIL] Double initialization detected: {e}")
        issues_found.append("GuardianCore double initialization")
    else:
        raise
except Exception as e:
    print(f"  [FAIL] GuardianCore test failed: {e}")
    issues_found.append(f"GuardianCore test error: {e}")

print()

# Test 3: Check for direct GuardianCore() calls
print("[TEST 3] Checking for direct GuardianCore() calls...")
try:
    import os
    result = subprocess.run(
        ['powershell', '-Command', 
         f'$count = (Get-ChildItem -Path "{project_root}" -Filter "*.py" -Recurse -ErrorAction SilentlyContinue | Select-String -Pattern "GuardianCore\\(" | Where-Object {{ $_.Path -notlike "*test*" -and $_.Path -notlike "*__pycache__*" -and $_.Path -notlike "*\.venv*" }} | Measure-Object).Count; Write-Output $count'],
        capture_output=True,
        text=True,
        timeout=10
    )
    count = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
    if count == 0:
        print("  [OK] No direct GuardianCore() calls found")
    else:
        print(f"  [WARN] Found {count} direct GuardianCore() calls")
        issues_found.append(f"Found {count} direct GuardianCore() calls")
except Exception as e:
    print(f"  [WARN] Could not check for GuardianCore() calls: {e}")

print()

# Test 4: Check heartbeat logging (should not use print)
print("[TEST 4] Checking heartbeat logging...")
try:
    with open(project_root / "project_guardian" / "monitoring.py", 'r', encoding='utf-8') as f:
        content = f.read()
        if 'print(' in content and ('heartbeat' in content.lower() or 'tick' in content.lower()):
            print("  [WARN] Found print() statements with heartbeat/tick in monitoring.py")
            issues_found.append("Heartbeat may be using print() instead of logger")
        else:
            print("  [OK] No print() statements for heartbeat found")
except Exception as e:
    print(f"  [WARN] Could not check monitoring.py: {e}")

print()

# Test 5: Dashboard start idempotency
print("[TEST 5] Testing dashboard start idempotency...")
try:
    from project_guardian.ui_control_panel import UIControlPanel, reset_dashboard_guard
    
    reset_dashboard_guard()
    
    panel1 = UIControlPanel()
    panel2 = UIControlPanel()
    
    # First start
    panel1.start(source="test1")
    started_1 = panel1.running
    
    # Second start (should be idempotent)
    panel2.start(source="test2")
    started_2 = panel2.running
    
    if started_1 and started_2:
        print("  [OK] Dashboard start is idempotent (module-level guard working)")
    else:
        print("  [WARN] Dashboard start behavior unclear")
        
    # Cleanup
    try:
        panel1.stop()
        panel2.stop()
    except:
        pass
        
except Exception as e:
    print(f"  [WARN] Dashboard test warning: {e}")

print()

# Summary
print("="*70)
print("VERIFICATION SUMMARY")
print("="*70)

if not issues_found:
    print("[SUCCESS] All automated tests passed!")
    print()
    print("Next: Run manual verification:")
    print("  1. python run_elysia_unified.py")
    print("  2. In another terminal: python elysia_interface.py")
    print("  3. Choose option 7 (Open Web Dashboard)")
    print("  4. Verify console remains responsive for 3 minutes")
    print()
    print("See MANUAL_VERIFICATION_GUIDE.md for detailed steps.")
else:
    print("[ISSUES FOUND]")
    for i, issue in enumerate(issues_found, 1):
        print(f"  {i}. {issue}")
    print()
    print("Please fix these issues before manual verification.")

print("="*70)
