#!/usr/bin/env python3
"""
Memory Cleanup Script
=====================
Quick script to cleanup and consolidate Project Guardian memories
"""

import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

try:
    from project_guardian.core import GuardianCore
    from project_guardian.memory_cleanup import MemoryCleanup, auto_cleanup_memory
    
    print("="*60)
    print("Project Guardian Memory Cleanup")
    print("="*60)
    print()
    
    # Initialize GuardianCore
    print("Loading Guardian Core...")
    core = GuardianCore()
    
    # Get current memory stats
    if hasattr(core.memory, 'memory_log'):
        current_count = len(core.memory.memory_log)
        print(f"Current memory count: {current_count}")
        
        # Get size estimate
        cleanup = MemoryCleanup(core.memory)
        stats = cleanup.get_memory_size_estimate()
        if "error" not in stats:
            print(f"Estimated memory size: {stats.get('estimated_size_mb', 0):.2f} MB")
        
        # Ask for confirmation
        if current_count > 5000:
            print(f"\n⚠️  Memory count ({current_count}) is high!")
            print("Recommended: Consolidate to 5000 memories")
            
            response = input("\nProceed with cleanup? (y/n): ").strip().lower()
            if response == 'y':
                print("\nPerforming memory consolidation...")
                result = core.memory.consolidate(max_memories=5000, keep_recent_days=30)
                
                if "error" not in result:
                    print(f"\n✅ Cleanup completed!")
                    print(f"   Original: {result.get('original_count', 0)} memories")
                    print(f"   Final: {result.get('final_count', 0)} memories")
                    print(f"   Removed: {result.get('removed', 0)} memories")
                    print(f"   Recent kept: {result.get('recent_kept', 0)}")
                    print(f"   High priority kept: {result.get('high_priority_kept', 0)}")
                else:
                    print(f"\n❌ Error: {result.get('error')}")
            else:
                print("Cleanup cancelled.")
        else:
            print(f"\n✅ Memory count ({current_count}) is within normal range.")
            print("No cleanup needed.")
    else:
        print("❌ Memory system not available")
    
    print("\n" + "="*60)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

