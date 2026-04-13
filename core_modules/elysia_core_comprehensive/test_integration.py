#!/usr/bin/env python3
"""
Integration Test: Project Guardian + Elysia Core
Tests the merged system functionality.
"""

import sys
import os
import time

def test_enhanced_memory():
    """Test enhanced memory functionality"""
    print("🧠 Testing Enhanced Memory...")
    
    try:
        from enhanced_memory_core import EnhancedMemoryCore
        
        memory = EnhancedMemoryCore("test_memory.json")
        
        # Test basic functionality
        memory.remember("Test memory", category="test", priority=0.8)
        memory.remember("Another test", category="test", priority=0.6)
        memory.remember("System event", category="system", priority=0.9)
        
        # Test enhanced features
        stats = memory.get_memory_stats()
        assert stats["total_memories"] == 3
        assert stats["categories"] == 2
        
        # Test search
        results = memory.search_memories("test", category="test")
        assert len(results) == 2
        
        # Test high priority
        high_priority = memory.get_high_priority_memories(threshold=0.7)
        assert len(high_priority) == 2
        
        print("   ✅ Enhanced memory test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Enhanced memory test failed: {e}")
        return False

def test_enhanced_trust():
    """Test enhanced trust functionality"""
    print("🤝 Testing Enhanced Trust...")
    
    try:
        from enhanced_trust_matrix import EnhancedTrustMatrix
        
        trust = EnhancedTrustMatrix("test_trust.json")
        
        # Test basic functionality
        trust.update_trust("test_component", 0.1, "Test operation", "test")
        trust.update_trust("another_component", -0.2, "Failed operation", "test")
        
        # Test enhanced features
        stats = trust.get_trust_stats()
        assert stats["total_components"] == 2
        
        # Test validation
        can_mutate = trust.validate_trust_for_action("test_component", "mutation", 0.6)
        assert can_mutate == False  # Trust too low
        
        # Test warnings
        warnings = trust.get_low_trust_warnings(threshold=0.3)
        assert len(warnings) == 1
        
        print("   ✅ Enhanced trust test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Enhanced trust test failed: {e}")
        return False

def test_enhanced_tasks():
    """Test enhanced task functionality"""
    print("📋 Testing Enhanced Tasks...")
    
    try:
        from enhanced_task_engine import EnhancedTaskEngine
        from enhanced_memory_core import EnhancedMemoryCore
        
        memory = EnhancedMemoryCore("test_memory.json")
        task_engine = EnhancedTaskEngine(memory, "test_tasks.json")
        
        # Test basic functionality
        task1 = task_engine.create_task(
            "Test Task",
            "Test description",
            priority=0.7,
            category="test"
        )
        
        task2 = task_engine.create_task(
            "Another Task",
            "Another description",
            priority=0.5,
            category="test"
        )
        
        # Test enhanced features
        stats = task_engine.get_task_stats()
        assert stats["total_tasks"] == 2
        assert stats["active_tasks"] == 2
        
        # Test status update
        task_engine.update_task_status(task1["id"], "in_progress", "Started")
        task_engine.complete_task(task1["id"])
        
        # Test search
        test_tasks = task_engine.search_tasks("Test", category="test")
        assert len(test_tasks) == 1
        
        print("   ✅ Enhanced tasks test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Enhanced tasks test failed: {e}")
        return False

def test_runtime_integration():
    """Test runtime loop integration"""
    print("🔄 Testing Runtime Integration...")
    
    try:
        from elysia_runtime_loop import ElysiaRuntimeLoop
        
        # Initialize runtime (should use enhanced components)
        runtime = ElysiaRuntimeLoop()
        
        # Test that enhanced components are loaded
        assert hasattr(runtime, 'memory')
        assert hasattr(runtime, 'trust')
        assert hasattr(runtime, 'tasks')
        
        # Test Guardian integration if available
        if hasattr(runtime, 'guardian'):
            print("   ✅ Project Guardian integration detected")
        else:
            print("   ⚠️  Project Guardian not available, using basic components")
        
        print("   ✅ Runtime integration test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Runtime integration test failed: {e}")
        return False

def cleanup_test_files():
    """Clean up test files"""
    test_files = [
        "test_memory.json",
        "test_trust.json", 
        "test_tasks.json"
    ]
    
    for file in test_files:
        if os.path.exists(file):
            os.remove(file)
            print(f"   🧹 Cleaned up {file}")

def main():
    """Run integration tests"""
    print("🛡️ Project Guardian Integration Test")
    print("=" * 50)
    
    tests = [
        test_enhanced_memory,
        test_enhanced_trust,
        test_enhanced_tasks,
        test_runtime_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    # Cleanup
    cleanup_test_files()
    
    # Results
    print("📊 Test Results:")
    print(f"   Passed: {passed}/{total}")
    print(f"   Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 All tests passed! Integration successful.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
