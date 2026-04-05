#!/usr/bin/env python3
"""
Check Current System Status
Shows runtime loop status and component availability
"""

import sys
from pathlib import Path
from datetime import datetime

# Add paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

print("="*70)
print("SYSTEM STATUS CHECK")
print("="*70)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Check if system is running by checking log file
log_file = project_root / "elysia_unified.log"
if log_file.exists():
    print("[INFO] Log file exists: elysia_unified.log")
    try:
        # Read last few lines of log
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            if lines:
                print(f"[INFO] Log has {len(lines)} lines")
                print("\nLast 5 log entries:")
                print("-" * 70)
                for line in lines[-5:]:
                    print(line.rstrip())
    except Exception as e:
        print(f"[WARN] Could not read log: {e}")
else:
    print("[INFO] Log file not found (system may not be running)")

print("\n" + "="*70)
print("COMPONENT AVAILABILITY CHECK")
print("="*70)

# Check components
components = {
    "RuntimeLoop (project_guardian)": False,
    "ElysiaLoopCore": False,
    "GuardianCore": False,
    "ArchitectCore": False,
}

# Test RuntimeLoop
print("\n[1] Checking RuntimeLoop (project_guardian)...")
try:
    from project_guardian.runtime_loop_core import RuntimeLoop
    loop = RuntimeLoop()
    components["RuntimeLoop (project_guardian)"] = True
    print("[PASS] RuntimeLoop available and can be instantiated")
except Exception as e:
    print(f"[FAIL] RuntimeLoop error: {e}")

# Test ElysiaLoopCore
print("\n[2] Checking ElysiaLoopCore...")
try:
    from project_guardian.elysia_loop_core import ElysiaLoopCore
    components["ElysiaLoopCore"] = True
    print("[PASS] ElysiaLoopCore available")
except Exception as e:
    print(f"[FAIL] ElysiaLoopCore error: {e}")

# Test GuardianCore
print("\n[3] Checking GuardianCore...")
try:
    from project_guardian.core import GuardianCore
    components["GuardianCore"] = True
    print("[PASS] GuardianCore available")
except Exception as e:
    print(f"[FAIL] GuardianCore error: {e}")

# Test ArchitectCore
print("\n[4] Checking ArchitectCore...")
try:
    sys.path.insert(0, str(project_root / "core_modules" / "elysia_core_comprehensive"))
    from architect_core import ArchitectCore
    components["ArchitectCore"] = True
    print("[PASS] ArchitectCore available")
except Exception as e:
    print(f"[FAIL] ArchitectCore error: {e}")

# Summary
print("\n" + "="*70)
print("STATUS SUMMARY")
print("="*70)

for component, available in components.items():
    status = "[AVAILABLE]" if available else "[NOT AVAILABLE]"
    print(f"{status} {component}")

all_available = all(components.values())
print("\n" + "="*70)
if all_available:
    print("[SUCCESS] All critical components are available")
    print("System should be able to start with runtime_loop: True")
else:
    print("[WARNING] Some components are not available")
    print("Check errors above for details")

print("="*70)

# Check unified log if it exists
unified_log = project_root / "organized_project" / "data" / "logs" / "unified_autonomous_system.log"
if unified_log.exists():
    print("\n" + "="*70)
    print("RECENT STATUS FROM UNIFIED LOG")
    print("="*70)
    try:
        with open(unified_log, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            # Look for status updates
            status_lines = [line for line in lines if "Components Active" in line]
            if status_lines:
                print("\nLast status update:")
                print(status_lines[-1].rstrip())
            else:
                print("No status updates found in log")
    except Exception as e:
        print(f"Could not read unified log: {e}")

print("\n" + "="*70)

