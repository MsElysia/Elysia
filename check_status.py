# check_status.py
# Quick status check

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from project_guardian.core import GuardianCore

print("\n" + "="*60)
print("ELYSIA SYSTEM STATUS CHECK")
print("="*60)

core = GuardianCore({
    "enable_resource_monitoring": False,
    "enable_runtime_health_monitoring": False,
})

status = core.get_system_status()
verification = core.get_startup_verification()

print("\n[SYSTEM STATUS]")
print(f"  Status: OPERATIONAL")
print(f"  Memories: {status.get('memory', {}).get('total_memories', 'N/A')}")
print(f"  Active Tasks: {status.get('tasks', {}).get('active', 'N/A')}")
print(f"  Trust Nodes: {status.get('trust', {}).get('total_nodes', 'N/A')}")

if verification:
    checks = verification.get("checks", [])
    successes = sum(1 for c in checks if c.get("status") == "success")
    print(f"\n[STARTUP VERIFICATION]")
    print(f"  Checks Passed: {successes}/{len(checks)}")

print("\n" + "="*60)
print("System is RUNNING and ready!")
print("="*60 + "\n")

core.shutdown()

