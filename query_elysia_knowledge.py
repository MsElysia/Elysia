#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Query Elysia's Learned Knowledge
Shows what Elysia has learned from her learning sessions
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("="*70)
print("ELYSIA'S LEARNED KNOWLEDGE")
print("="*70)
print()

# Try to load GuardianCore memory system
try:
    from project_guardian.core import GuardianCore
    
    print("1. Loading Elysia's memory system...")
    core = GuardianCore({
        "enable_resource_monitoring": False,
        "enable_runtime_health_monitoring": False,
    })
    memory = core.memory
    print("   ✅ Memory system loaded\n")
    
    # Search for learned content
    print("2. Searching for learned content...")
    print("-"*70)
    
    # Learning-related tags to search for
    learning_tags = [
        "web_learning",
        "reddit",
        "financial_learning",
        "llm_research",
        "learning",
        "knowledge",
        "article",
        "rss_feed"
    ]
    
    all_memories = []
    learned_content = defaultdict(list)
    
    # Try different methods to retrieve memories
    try:
        # Method 1: Recall recent memories
        recent = memory.recall_last(count=100)
        if recent:
            all_memories.extend(recent)
            print(f"   ✅ Found {len(recent)} recent memories")
    except:
        pass
    
    try:
        # Method 2: Search by tags
        for tag in learning_tags:
            try:
                if hasattr(memory, 'search'):
                    results = memory.search(tag)
                    if results:
                        all_memories.extend(results)
            except:
                pass
    except:
        pass
    
    try:
        # Method 3: Get all memories if possible
        if hasattr(memory, 'get_all'):
            all_mem = memory.get_all()
            if all_mem:
                all_memories.extend(all_mem)
    except:
        pass
    
    # Filter and categorize learned content
    print("\n3. Categorizing learned content...")
    print("-"*70)
    
    categories = {
        "Reddit Learning": [],
        "Web Articles": [],
        "Financial Learning": [],
        "LLM Research": [],
        "RSS Feeds": [],
        "Other Learning": []
    }
    
    for mem in all_memories:
        content = mem.get('thought', mem.get('content', mem.get('memory', '')))
        tags = mem.get('tags', [])
        category = mem.get('category', '')
        content_lower = content.lower()
        
        # Categorize based on content, tags, and category
        # GuardianCore stores with category="learning" and content contains source info
        if 'reddit' in content_lower or any('reddit' in str(tag).lower() for tag in tags):
            categories["Reddit Learning"].append(mem)
        elif 'financial learning' in content_lower or 'financial' in content_lower:
            categories["Financial Learning"].append(mem)
        elif 'research insight' in content_lower or 'llm' in content_lower or 'gpt' in content_lower or 'claude' in content_lower:
            categories["LLM Research"].append(mem)
        elif 'rss' in content_lower or any('rss' in str(tag).lower() or 'feed' in str(tag).lower() for tag in tags):
            categories["RSS Feeds"].append(mem)
        elif 'learned from web' in content_lower or 'web' in content_lower or any('web' in str(tag).lower() or 'article' in str(tag).lower() for tag in tags):
            categories["Web Articles"].append(mem)
        elif category.lower() == 'learning' or 'learn' in content_lower[:50]:
            categories["Other Learning"].append(mem)
    
    # Display results
    print("\n4. Learned Content Summary:")
    print("="*70)
    
    total_items = 0
    for category, items in categories.items():
        count = len(items)
        total_items += count
        if count > 0:
            print(f"\n📚 {category}: {count} items")
            print("-"*70)
            
            # Show first 3 items as examples
            for i, item in enumerate(items[:3], 1):
                content = item.get('thought', item.get('content', item.get('memory', '')))
                timestamp = item.get('timestamp', item.get('created_at', 'Unknown'))
                
                # Truncate content for display
                preview = content[:200] if len(content) > 200 else content
                print(f"\n   {i}. [{timestamp}]")
                print(f"      {preview}...")
            
            if count > 3:
                print(f"\n   ... and {count - 3} more items")
    
    print("\n" + "="*70)
    print(f"TOTAL LEARNED ITEMS: {total_items}")
    print("="*70)
    
    # Show detailed statistics
    print("\n5. Learning Statistics:")
    print("-"*70)
    
    # Count by source (check content and category)
    source_counts = defaultdict(int)
    for mem in all_memories:
        content = str(mem.get('thought', mem.get('content', ''))).lower()
        category = str(mem.get('category', '')).lower()
        
        if 'reddit' in content:
            source_counts['Reddit'] += 1
        elif 'learned from web' in content or 'web' in content:
            source_counts['Web'] += 1
        elif 'financial learning' in content or 'financial' in content:
            source_counts['Financial'] += 1
        elif 'research insight' in content or 'llm' in content or 'gpt' in content or 'claude' in content:
            source_counts['LLM Research'] += 1
        elif 'rss' in content:
            source_counts['RSS'] += 1
        elif category == 'learning':
            source_counts['Learning'] += 1
    
    for source, count in source_counts.items():
        print(f"   {source}: {count} items")
    
    # Show recent learning activity
    print("\n6. Recent Learning Activity:")
    print("-"*70)
    
    # Sort by timestamp if available
    try:
        sorted_memories = sorted(
            all_memories,
            key=lambda x: x.get('timestamp', x.get('created_at', '')),
            reverse=True
        )[:10]
        
        for i, mem in enumerate(sorted_memories, 1):
            content = mem.get('thought', mem.get('content', mem.get('memory', '')))
            timestamp = mem.get('timestamp', mem.get('created_at', 'Unknown'))
            preview = content[:150] if len(content) > 150 else content
            print(f"\n   {i}. [{timestamp}]")
            print(f"      {preview}...")
    except:
        print("   Could not sort by timestamp")
    
    print("\n" + "="*70)
    print("✅ Knowledge Query Complete")
    print("="*70)
    print("\nTo see more details, check Elysia's memory system directly.")
    print("You can also check the learning session log: elysia_learning_session.log")
    
except ImportError as e:
    print(f"❌ Could not import GuardianCore: {e}")
    print("\nAlternative: Check the learning session log file:")
    print("   - elysia_learning_session.log")
    print("\nOr use the memory system directly if available.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    
    print("\n" + "="*70)
    print("ALTERNATIVE: Check Learning Session Log")
    print("="*70)
    print("\nYou can view what Elysia learned by checking the log file:")
    print("   python monitor_learning_session.py")
    print("\nOr view the log directly:")
    print("   Get-Content elysia_learning_session.log")

