#!/usr/bin/env python3
"""
Quick Manual Tests - Simple verification scripts
Run these one at a time to verify workflows
"""

import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_credits():
    """Test CoreCredits functionality."""
    print("="*70)
    print("TEST: CoreCredits")
    print("="*70)
    
    from project_guardian.core_credits import CoreCredits
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        credits = CoreCredits(storage_path=str(Path(temp_dir) / "credits.json"))
        
        # Create account
        account_id = credits.create_account(name="Test User", initial_balance=100.0)
        print(f"✅ Created account: {account_id}")
        
        # Check balance
        balance = credits.get_balance(account_id)
        print(f"✅ Initial balance: {balance}")
        
        # Earn credits
        credits.earn_credits(account_id, 50.0, "test earnings")
        balance = credits.get_balance(account_id)
        print(f"✅ Balance after earnings: {balance}")
        
        if balance == 150.0:
            print("✅ TEST PASSED: CoreCredits works correctly")
            return True
        else:
            print(f"❌ TEST FAILED: Expected 150.0, got {balance}")
            return False
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_memory():
    """Test MemoryCore functionality."""
    print("\n" + "="*70)
    print("TEST: MemoryCore")
    print("="*70)
    
    from project_guardian.memory import MemoryCore
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        memory = MemoryCore(filepath=str(Path(temp_dir) / "memory.json"))
        
        # Store memory
        memory.remember("Test memory", category="test", priority=0.8)
        print("✅ Stored memory")
        
        # Check if stored
        if hasattr(memory, 'memory_log') and len(memory.memory_log) > 0:
            print(f"✅ Memory log has {len(memory.memory_log)} entries")
            print("✅ TEST PASSED: MemoryCore works correctly")
            return True
        else:
            print("❌ TEST FAILED: Memory not stored")
            return False
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_mutation_components():
    """Test mutation components initialize."""
    print("\n" + "="*70)
    print("TEST: Mutation Components")
    print("="*70)
    
    from project_guardian.mutation_engine import MutationEngine
    from project_guardian.mutation_review_manager import MutationReviewManager
    from project_guardian.mutation_router import MutationRouter
    from project_guardian.trust_registry import TrustRegistry
    from project_guardian.trust_policy_manager import TrustPolicyManager
    from project_guardian.trust_eval_action import TrustEvalAction
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        # Initialize dependencies
        trust_registry = TrustRegistry(storage_path=str(Path(temp_dir) / "trust.json"))
        trust_policy = TrustPolicyManager(storage_path=str(Path(temp_dir) / "trust_policy.json"))
        trust_eval = TrustEvalAction(trust_registry=trust_registry)
        
        # Test MutationEngine
        engine = MutationEngine(
            runtime_loop=None,
            trust_eval=trust_eval,
            ask_ai=None,
            storage_path=str(Path(temp_dir) / "mutations.json")
        )
        print("✅ MutationEngine initialized")
        
        # Test ReviewManager
        review_manager = MutationReviewManager(
            trust_registry=trust_registry,
            trust_policy_manager=trust_policy
        )
        print("✅ MutationReviewManager initialized")
        
        # Test Router
        router = MutationRouter(
            trust_registry=trust_registry,
            trust_policy_manager=trust_policy
        )
        print("✅ MutationRouter initialized")
        
        print("✅ TEST PASSED: All mutation components initialize")
        return True
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_master_slave():
    """Test master-slave components."""
    print("\n" + "="*70)
    print("TEST: Master-Slave Components")
    print("="*70)
    
    from project_guardian.master_slave_controller import MasterSlaveController
    from project_guardian.slave_deployment import SlaveDeployment
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    try:
        # Test MasterSlaveController
        controller = MasterSlaveController(
            master_id="test_master_001",
            master_name="Test Master",
            storage_path=str(Path(temp_dir) / "master_slave.json")
        )
        print("✅ MasterSlaveController initialized")
        
        # Test SlaveDeployment
        deployment = SlaveDeployment(
            master_controller=controller,
            slave_code_package="test_package.zip"
        )
        print("✅ SlaveDeployment initialized")
        
        print("✅ TEST PASSED: Master-slave components initialize")
        return True
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    print("\n" + "="*70)
    print("QUICK MANUAL TESTS")
    print("="*70)
    print("Running simple verification tests...")
    print("Run individual tests or all together")
    print("="*70 + "\n")
    
    results = []
    
    # Run all tests
    results.append(("CoreCredits", test_credits()))
    results.append(("MemoryCore", test_memory()))
    results.append(("Mutation Components", test_mutation_components()))
    results.append(("Master-Slave", test_master_slave()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} passed")
    print("="*70)
    
    sys.exit(0 if passed == total else 1)

