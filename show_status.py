#!/usr/bin/env python3
"""
Show Current System Status
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

print("="*70)
print("PROJECT GUARDIAN / ELYSIA SYSTEM STATUS")
print("="*70)
print(f"Check Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Check if system appears to be running
unified_log = project_root / "organized_project" / "data" / "logs" / "unified_autonomous_system.log"
elysia_log = project_root / "elysia_unified.log"

print("LOG FILES:")
print("-" * 70)
if unified_log.exists():
    try:
        with open(unified_log, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            if lines:
                # Get last status
                status_lines = [l for l in lines if "Components Active" in l]
                if status_lines:
                    last_status = status_lines[-1]
                    print(f"Unified Log: {len(lines)} lines")
                    print(f"Last Status: {last_status.split('INFO - ')[-1].strip()}")
                    
                    # Extract timestamp
                    if "STATUS UPDATE" in lines[-10:]:
                        print("System appears to be RUNNING")
                    else:
                        print("System may be STOPPED (no recent status updates)")
                else:
                    print("Unified Log: No status entries found")
            else:
                print("Unified Log: Empty")
    except Exception as e:
        print(f"Unified Log: Error reading - {e}")
else:
    print("Unified Log: Not found")

if elysia_log.exists():
    try:
        with open(elysia_log, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            print(f"Elysia Log: {len(lines)} lines")
            if lines:
                print(f"Last entry: {lines[-1][:80]}...")
    except:
        print("Elysia Log: Error reading")
else:
    print("Elysia Log: Not found")

print("\n" + "="*70)
print("COMPONENT STATUS")
print("="*70)

# Check components
components_status = {}

# RuntimeLoop
try:
    from project_guardian.runtime_loop_core import RuntimeLoop
    loop = RuntimeLoop()
    components_status["RuntimeLoop"] = "AVAILABLE"
except Exception as e:
    components_status["RuntimeLoop"] = f"ERROR: {str(e)[:50]}"

# ElysiaLoopCore
try:
    from project_guardian.elysia_loop_core import ElysiaLoopCore
    components_status["ElysiaLoopCore"] = "AVAILABLE"
except Exception as e:
    components_status["ElysiaLoopCore"] = f"ERROR: {str(e)[:50]}"

# GuardianCore
try:
    from project_guardian.core import GuardianCore
    components_status["GuardianCore"] = "AVAILABLE"
except Exception as e:
    components_status["GuardianCore"] = f"ERROR: {str(e)[:50]}"

# ArchitectCore
try:
    sys.path.insert(0, str(project_root / "core_modules" / "elysia_core_comprehensive"))
    from architect_core import ArchitectCore
    components_status["ArchitectCore"] = "AVAILABLE"
except Exception as e:
    components_status["ArchitectCore"] = f"ERROR: {str(e)[:50]}"

for component, status in components_status.items():
    print(f"{component:20} : {status}")

print("\n" + "="*70)
print("RUNTIME LOOP FIX STATUS")
print("="*70)

# Check if fix is in place
try:
    with open(project_root / "run_elysia_unified.py", 'r') as f:
        content = f.read()
        if "project_guardian.runtime_loop_core import RuntimeLoop" in content:
            print("[OK] Runtime loop fallback fix is APPLIED")
            print("     System will use project_guardian.RuntimeLoop as fallback")
        else:
            print("[WARN] Runtime loop fallback fix may not be applied")
except Exception as e:
    print(f"[ERROR] Could not check fix status: {e}")

print("\n" + "="*70)
print("RECOMMENDATION")
print("="*70)

if all("AVAILABLE" in status for status in components_status.values()):
    print("[SUCCESS] All components are available")
    print("          System should start successfully")
    print("          After restart, runtime_loop should show: True")
else:
    print("[WARNING] Some components have issues")
    print("          Check errors above")

print("\nTo restart: Double-click START_ELYSIA_UNIFIED.bat")
print("="*70)

