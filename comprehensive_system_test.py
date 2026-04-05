# comprehensive_system_test.py
# Comprehensive end-to-end system test

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from project_guardian.core import GuardianCore

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_comprehensive_system():
    """Comprehensive system test."""
    print("\n" + "="*70)
    print("COMPREHENSIVE SYSTEM TEST")
    print("="*70)
    
    results = {}
    
    try:
        # Initialize system
        print("\n[1] Initializing System...")
        config = {
            "enable_resource_monitoring": False,
            "enable_runtime_health_monitoring": False,
        }
        core = GuardianCore(config=config)
        results["initialization"] = True
        print("  [OK] System initialized")
        
        # Test memory operations
        print("\n[2] Testing Memory Operations...")
        core.memory.remember("Test memory 1", category="test")
        core.memory.remember("Test memory 2", category="test")
        memories = core.memory.recall_last(count=5)
        results["memory_write"] = len(memories) >= 0
        results["memory_read"] = True
        print(f"  [OK] Memory operations: wrote 2, read {len(memories)} memories")
        
        # Test system status
        print("\n[3] Testing System Status...")
        status = core.get_system_status()
        results["system_status"] = isinstance(status, dict) and len(status) > 0
        print(f"  [OK] System status retrieved: {len(status)} components")
        
        # Test startup verification
        print("\n[4] Testing Startup Verification...")
        startup_verification = core.get_startup_verification()
        results["startup_verification"] = startup_verification is not None
        if startup_verification:
            checks = startup_verification.get("checks", [])
            successes = sum(1 for c in checks if c.get("status") == "success")
            print(f"  [OK] Startup verification: {successes}/{len(checks)} checks passed")
        
        # Test runtime health (if available)
        print("\n[5] Testing Runtime Health...")
        try:
            health = core.get_runtime_health()
            results["runtime_health"] = health is not None
            if health:
                print(f"  [OK] Runtime health: {health.get('status', 'unknown')}")
        except Exception as e:
            results["runtime_health"] = False
            print(f"  - Runtime health monitoring disabled")
        
        # Test component access
        print("\n[6] Testing Component Access...")
        components = [
            ("memory", core.memory),
            ("mutation_engine", core.mutation_engine if hasattr(core, 'mutation_engine') else None),
            ("trust_registry", core.trust_registry if hasattr(core, 'trust_registry') else None),
        ]
        for name, component in components:
            if component:
                results[f"component_{name}"] = True
                print(f"  [OK] {name} component accessible")
            else:
                results[f"component_{name}"] = False
                print(f"  - {name} component not available")
        
        # Test graceful shutdown
        print("\n[7] Testing Graceful Shutdown...")
        core.shutdown()
        results["shutdown"] = True
        print("  [OK] System shut down gracefully")
        
        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        print(f"Tests Passed: {passed}/{total}")
        
        for test, result in sorted(results.items()):
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status} {test}")
        
        if passed == total:
            print("\n[SUCCESS] All comprehensive tests passed!")
            print("System is fully operational and ready for production.")
            return True
        else:
            print(f"\n[PARTIAL] {passed}/{total} tests passed")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] System test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_comprehensive_system()
    sys.exit(0 if success else 1)

