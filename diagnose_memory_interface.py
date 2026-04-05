#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix Learning Memory Integration
Updates learning systems to properly store in GuardianCore memory
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("="*70)
print("FIXING LEARNING MEMORY INTEGRATION")
print("="*70)
print()

# Check how GuardianCore memory works
try:
    from project_guardian.core import GuardianCore
    
    print("1. Testing GuardianCore memory interface...")
    core = GuardianCore({
        "enable_resource_monitoring": False,
        "enable_runtime_health_monitoring": False,
    })
    memory = core.memory
    
    print(f"   Memory type: {type(memory)}")
    print(f"   Has 'remember' method: {hasattr(memory, 'remember')}")
    print(f"   Has 'execute' method: {hasattr(memory, 'execute')}")
    print(f"   Has 'store' method: {hasattr(memory, 'store')}")
    print(f"   Methods: {[m for m in dir(memory) if not m.startswith('_')]}")
    
    # Test storing
    print("\n2. Testing memory storage...")
    try:
        if hasattr(memory, 'remember'):
            result = memory.remember(
                "Test learning content from Reddit: AI systems are advancing",
                category="learning",
                tags=["reddit", "test", "ai"]
            )
            print(f"   ✅ 'remember' works: {result}")
        elif hasattr(memory, 'store'):
            result = memory.store(
                thought="Test learning content",
                category="learning",
                tags=["test"]
            )
            print(f"   ✅ 'store' works: {result}")
        elif hasattr(memory, 'execute'):
            result = memory.execute("store_memory", {
                "content": "Test learning content",
                "memory_type": "knowledge",
                "tags": ["test"]
            })
            print(f"   ✅ 'execute' works: {result}")
        else:
            print("   ⚠️  Unknown memory interface")
    except Exception as e:
        print(f"   ⚠️  Error testing storage: {e}")
        import traceback
        traceback.print_exc()
    
    # Check what's actually in memory
    print("\n3. Checking stored content...")
    try:
        recent = memory.recall_last(count=10)
        print(f"   Found {len(recent)} recent memories")
        
        # Show structure
        if recent:
            print("\n   Memory structure example:")
            first = recent[0]
            print(f"   Keys: {list(first.keys())}")
            print(f"   Sample: {first}")
    except Exception as e:
        print(f"   ⚠️  Error checking memory: {e}")
    
    print("\n" + "="*70)
    print("DIAGNOSIS COMPLETE")
    print("="*70)
    print("\nNow updating learning systems to use correct interface...")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()















