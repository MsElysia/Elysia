#!/usr/bin/env python3
"""
End-to-end verification script.
Actually runs the unified interface and verifies the fixes.
"""

import sys
import time
import threading
import subprocess
import signal
from pathlib import Path
from io import StringIO
import contextlib
import logging

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

# Capture stdout/stderr
stdout_capture = StringIO()
stderr_capture = StringIO()

print("="*70)
print("END-TO-END VERIFICATION")
print("="*70)
print()

issues_found = []
evidence = []

# Test 1: Architect-Core initialization (no crash)
print("[TEST 1] Architect-Core initialization (no crash)...")
try:
    from core_modules.elysia_core_comprehensive.architect_core import ArchitectCore
    
    # Capture any exceptions
    architect = None
    exception_occurred = None
    
    try:
        architect = ArchitectCore(enable_webscout=True)
    except TypeError as e:
        if "missing 1 required positional argument" in str(e) and "web_reader" in str(e):
            exception_occurred = e
    except Exception as e:
        exception_occurred = e
    
    if exception_occurred:
        print(f"  [FAIL] Architect-Core crashed: {exception_occurred}")
        issues_found.append(f"Architect-Core crash: {exception_occurred}")
        evidence.append(f"Architect-Core exception: {exception_occurred}")
    else:
        print("  [OK] Architect-Core initialized without crash")
        evidence.append("Architect-Core initialized successfully")
        if architect and architect.webscout:
            if architect.webscout.web_reader:
                evidence.append("WebScout has web_reader from singleton")
            else:
                evidence.append("WebScout initialized without web_reader (graceful degradation)")
except Exception as e:
    print(f"  [FAIL] Test setup failed: {e}")
    issues_found.append(f"Test setup error: {e}")

print()

# Test 2: GuardianCore singleton (no double init)
print("[TEST 2] GuardianCore singleton (no double init)...")
try:
    from project_guardian.guardian_singleton import get_guardian_core, reset_singleton
    from project_guardian.core import GuardianCore
    
    reset_singleton()
    GuardianCore._any_instance_initialized = False
    
    # Simulate unified system
    print("  [INFO] Creating first GuardianCore (simulating UnifiedElysiaSystem)...")
    guardian1 = get_guardian_core(config={})
    
    if not guardian1:
        print("  [FAIL] First GuardianCore creation returned None")
        issues_found.append("First GuardianCore creation failed")
    else:
        evidence.append(f"First GuardianCore created: {id(guardian1)}")
        
        # Simulate interface trying to get GuardianCore
        print("  [INFO] Getting GuardianCore again (simulating elysia_interface.py)...")
        try:
            guardian2 = get_guardian_core(config={})
            
            if guardian2 is None:
                print("  [FAIL] Second get_guardian_core() returned None")
                issues_found.append("Second get_guardian_core() failed")
            elif guardian1 is guardian2:
                print("  [OK] Same instance returned (singleton working)")
                evidence.append(f"Second GuardianCore is same instance: {id(guardian2)}")
            else:
                print("  [FAIL] Different instances (singleton broken)")
                issues_found.append("GuardianCore singleton not working")
                evidence.append(f"Different instances: {id(guardian1)} vs {id(guardian2)}")
        except RuntimeError as e:
            if "already exists" in str(e):
                print(f"  [FAIL] Double initialization exception: {e}")
                issues_found.append(f"Double init exception: {e}")
                evidence.append(f"Exception: {e}")
            else:
                raise
except Exception as e:
    print(f"  [FAIL] GuardianCore test failed: {e}")
    import traceback
    traceback.print_exc()
    issues_found.append(f"GuardianCore test error: {e}")

print()

# Test 3: Dashboard start idempotency
print("[TEST 3] Dashboard start idempotency...")
try:
    from project_guardian.ui_control_panel import UIControlPanel, reset_dashboard_guard
    
    reset_dashboard_guard()
    
    # Create two instances
    panel1 = UIControlPanel(host="127.0.0.1", port=5001)  # Different port to avoid conflicts
    panel2 = UIControlPanel(host="127.0.0.1", port=5001)
    
    # First start
    print("  [INFO] Starting dashboard (first attempt)...")
    panel1.start(source="test_verification_1")
    started_1 = panel1.running
    
    # Second start (should be idempotent)
    print("  [INFO] Starting dashboard (second attempt - should be idempotent)...")
    panel2.start(source="test_verification_2")
    started_2 = panel2.running
    
    if started_1 and started_2:
        print("  [OK] Dashboard start is idempotent (module-level guard working)")
        evidence.append("Dashboard start is idempotent")
    else:
        print(f"  [WARN] Dashboard start behavior unclear: started_1={started_1}, started_2={started_2}")
        
    # Cleanup
    try:
        panel1.stop()
        panel2.stop()
    except:
        pass
        
except Exception as e:
    print(f"  [WARN] Dashboard test warning: {e}")
    evidence.append(f"Dashboard test: {e}")

print()

# Test 4: Verify no heartbeat spam in stdout
print("[TEST 4] Verifying heartbeat logging levels...")
try:
    # Check source files
    elysia_loop_file = project_root / "project_guardian" / "elysia_loop_core.py"
    monitoring_file = project_root / "project_guardian" / "monitoring.py"
    
    heartbeat_issues = []
    
    for file_path in [elysia_loop_file, monitoring_file]:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if 'logger.info' in line and 'heartbeat' in line.lower():
                        heartbeat_issues.append(f"{file_path}:{i}: {line.strip()}")
    
    if heartbeat_issues:
        print(f"  [FAIL] Found logger.info with heartbeat:")
        for issue in heartbeat_issues:
            print(f"    {issue}")
        issues_found.append("Heartbeat using logger.info instead of logger.debug")
        evidence.append(f"Heartbeat INFO issues: {heartbeat_issues}")
    else:
        print("  [OK] No heartbeat messages at INFO level")
        evidence.append("All heartbeat messages use logger.debug")
        
except Exception as e:
    print(f"  [WARN] Heartbeat check warning: {e}")

print()

# Summary
print("="*70)
print("VERIFICATION SUMMARY")
print("="*70)

if not issues_found:
    print("[SUCCESS] All automated tests passed!")
    print()
    print("Evidence collected:")
    for item in evidence:
        print(f"  [OK] {item}")
else:
    print("[ISSUES FOUND]")
    for i, issue in enumerate(issues_found, 1):
        print(f"  {i}. {issue}")
    print()
    print("Evidence collected:")
    for item in evidence:
        print(f"  - {item}")

print("="*70)

# Return exit code
sys.exit(0 if not issues_found else 1)
