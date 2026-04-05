#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Force Elysia to Learn Right Now
Runs a learning cycle and immediately shows what was learned
"""

import sys
import os
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Load API keys
try:
    from load_api_keys import load_api_keys
    load_api_keys()
    print("✅ API keys loaded")
except:
    pass

print("="*70)
print("FORCING ELYSIA TO LEARN NOW")
print("="*70)
print()

try:
    from project_guardian.core import GuardianCore
    from organized_project.src.learning.web.online_learning_system import OnlineLearningSystem
    
    # Initialize
    print("1. Initializing Elysia...")
    core = GuardianCore({
        "enable_resource_monitoring": False,
        "enable_runtime_health_monitoring": False,
    })
    memory = core.memory
    
    # Count before
    before = memory.recall_last(count=1000)
    before_count = len(before)
    print(f"   ✅ Memory system loaded ({before_count} existing memories)")
    
    # Create learning system
    learning = OnlineLearningSystem(memory_system=memory)
    print("   ✅ Learning system ready\n")
    
    # Learn from Reddit
    print("2. Learning from Reddit...")
    print("-"*70)
    
    async def learn_now():
        result = await learning.learn_from_social_media(
            platform="reddit",
            query="AI autonomous systems",
            max_posts=5
        )
        return result
    
    result = asyncio.run(learn_now())
    
    if result.get("status") == "success":
        posts = result.get("data", {}).get("posts_processed", 0)
        print(f"   ✅ Learned from {posts} Reddit posts!")
    else:
        print(f"   ⚠️  {result.get('message', 'Unknown error')}")
    
    # Check what was stored
    print("\n3. Checking what Elysia learned...")
    print("-"*70)
    
    after = memory.recall_last(count=1000)
    after_count = len(after)
    new_memories = after_count - before_count
    
    print(f"   📊 New memories created: {new_memories}")
    
    # Find the new learning memories
    new_learning = []
    for mem in after[:20]:  # Check last 20
        thought = mem.get('thought', mem.get('content', ''))
        category = mem.get('category', '')
        
        if 'learn' in thought.lower()[:50] or category == 'learning':
            new_learning.append(mem)
    
    if new_learning:
        print(f"\n   ✅ Found {len(new_learning)} new learning memories!")
        print("\n   What Elysia learned:")
        print("-"*70)
        
        for i, mem in enumerate(new_learning[:10], 1):
            thought = mem.get('thought', mem.get('content', ''))
            category = mem.get('category', 'unknown')
            time = mem.get('time', mem.get('timestamp', 'unknown'))
            
            print(f"\n   {i}. [{time}] Category: {category}")
            print(f"      {thought[:300]}...")
    else:
        print("\n   ⚠️  No learning memories found in recent memories")
        print("   Showing all recent memories to debug:")
        for i, mem in enumerate(after[:5], 1):
            print(f"\n   {i}. {mem}")
    
    print("\n" + "="*70)
    print("LEARNING COMPLETE")
    print("="*70)
    print("\nNow run: python query_elysia_knowledge.py")
    print("to see all learned content organized by category.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()















