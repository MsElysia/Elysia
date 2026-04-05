#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick Learning Summary
Shows a quick summary of what Elysia has learned
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("="*70)
print("ELYSIA LEARNING SUMMARY")
print("="*70)
print()

try:
    from project_guardian.core import GuardianCore
    
    core = GuardianCore({
        "enable_resource_monitoring": False,
        "enable_runtime_health_monitoring": False,
    })
    memory = core.memory
    
    # Get recent memories
    recent = memory.recall_last(count=200)
    
    # Count by category
    categories = {
        "Reddit": 0,
        "Web Articles": 0,
        "Financial": 0,
        "LLM Research": 0,
        "RSS": 0,
        "Other": 0
    }
    
    for mem in recent:
        tags = mem.get('tags', [])
        tag_str = ' '.join(str(t).lower() for t in tags)
        
        if 'reddit' in tag_str:
            categories["Reddit"] += 1
        elif 'web' in tag_str or 'article' in tag_str:
            categories["Web Articles"] += 1
        elif 'financial' in tag_str:
            categories["Financial"] += 1
        elif 'llm' in tag_str or 'research' in tag_str:
            categories["LLM Research"] += 1
        elif 'rss' in tag_str:
            categories["RSS"] += 1
        else:
            categories["Other"] += 1
    
    print("📊 Learning Summary:")
    print("-"*70)
    total = sum(categories.values())
    
    for category, count in categories.items():
        if count > 0:
            percentage = (count / total * 100) if total > 0 else 0
            bar = "█" * int(percentage / 2)
            print(f"{category:20} {count:4} items {bar} {percentage:.1f}%")
    
    print("-"*70)
    print(f"{'TOTAL':20} {total:4} items")
    print()
    
    # Show sample of recent learning
    print("📝 Recent Learning Samples:")
    print("-"*70)
    
    learning_samples = []
    for mem in recent[:20]:
        content = mem.get('thought', mem.get('content', mem.get('memory', '')))
        tags = mem.get('tags', [])
        
        if any('learn' in str(t).lower() or 'reddit' in str(t).lower()) or 
               'web' in str(t).lower() or 'financial' in str(t).lower() 
               for t in tags):
            learning_samples.append((content[:150], tags))
    
    for i, (content, tags) in enumerate(learning_samples[:5], 1):
        print(f"\n{i}. {content}...")
        if tags:
            print(f"   Tags: {', '.join(str(t) for t in tags[:3])}")
    
    print("\n" + "="*70)
    print("✅ Summary Complete")
    print("="*70)
    print("\nFor detailed view, run: python query_elysia_knowledge.py")
    print("For search, run: python search_elysia_knowledge.py 'topic'")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nCheck the learning session log instead:")
    print("   python monitor_learning_session.py")

